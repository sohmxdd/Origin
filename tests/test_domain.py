"""Tests for the domain models and ULID generation."""

import time
from datetime import datetime
from origin.domain.models import Decision, MemoryEntry, TimelineEvent
from origin.domain.ulid import generate_ulid, encode_base32


def test_ulid_generation() -> None:
    """Verify that ULIDs are unique, 26 characters, and sort lexicographically."""
    ulid1 = generate_ulid()
    assert len(ulid1) == 26
    assert all(c in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for c in ulid1)

    time.sleep(0.005)  # small pause to ensure clock moves
    ulid2 = generate_ulid()
    assert ulid1 != ulid2
    # Lexicographical sort check (older time timestamp is smaller)
    assert ulid1 < ulid2


def test_base32_encoding() -> None:
    """Verify Crockford Base32 encoding works correctly."""
    # Test zero
    assert encode_base32(0, 5) == "00000"
    # Test simple conversion
    # 31 = 'Z' (last char in Crockford base32 alphabet)
    assert encode_base32(31, 1) == "Z"
    # 32 = '10' (first digit rollover)
    assert encode_base32(32, 2) == "10"


def test_decision_model_creation() -> None:
    """Test creating a Decision model and its schema validation."""
    decision = Decision.create(
        title="Use SQLite",
        rationale="Simple local file",
        alternatives_considered=["JSON", "XML"],
        affected_files=["db.py"],
        confidence=0.95,
        originating_agent="human",
    )
    assert decision.id.startswith("dec_")
    assert len(decision.id) == 30  # "dec_" (4 chars) + ULID (26 chars)
    assert decision.title == "Use SQLite"
    assert decision.alternatives_considered == ["JSON", "XML"]
    assert decision.status == "active"
    assert isinstance(decision.created_at, datetime)
    assert isinstance(decision.updated_at, datetime)


def test_memory_entry_model_creation() -> None:
    """Test creating a MemoryEntry model."""
    entry = MemoryEntry.create(
        category="tech_stack",
        key="db_type",
        value="sqlite",
        originating_agent="claude-code",
    )
    assert entry.id.startswith("mem_")
    assert entry.category == "tech_stack"
    assert entry.key == "db_type"
    assert entry.value == "sqlite"
    assert entry.status == "active"


def test_timeline_event_model_creation() -> None:
    """Test creating a TimelineEvent model."""
    event = TimelineEvent.create(
        event_type="decision_created",
        summary="sqlite chosen",
        ref_artifact_id="dec_123",
        commit_sha="abcdef123",
        originating_agent="codex-cli",
    )
    assert event.id.startswith("evt_")
    assert event.event_type == "decision_created"
    assert event.ref_artifact_id == "dec_123"
    assert event.commit_sha == "abcdef123"
    assert event.summary == "sqlite chosen"
