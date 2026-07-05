"""Build inference context from persona + memory."""

from __future__ import annotations

import json

from shadow_pa.config import PersonaConfig
from shadow_pa.memory.store import MemoryStore


class ContextBuilder:
    def __init__(self, store: MemoryStore, persona: PersonaConfig) -> None:
        self.store = store
        self.persona = persona

    def build_system_prompt(self, user_query: str | None = None) -> str:
        parts: list[str] = [
            "You are a personal assistant shadowing the user.",
            "Use ONLY facts from the memory sections below.",
            "If information is missing, ask — do not invent facts about the user.",
        ]

        identity = self.persona.identity
        if identity:
            parts.append("\n[IDENTITY]")
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
