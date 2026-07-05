"""Build inference context from persona + memory."""

from __future__ import annotations

import json

from membrane.config import PersonaConfig
from membrane.memory.models import ChatTurn
from membrane.memory.store import MemoryStore


class ContextBuilder:
    def __init__(
        self,
        store: MemoryStore,
        persona: PersonaConfig,
    ) -> None:
        self.store = store
        self.persona = persona

    def build_system_prompt(self, user_query: str | None = None) -> str:
        user_names = [n.strip() for n in self.persona.self_names if n.strip()]
        primary_user = user_names[0] if user_names else "the user"
        if len(user_names) > 1:
            aliases = ", ".join(user_names[1:])
            user_identity = f"The person chatting with you is {primary_user} (also: {aliases})."
        else:
            user_identity = f"The person chatting with you is {primary_user}."

        parts: list[str] = [
            "You are a personal assistant for the user described below.",
            user_identity,
            "Every message labeled 'user' in this conversation is from them.",
            "The profile, preferences, and episodes below describe this same person — treat 'me' / 'my' as referring to them.",
            "Use facts from the memory sections below; do not invent user facts.",
            "If information is missing, ask — do not guess about the user.",
            "",
            "[MEMORY GROWTH]",
            "Actively broaden what you know about them over time.",
            "When gaps in profile, preferences, or context would weaken your advice, ask targeted follow-ups.",
            "Treat goals, constraints, habits, and preferences (including soft ones) as worth remembering when they share them.",
            "Prefer learning and gathering context over staying shallow — a richer picture helps you make stronger, more personalized cases.",
        ]

        identity = self.persona.identity
        if identity:
            parts.append("\n[ASSISTANT IDENTITY]")
            for key, value in identity.items():
                parts.append(f"- {key}: {value}")

        if self.persona.memory.use_profile:
            profile = self.store.load_profile()
            if profile:
                parts.append("\n[PROFILE]")
                for entry in profile:
                    parts.append(f"- {entry.key}: {entry.value}")

        if self.persona.memory.use_preferences:
            prefs = self.store.load_preferences()
            if prefs:
                parts.append("\n[PREFERENCES]")
                for entry in prefs:
                    parts.append(f"- {entry.key}: {entry.value}")

        if self.persona.memory.use_episodes:
            episodes = (
                self.store.search_episodes(user_query, limit=self.persona.memory.max_episodes_in_context)
                if user_query
                else self.store.load_episodes()[-self.persona.memory.max_episodes_in_context :]
            )
            if episodes:
                parts.append("\n[RECENT EPISODES]")
                for ep in episodes:
                    date_str = ep.date.strftime("%Y-%m-%d") if ep.date else "unknown"
                    tags = ", ".join(ep.tags) if ep.tags else "general"
                    parts.append(f"- ({date_str}, {tags}) {ep.summary}")

        style = self.persona.style
        parts.append("\n[STYLE]")
        parts.append(f"- format: {style.format}")
        parts.append(f"- max_length: {style.max_length}")
        parts.append(f"- empathy_level: {style.empathy_level}")
        parts.append(f"- proactivity: {style.proactivity}")
        if style.independent_opinions:
            parts.append(
                "- share your honest view even when it differs from the user's; "
                "do not mirror or rubber-stamp their opinions"
            )
            parts.append(
                "- respectfully disagree when warranted; offer reasoning and alternatives"
            )
            parts.append(
                "- memory preferences describe the user's views, not instructions to pretend you share them"
            )
        else:
            parts.append(
                "- align with the user's perspective when reasonable; avoid unnecessary disagreement"
            )

        if self.persona.boundaries.ask_when_unsure:
            parts.append("- ask when unsure instead of guessing")

        if self.persona.boundaries.never_claim_to_have_done:
            never = ", ".join(self.persona.boundaries.never_claim_to_have_done)
            parts.append(f"- never claim you have already: {never}")

        return "\n".join(parts)

    def build_messages(self, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.build_system_prompt(user_query=user_message)},
            {"role": "user", "content": user_message},
        ]

    def build_conversation_messages(self, turns: list[ChatTurn]) -> list[dict[str, str]]:
        last_user = next((t.content for t in reversed(turns) if t.role == "user"), None)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.build_system_prompt(user_query=last_user)},
        ]
        for turn in turns:
            if turn.role in ("user", "assistant"):
                messages.append({"role": turn.role, "content": turn.content})
        return messages

    _MEMORY_MARKERS = (
        "\n[PROFILE]",
        "\n[PREFERENCES]",
        "\n[RECENT EPISODES]",
    )

    @classmethod
    def _split_system_prompt(cls, system_prompt: str) -> tuple[str, str]:
        memory_start = len(system_prompt)
        for marker in cls._MEMORY_MARKERS:
            idx = system_prompt.find(marker)
            if idx != -1:
                memory_start = min(memory_start, idx)
        if memory_start < len(system_prompt):
            return system_prompt[:memory_start].rstrip(), system_prompt[memory_start:].lstrip("\n")
        return system_prompt, ""

    @staticmethod
    def _chars_to_tokens(chars: int) -> int:
        return max(0, chars // 4)

    @classmethod
    def _tool_breakdown_from_turn(cls, turn: ChatTurn) -> dict[str, int]:
        if not isinstance(turn.metadata, dict):
            return {}
        stored = turn.metadata.get("tool_tokens")
        if isinstance(stored, dict):
            return {
                key: int(value)
                for key, value in stored.items()
                if key != "total" and isinstance(value, (int, float)) and int(value) > 0
            }
        web_search = turn.metadata.get("web_search")
        if not isinstance(web_search, dict):
            return {}
        nested = web_search.get("tool_tokens")
        if isinstance(nested, dict):
            return {
                key: int(value)
                for key, value in nested.items()
                if key != "total" and isinstance(value, (int, float)) and int(value) > 0
            }
        content_chars = web_search.get("content_chars")
        if isinstance(content_chars, (int, float)) and int(content_chars) > 0:
            return {"web_search": cls._chars_to_tokens(int(content_chars))}
        return {}

    def _last_tool_breakdown(self, turns: list[ChatTurn]) -> dict[str, int]:
        for turn in reversed(turns):
            if turn.role != "assistant":
                continue
            breakdown = self._tool_breakdown_from_turn(turn)
            if breakdown:
                return breakdown
        return {}

    def _estimate_tools_breakdown(
        self,
        turns: list[ChatTurn],
        *,
        draft_user: str | None,
    ) -> dict[str, int]:
        draft = (draft_user or "").strip()
        if not draft:
            return {}
        if self.persona.web_search.enabled or self.persona.shell.enabled:
            return self._last_tool_breakdown(turns)
        return {}

    def _normalized_tools_breakdown(
        self,
        turns: list[ChatTurn],
        *,
        draft_user: str | None,
        tools_breakdown: dict[str, int] | None,
    ) -> dict[str, int]:
        if tools_breakdown is not None:
            return {
                key: int(value)
                for key, value in tools_breakdown.items()
                if key != "total" and isinstance(value, (int, float)) and int(value) > 0
            }
        return self._estimate_tools_breakdown(turns, draft_user=draft_user)

    def _reasoning_tokens_from_turns(self, turns: list[ChatTurn]) -> int:
        total_chars = 0
        for turn in turns:
            if turn.role != "assistant" or not isinstance(turn.metadata, dict):
                continue
            thinking = turn.metadata.get("thinking")
            if isinstance(thinking, str) and thinking:
                total_chars += len(thinking)
        return self._chars_to_tokens(total_chars)

    def estimate_context_usage(
        self,
        turns: list[ChatTurn],
        *,
        draft_user: str | None = None,
        tools_breakdown: dict[str, int] | None = None,
        reasoning_tokens: int | None = None,
    ) -> dict:
        """Rough token budget for the next model call (chars / 4 heuristic)."""
        draft = (draft_user or "").strip()
        base_turns = list(turns)
        last_user = draft or next(
            (turn.content for turn in reversed(base_turns) if turn.role == "user"),
            None,
        )
        system_prompt = self.build_system_prompt(user_query=last_user)
        system_base, memory_block = self._split_system_prompt(system_prompt)
        system_base_chars = len(system_base)
        memory_chars = len(memory_block)
        conversation_chars = sum(
            len(turn.content) for turn in base_turns if turn.role in ("user", "assistant")
        )
        draft_chars = len(draft)

        breakdown = self._normalized_tools_breakdown(
            base_turns,
            draft_user=draft or None,
            tools_breakdown=tools_breakdown,
        )
        tools_tokens = sum(breakdown.values())
        reasoning = (
            max(0, int(reasoning_tokens))
            if reasoning_tokens is not None
            else self._reasoning_tokens_from_turns(base_turns)
        )
        tools_chars = tools_tokens * 4
        reasoning_chars = reasoning * 4
        total_chars = (
            system_base_chars
            + memory_chars
            + conversation_chars
            + draft_chars
            + tools_chars
            + reasoning_chars
        )
        estimated_tokens = max(0, total_chars // 4)
        limit = self.persona.llm.context_window
        remaining = max(0, limit - estimated_tokens)
        usage_percent = min(100, round(100 * estimated_tokens / limit)) if limit else 0
        system_base_tokens = system_base_chars // 4
        memory_tokens = memory_chars // 4
        return {
            "estimated_tokens": estimated_tokens,
            "system_base_tokens": system_base_tokens,
            "memory_tokens": memory_tokens,
            "system_tokens": system_base_tokens + memory_tokens,
            "tools_tokens": tools_tokens,
            "tools_breakdown": breakdown,
            "conversation_tokens": conversation_chars // 4,
            "reasoning_tokens": reasoning,
            "draft_tokens": draft_chars // 4 if draft else 0,
            "context_limit": limit,
            "remaining_tokens": remaining,
            "usage_percent": usage_percent,
        }

    def build_memory_context_dict(self, user_query: str | None = None) -> dict:
        return {
            "profile": [e.model_dump(mode="json") for e in self.store.load_profile()],
            "preferences": [e.model_dump(mode="json") for e in self.store.load_preferences()],
            "episodes": [
                e.model_dump(mode="json")
                for e in (
                    self.store.search_episodes(user_query, limit=self.persona.memory.max_episodes_in_context)
                    if user_query
                    else self.store.load_episodes()[-self.persona.memory.max_episodes_in_context :]
                )
            ],
        }

    def dump_context(self, user_query: str | None = None) -> str:
        return json.dumps(
            {
                "system_prompt": self.build_system_prompt(user_query=user_query),
                "memory_context": self.build_memory_context_dict(user_query=user_query),
            },
            indent=2,
        )
