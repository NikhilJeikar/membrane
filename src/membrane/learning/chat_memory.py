"""Suggest profile/preference memory from a single chat turn."""

from __future__ import annotations

import json

from membrane.config import PersonaConfig
from membrane.llm.ollama import OllamaClient, OllamaError
from membrane.memory.models import MemoryCategory, MemoryProposal, MemorySource
from membrane.memory.review import _existing_memory_note
from membrane.memory.store import MemoryStore
from membrane.shadow.extractor import EXTRACTION_SYSTEM, ShadowExtractor

_TURN_EXTRACTION_USER = """The SELF user is: {self_names}.

From this chat exchange, extract profile facts and communication preferences about SELF that would help personalize future assistance.
Prefer inclusion over omission: capture goals, working style, recurring themes, and durable preferences when there is reasonable evidence — not only rigid "stable" facts.
Skip pure small talk with no lasting signal, but when a turn reveals something useful, include it rather than returning empty arrays.
Do not extract episodes.

Return JSON:
{{
  "profiles": [{{"key": "snake_case", "value": "...", "confidence": 0.0-1.0, "evidence": ["quote"]}}],
  "preferences": [{{"key": "snake_case", "value": "...", "strength": 0.0-1.0, "evidence": ["quote"]}}]
}}

USER: {user_message}
ASSISTANT: {assistant_reply}
"""


def suggest_memory_from_turn(
    store: MemoryStore,
    persona: PersonaConfig,
    user_message: str,
    assistant_reply: str,
    *,
    client: OllamaClient | None = None,
    max_suggestions: int = 4,
) -> list[MemoryProposal]:
    """Return profile/preference proposals for one chat turn (not yet saved)."""
    if not (persona.memory.use_profile or persona.memory.use_preferences):
        return []
    user_message = user_message.strip()
    assistant_reply = assistant_reply.strip()
    if not user_message or not assistant_reply:
        return []

    extractor = ShadowExtractor(store, persona, client=client)
    prompt = _TURN_EXTRACTION_USER.format(
        self_names=", ".join(persona.self_names) or "the user",
        user_message=user_message[:4000],
        assistant_reply=assistant_reply[:4000],
    )
    try:
        raw = extractor.client.chat(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            model=persona.llm.extractor_model,
            temperature=0.2,
            json_mode=True,
        )
    except OllamaError:
        return []

    try:
        data = extractor.client.parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        return []

    proposals = extractor._data_to_proposals(data, source=MemorySource.CHAT)
    filtered: list[MemoryProposal] = []
    for proposal in proposals:
        if proposal.category not in (MemoryCategory.PROFILE, MemoryCategory.PREFERENCE):
            continue
        if proposal.category == MemoryCategory.PROFILE and not persona.memory.use_profile:
            continue
        if proposal.category == MemoryCategory.PREFERENCE and not persona.memory.use_preferences:
            continue
        note = _existing_memory_note(store, proposal)
        if note and "same value" in note.lower():
            continue
        filtered.append(proposal)
        if len(filtered) >= max_suggestions:
            break
    return filtered
