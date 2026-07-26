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


def test_incremental_sync_mid_poll_race(tmp_path) -> None:
    """Test incremental sync resilience when a file's mtime changes right as sync begins."""
    import yaml
    from origin.application.use_cases import init_workspace, add_decision
    from origin.infrastructure.database import atomic_write_yaml

    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "RaceTest", with_hooks=False)
    origin_dir = os.path.join(workspace_root, ".origin")
    repo = ArtifactRepository(os.path.join(origin_dir, "workspace.db"))

    dec = add_decision(
        workspace_root=workspace_root,
        title="Initial Title",
        rationale="Initial Rationale",
        alternatives_considered=[],
        affected_files=["src/main.py"],
        confidence=1.0,
        originating_agent="human",
    )

    # Initial sync
    repo.sync_index()
    initial_stored = repo.get(dec.id)
    assert isinstance(initial_stored, Decision)
    assert initial_stored.title == "Initial Title"

    # Simulate mid-poll modification on disk
    dec_file = os.path.join(origin_dir, "decisions", f"{dec.id}.yaml")
    with open(dec_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["title"] = "Updated Mid-Poll Title"
    atomic_write_yaml(dec_file, data)

    # Re-sync incrementally
    repo.sync_index()
    updated_stored = repo.get(dec.id)
    assert isinstance(updated_stored, Decision)
    assert updated_stored.title == "Updated Mid-Poll Title"


def test_sync_index_file_rename(tmp_path) -> None:
    """Verify incremental sync behavior when a file is manually renamed on disk outside Origin.

    Note: Decision/Memory files are named by immutable ULID (dec_xxx.yaml) and normal CLI/MCP/TUI
    surfaces never rename them. This test explicitly verifies manual disk tampering recovery:
    when a file is renamed externally, sync_index() cleanly purges the old record and indexes
    the content under the new path without creating duplicate/stale entries.
    """
    from origin.application.use_cases import init_workspace, add_decision

    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "RenameTest", with_hooks=False)
    origin_dir = os.path.join(workspace_root, ".origin")
    repo = ArtifactRepository(os.path.join(origin_dir, "workspace.db"))

    dec = add_decision(
        workspace_root=workspace_root,
        title="File to be Renamed",
        rationale="Testing manual file rename recovery",
        alternatives_considered=[],
        affected_files=["src/app.py"],
        confidence=1.0,
        originating_agent="human",
    )
    repo.sync_index()

    old_file = os.path.join(origin_dir, "decisions", f"{dec.id}.yaml")
    new_file = os.path.join(origin_dir, "decisions", f"renamed_{dec.id}.yaml")

    # Manually rename file on disk (external tampering)
    os.rename(old_file, new_file)

    repo.sync_index()
    decisions = repo.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "File to be Renamed"

