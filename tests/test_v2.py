"""Unit and integration tests for Origin v2 features.

Validates atomic file write integrity, v1-to-v2 workspace migration,
idempotent git trailer parsing, and proposed/reject workflows.
"""

import os
import shutil
import pytest
from unittest.mock import MagicMock, patch

from origin.domain.models import Decision, MemoryEntry, TimelineEvent
from origin.infrastructure.database import ArtifactRepository, atomic_write_yaml
from origin.config import load_config, save_config, WorkspaceConfig, get_origin_dir
from origin.application.use_cases import (
    add_decision,
    accept_decision,
    reject_decision,
    sync_git_commits,
    migrate_workspace,
)


def test_atomic_write_safety(tmp_path):
    """Verify that a failed/interrupted write does not corrupt or overwrite the original file."""
    file_path = os.path.join(tmp_path, "test.yaml")
    
    # 1. Establish initial valid file contents
    initial_data = {"key": "initial_value"}
    atomic_write_yaml(file_path, initial_data)
    assert os.path.exists(file_path)

    # 2. Trigger an update but mock os.replace to raise an exception simulating write interruption
    updated_data = {"key": "new_corrupt_value"}
    with patch("os.replace", side_effect=IOError("Disk full or process terminated")):
        with pytest.raises(IOError):
            atomic_write_yaml(file_path, updated_data)

    # 3. Verify original file content is completely intact and not overwritten
    with open(file_path, "r", encoding="utf-8") as f:
        import yaml
        content = yaml.safe_load(f)
        assert content == initial_data
        assert content != updated_data


def test_v1_to_v2_migration(tmp_path):
    """Verify migrate_workspace moves v1 SQLite rows to v2 YAML files and updates schema."""
    workspace_root = str(tmp_path)
    origin_dir = get_origin_dir(workspace_root)
    os.makedirs(origin_dir, exist_ok=True)

    # 1. Seed a v1 config
    config = WorkspaceConfig(workspace_name="LegacyApp")
    config.schema_version = "1.0"
    save_config(workspace_root, config)

    # 2. Seed a v1 SQLite table and data manually
    db_path = os.path.join(origin_dir, "workspace.db")
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            originating_agent TEXT NOT NULL,
            status TEXT NOT NULL,
            superseded_by TEXT,
            title TEXT,
            rationale TEXT,
            alternatives_considered TEXT,
            affected_files TEXT,
            confidence REAL,
            category TEXT,
            key TEXT,
            value TEXT,
            event_type TEXT,
            ref_artifact_id TEXT,
            commit_sha TEXT,
            summary TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO artifacts (id, type, created_at, updated_at, originating_agent, status, title, rationale, alternatives_considered, affected_files, confidence)
        VALUES ('dec_123', 'decision', '2026-07-13T12:00:00Z', '2026-07-13T12:00:00Z', 'human', 'active', 'Legacy Title', 'Legacy Rationale', '[]', '[]', 1.0)
        """
    )
    conn.execute(
        """
        INSERT INTO artifacts (id, type, created_at, updated_at, originating_agent, status, category, key, value)
        VALUES ('mem_456', 'memory', '2026-07-13T12:00:00Z', '2026-07-13T12:00:00Z', 'human', 'active', 'tech_stack', 'framework', 'flask')
        """
    )
    conn.commit()
    conn.close()

    # 3. Execute migration
    migrate_workspace(workspace_root)

    # 4. Verify config.yaml schema is bumped
    new_config = load_config(workspace_root)
    assert new_config.schema_version == "2.0"

    # 5. Verify YAML files were created
    dec_file = os.path.join(origin_dir, "decisions", "dec_123.yaml")
    mem_file = os.path.join(origin_dir, "memory", "tech_stack.framework.yaml")
    assert os.path.exists(dec_file)
    assert os.path.exists(mem_file)

    # 6. Verify index is intact and synchronized
    repo = ArtifactRepository(db_path)
    dec = repo.get("dec_123")
    assert isinstance(dec, Decision)
    assert dec.title == "Legacy Title"

    mem = repo.get_memory_entry("tech_stack", "framework")
    assert isinstance(mem, MemoryEntry)
    assert mem.value == "flask"


def test_sync_git_commits_idempotency(tmp_path):
    """Verify that sync_git_commits runs idempotently and doesn't duplicate events."""
    workspace_root = str(tmp_path)
    origin_dir = get_origin_dir(workspace_root)
    os.makedirs(origin_dir, exist_ok=True)

    # Seed v2 config and repository
    config = WorkspaceConfig(workspace_name="GitApp")
    config.schema_version = "2.0"
    save_config(workspace_root, config)
    db_path = os.path.join(origin_dir, "workspace.db")
    repo = ArtifactRepository(db_path)

    # Seed a decision
    dec = Decision.create("Test Decision", "Rationale", [], [], 1.0, "human")
    repo.save(dec)

    # Mock GitHelper to return commits containing trailers
    mock_commits = [
        {
            "sha": "abcdef1234567890abcdef1234567890abcdef12",
            "subject": "commit with trailer",
            "decision_ids": [dec.id],
        }
    ]

    with patch("origin.application.use_cases.GitHelper") as MockGitHelper:
        mock_git = MagicMock()
        mock_git.get_commits_with_trailer.return_value = mock_commits
        MockGitHelper.return_value = mock_git

        # Run sync first time
        sync_git_commits(workspace_root)
        timeline_1 = repo.list_timeline()
        # Verify one commit event was created
        commit_events_1 = [e for e in timeline_1 if e.event_type == "commit"]
        assert len(commit_events_1) == 1
        assert commit_events_1[0].commit_sha == "abcdef1234567890abcdef1234567890abcdef12"

        # Run sync second time
        sync_git_commits(workspace_root)
        timeline_2 = repo.list_timeline()
        commit_events_2 = [e for e in timeline_2 if e.event_type == "commit"]
        # Verify no duplicate commit event was added
        assert len(commit_events_2) == 1


