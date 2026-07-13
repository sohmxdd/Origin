"""Tests for the SQLite artifact repository."""

import os
import sqlite3
from typing import Any
import pytest
from origin.domain.models import Decision, MemoryEntry, TimelineEvent
from origin.infrastructure.database import ArtifactRepository


@pytest.fixture
def temp_db(tmp_path: Any) -> str:
    """Fixture that returns a temporary database file path."""
    db_file = tmp_path / "workspace.db"
    return str(db_file)


def test_db_initialization_and_wal(temp_db: str) -> None:
    """Verify tables are created and WAL mode is active."""
    repo = ArtifactRepository(temp_db)
    assert os.path.exists(temp_db)

    # Directly check journal_mode
    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_save_and_get_decision(temp_db: str) -> None:
    """Test saving and loading a Decision including list serialization."""
    repo = ArtifactRepository(temp_db)
    dec = Decision.create(
        title="Choose Postgres",
        rationale="Needs relational logic",
        alternatives_considered=["MongoDB", "MySQL"],
        affected_files=["db.py", "models.py"],
        confidence=0.9,
        originating_agent="claude-code",
    )
    repo.save(dec)

    retrieved = repo.get(dec.id)
    assert retrieved is not None
    assert isinstance(retrieved, Decision)
    assert retrieved.id == dec.id
    assert retrieved.title == "Choose Postgres"
    assert retrieved.alternatives_considered == ["MongoDB", "MySQL"]
    assert retrieved.affected_files == ["db.py", "models.py"]
    assert retrieved.confidence == 0.9
    assert retrieved.originating_agent == "claude-code"


def test_save_and_get_memory_entry(temp_db: str) -> None:
    """Test memory entry creation and get_memory_entry utility."""
    repo = ArtifactRepository(temp_db)
    entry = MemoryEntry.create(
        category="tech_stack",
        key="primary_db",
        value="postgresql",
        originating_agent="human",
    )
    repo.save(entry)

    # Test generic get
    retrieved = repo.get(entry.id)
    assert retrieved is not None
    assert isinstance(retrieved, MemoryEntry)
    assert retrieved.key == "primary_db"
    assert retrieved.value == "postgresql"

    # Test get_memory_entry
    mem = repo.get_memory_entry("tech_stack", "primary_db")
    assert mem is not None
    assert mem.id == entry.id
    assert mem.value == "postgresql"

    # Test get_memory_entry missing
    assert repo.get_memory_entry("tech_stack", "secondary_db") is None


def test_update_status(temp_db: str) -> None:
    """Test status update and supersession pointer linking."""
    repo = ArtifactRepository(temp_db)
    dec = Decision.create(
        title="Use Postgres",
        rationale="Relational structure",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.8,
        originating_agent="human",
    )
    repo.save(dec)

    repo.update_status(dec.id, status="superseded", superseded_by="dec_999")
    updated = repo.get(dec.id)
    assert updated is not None
    assert updated.status == "superseded"
    assert updated.superseded_by == "dec_999"


def test_list_methods(temp_db: str) -> None:
    """Verify lists of decisions, memory, and timeline events return correctly."""
    repo = ArtifactRepository(temp_db)

    dec1 = Decision.create("D1", "R1", [], [], 0.5, "agent")
    dec2 = Decision.create("D2", "R2", [], [], 0.6, "agent")
    repo.save(dec1)
    repo.save(dec2)

    mem1 = MemoryEntry.create("architecture", "pattern", "clean", "agent")
    repo.save(mem1)

    evt1 = TimelineEvent.create("decision_created", "Created dec1", "agent", dec1.id)
    repo.save(evt1)

    # Assert lists
    decisions = repo.list_decisions()
    assert len(decisions) == 2
    assert decisions[0].title == "D1"

    active_decisions = repo.list_decisions(status="active")
    assert len(active_decisions) == 2

    # Supersede one
    repo.update_status(dec1.id, "superseded", dec2.id)
    active_decisions = repo.list_decisions(status="active")
    assert len(active_decisions) == 1
    assert active_decisions[0].id == dec2.id

    memories = repo.list_memory()
    assert len(memories) == 1
    assert memories[0].key == "pattern"

    events = repo.list_timeline()
    assert len(events) == 1
    assert events[0].ref_artifact_id == dec1.id


def test_search(temp_db: str) -> None:
    """Verify search finds keywords in title, rationale, key, or value."""
    repo = ArtifactRepository(temp_db)

    dec = Decision.create("Use pgvector", "For embedding storage", [], [], 1.0, "agent")
    mem = MemoryEntry.create("tech_stack", "vector_index", "pgvector extension", "agent")
    repo.save(dec)
    repo.save(mem)

    # Search query
    res = repo.search("pgvector")
    assert len(res) == 2

    # Search specific text
    res = repo.search("embedding")
    assert len(res) == 1
    assert res[0].id == dec.id

    # Search missing
    assert len(repo.search("mongodb")) == 0
