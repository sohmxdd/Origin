"""Unit tests for get_decisions_affecting_file and path normalization."""

import os
import pytest
from datetime import datetime, timezone
from origin.exceptions import OriginError
from origin.application.use_cases import init_workspace, add_decision, supersede_decision, get_decisions_affecting_file
from origin.infrastructure.database import ArtifactRepository


def test_blame_path_normalization_and_history(tmp_path):
    """Verify that blame queries successfully canonicalize different file path styles and return chronological trace."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "BlameTest", with_hooks=False)

    # 1. Add oldest decision affecting src/db.py
    dec1 = add_decision(
        workspace_root=workspace_root,
        title="SQL database",
        rationale="Old database layer config",
        alternatives_considered=["JSON"],
        affected_files=["src/db.py"],
        confidence=1.0,
        originating_agent="human",
    )

    # 2. Supersede oldest decision with a new active decision affecting src/db.py
    dec2 = supersede_decision(
        workspace_root=workspace_root,
        old_decision_id=dec1.id,
        title="PostgreSQL database",
        rationale="Upgrade scaling capabilities",
        alternatives_considered=["SQLite"],
        affected_files=["src/db.py"],
        confidence=0.9,
        originating_agent="human",
    )

    # 3. Add proposed decision affecting src/db.py (latest)
    dec3 = add_decision(
        workspace_root=workspace_root,
        title="Proposed Redis cache",
        rationale="Add cache to DB helper",
        alternatives_considered=["In-Memory"],
        affected_files=["src/db.py"],
        confidence=0.8,
        originating_agent="human",
        status="proposed",
    )

    # Query blame history using different path formats
    # Format A: Canonical relative path
    history_a = get_decisions_affecting_file(workspace_root, "src/db.py")
    assert len(history_a) == 3
    assert [d.id for d in history_a] == [dec1.id, dec2.id, dec3.id]
    assert history_a[0].status == "superseded"
    assert history_a[0].superseded_by == dec2.id
    assert history_a[1].status == "active"
    assert history_a[2].status == "proposed"

    # Format B: Windows backslash separator
    history_b = get_decisions_affecting_file(workspace_root, "src\\db.py")
    assert len(history_b) == 3
    assert [d.id for d in history_b] == [dec1.id, dec2.id, dec3.id]

    # Format C: Absolute path
    abs_path = os.path.abspath(os.path.join(workspace_root, "src/db.py"))
    history_c = get_decisions_affecting_file(workspace_root, abs_path)
    assert len(history_c) == 3
    assert [d.id for d in history_c] == [dec1.id, dec2.id, dec3.id]

    # Format D: Relative path with leading/trailing dots/slashes
    history_d = get_decisions_affecting_file(workspace_root, "./src/db.py")
    assert len(history_d) == 3
    assert [d.id for d in history_d] == [dec1.id, dec2.id, dec3.id]

    # Check non-matching file
    history_none = get_decisions_affecting_file(workspace_root, "src/other.py")
    assert len(history_none) == 0
