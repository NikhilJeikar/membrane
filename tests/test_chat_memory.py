"""Tests for post-chat memory suggestions."""

from __future__ import annotations

import json

from membrane.config import PersonaConfig
from membrane.learning.chat_memory import suggest_memory_from_turn
from membrane.memory.models import MemoryCategory, MemorySource, ProfileEntry
from membrane.memory.store import MemoryStore


def test_suggest_memory_from_turn_filters_profile_and_preference(tmp_path):
    store = MemoryStore(tmp_path)
    store.upsert_profile(
        ProfileEntry(key="location", value="India", source=MemorySource.MANUAL)
    )

    class FakeClient:
        def chat(self, messages, **_kwargs):
            return json.dumps(
                {
                    "profiles": [
                        {
                            "key": "location",
                            "value": "India",
                            "confidence": 0.9,
                            "evidence": ["I live in India"],
                        },
                        {
                            "key": "occupation",
                            "value": "engineer",
                            "confidence": 0.8,
                            "evidence": ["I work as an engineer"],
                        },
                    ],
                    "preferences": [
                        {
                            "key": "response_style",
                            "value": "concise",
                            "strength": 0.7,
                            "evidence": ["keep it short"],
                        }
                    ],
                    "episodes": [{"summary": "should be skipped", "tags": ["x"]}],
                }
            )

        def parse_json_response(self, text):
            return json.loads(text)

    proposals = suggest_memory_from_turn(
        store,
        PersonaConfig(),
        "I live in India and work as an engineer. Keep it short.",
        "Got it.",
        client=FakeClient(),
    )
    assert len(proposals) == 2
    categories = {p.category for p in proposals}
    assert MemoryCategory.PROFILE in categories
    assert MemoryCategory.PREFERENCE in categories
    assert all(p.category != MemoryCategory.EPISODE for p in proposals)
    assert not any(p.profile and p.profile.key == "location" for p in proposals)