def test_proposed_decision_workflow(tmp_path):
    """Verify proposed decision addition, rejection, and acceptance transitions."""
    workspace_root = str(tmp_path)
    origin_dir = get_origin_dir(workspace_root)
    os.makedirs(origin_dir, exist_ok=True)

    config = WorkspaceConfig(workspace_name="WorkflowApp")
    config.schema_version = "2.0"
    save_config(workspace_root, config)
    db_path = os.path.join(origin_dir, "workspace.db")
    repo = ArtifactRepository(db_path)

    # 1. Add proposed decision
    dec_proposed = add_decision(
        workspace_root=workspace_root,
        title="Proposed Choice",
        rationale="Why not?",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.8,
        originating_agent="agent",
        status="proposed",
    )
    assert dec_proposed.status == "proposed"

    # Verify proposed decision is not returned by list_decisions("active")
    assert len(repo.list_decisions("active")) == 0
    assert len(repo.list_decisions("proposed")) == 1

    # 2. Reject proposed decision
    reject_decision(workspace_root, dec_proposed.id, agent="human")
    dec_rejected = repo.get(dec_proposed.id)
    assert dec_rejected.status == "rejected"
    assert len(repo.list_decisions("proposed")) == 0
    assert len(repo.list_decisions("rejected")) == 1

    # 3. Add another proposed decision and accept it
    dec_proposed2 = add_decision(
        workspace_root=workspace_root,
        title="Proposed Choice 2",
        rationale="Better",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.9,
        originating_agent="agent",
        status="proposed",
    )
    accept_decision(workspace_root, dec_proposed2.id, agent="human")
    dec_accepted = repo.get(dec_proposed2.id)
    assert dec_accepted.status == "active"
    assert len(repo.list_decisions("active")) == 1
    assert len(repo.list_decisions("proposed")) == 0
