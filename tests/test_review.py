"""Tests for interactive memory review helpers."""

from shadow_pa.memory.models import (
    MemoryCategory,
    MemoryProposal,
    MemorySource,
    ProfileEntry,
    ProposalStatus,
)
from shadow_pa.memory.review import _existing_memory_note, _proposal_body
from shadow_pa.memory.store import MemoryStore


def test_proposal_body_includes_profile_fields():
    proposal = MemoryProposal(
        category=MemoryCategory.PROFILE,
        source=MemorySource.CURSOR,
        reason="test",
        profile=ProfileEntry(
            key="timezone",
            value="Asia/Kolkata",
            evidence=["from chat"],
        ),
    )
    body = _proposal_body(proposal)
    assert "timezone" in body
    assert "Asia/Kolkata" in body
    assert "from chat" in body


def test_existing_memory_note_detects_key_conflict(tmp_path):
    store = MemoryStore(tmp_path)
    store.upsert_profile(ProfileEntry(key="occupation", value="Engineer"))

    proposal = MemoryProposal(
        category=MemoryCategory.PROFILE,
        profile=ProfileEntry(key="occupation", value="Software engineer"),
    )
    note = _existing_memory_note(store, proposal)
    assert note is not None
    assert "occupation" in note


def test_list_proposed_excludes_rejected(tmp_path):
    store = MemoryStore(tmp_path)
    p1 = MemoryProposal(category=MemoryCategory.PROFILE, profile=ProfileEntry(key="a", value="1"))
    p2 = MemoryProposal(category=MemoryCategory.PROFILE, profile=ProfileEntry(key="b", value="2"))
    store.propose(p1)
    store.propose(p2)
    store.reject(p2.id)

    pending = store.list_proposed(ProposalStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].id == p1.id
