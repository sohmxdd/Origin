"""Shared fixtures for Origin tests."""

import pytest
from origin.application.use_cases import add_decision, set_memory, init_workspace


@pytest.fixture
def tui_workspace(tmp_path):
    """Create an initialized Origin workspace with test data."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "TuiTestApp", with_hooks=False)

    # Seed a proposed decision
    add_decision(
        workspace_root=workspace_root,
        title="Use Redis for caching",
        rationale="Fast in-memory key-value store.",
        alternatives_considered=["Memcached"],
        affected_files=["src/cache.py"],
        confidence=0.8,
        originating_agent="agent",
        status="proposed",
    )

    # Seed an active decision
    add_decision(
        workspace_root=workspace_root,
        title="Use PostgreSQL",
        rationale="Relational DB for core data.",
        alternatives_considered=["MySQL"],
        affected_files=["src/db.py"],
        confidence=0.95,
        originating_agent="human",
        status="active",
    )

    # Seed a memory entry
    set_memory(workspace_root, "tech_stack", "framework", "fastapi", "human")

    return workspace_root
