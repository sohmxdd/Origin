"""Tests for the application use cases."""

import os
from typing import Any
import pytest

from origin.exceptions import (
    DecisionNotActiveError,
    DecisionNotFoundError,
    InvalidArtifactError,
    WorkspaceAlreadyInitializedError,
)
from origin.application.use_cases import (
    init_workspace,
    add_decision,
    supersede_decision,
    set_memory,
    get_memory,
    search_artifacts,
    get_context_bundle,
)


@pytest.fixture
def clean_root(tmp_path: Any) -> str:
    """Fixture returning an empty directory path for testing use cases."""
    return str(tmp_path)


def test_init_workspace_creates_files(clean_root: str) -> None:
    """Verify init_workspace correctly scaffolds the workspace directory structure."""
    init_workspace(clean_root, "TestApp", with_hooks=False)

    origin_dir = os.path.join(clean_root, ".origin")
    assert os.path.isdir(origin_dir)
    assert os.path.exists(os.path.join(origin_dir, "config.yaml"))
    assert os.path.exists(os.path.join(origin_dir, "workspace.db"))
    assert os.path.exists(os.path.join(origin_dir, "decisions.md"))
    assert os.path.exists(os.path.join(origin_dir, "memory.md"))
    assert os.path.exists(os.path.join(origin_dir, "ORIGIN.md"))


def test_init_workspace_already_initialized(clean_root: str) -> None:
    """Verify init_workspace throws error when initialized twice."""
    init_workspace(clean_root, "TestApp", with_hooks=False)
    with pytest.raises(WorkspaceAlreadyInitializedError):
        init_workspace(clean_root, "TestApp", with_hooks=False)


def test_add_decision_flow(clean_root: str) -> None:
    """Verify add_decision adds records and triggers timeline events and mirrors."""
    init_workspace(clean_root, "TestApp", with_hooks=False)

    dec = add_decision(
        workspace_root=clean_root,
        title="Use SQLite",
        rationale="Embedded database is enough",
        alternatives_considered=["Postgres", "JSON files"],
        affected_files=["src/db.py"],
        confidence=0.9,
        originating_agent="human",
    )

    assert dec.id.startswith("dec_")
    assert dec.title == "Use SQLite"

    # Verify mirrors are refreshed
    decisions_md_path = os.path.join(clean_root, ".origin", "decisions.md")
    with open(decisions_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Use SQLite" in content
    assert dec.id in content


def test_supersede_decision_flow(clean_root: str) -> None:
    """Verify supersede_decision transitions status and links old/new decisions."""
    init_workspace(clean_root, "TestApp", with_hooks=False)

    # 1. Create first decision
    dec1 = add_decision(clean_root, "D1", "R1", [], [], 0.8, "human")

    # 2. Supersede first decision
    dec2 = supersede_decision(
        workspace_root=clean_root,
        old_decision_id=dec1.id,
        title="D2",
        rationale="R2 supersedes R1",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.9,
        originating_agent="claude-code",
    )

    assert dec2.id.startswith("dec_")
    assert dec2.title == "D2"

    # Verify mirrors are refreshed and contain correct statuses
    decisions_md_path = os.path.join(clean_root, ".origin", "decisions.md")
    with open(decisions_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    # The mirror only lists ACTIVE decisions in its index/details
    assert "D2" in content
    assert "D1" not in content  # because D1 is now superseded, not active

    # Test error cases
    with pytest.raises(DecisionNotFoundError):
        supersede_decision(clean_root, "dec_nonexistent", "D3", "R3", [], [], 0.9, "human")

    with pytest.raises(DecisionNotActiveError):
        supersede_decision(clean_root, dec1.id, "D3", "R3", [], [], 0.9, "human")


def test_memory_set_and_get(clean_root: str) -> None:
    """Verify setting memory entries works and error out on invalid category."""
    init_workspace(clean_root, "TestApp", with_hooks=False)

    # Set new memory
    mem1 = set_memory(clean_root, "tech_stack", "backend", "fastapi", "human")
    assert mem1.key == "backend"
    assert mem1.value == "fastapi"

    # Retrieve
    retrieved = get_memory(clean_root, "tech_stack", "backend")
    assert retrieved is not None
    assert retrieved.value == "fastapi"

    # Update value
    mem2 = set_memory(clean_root, "tech_stack", "backend", "django", "human")
    assert mem2.id == mem1.id
    assert mem2.value == "django"

    # Invalid category
    with pytest.raises(InvalidArtifactError):
        set_memory(clean_root, "invalid_cat", "key", "val", "human")


def test_search_and_context_bundle(clean_root: str) -> None:
    """Verify search and context retrieval work correctly."""
    init_workspace(clean_root, "TestApp", with_hooks=False)

    add_decision(clean_root, "Use Pytest", "For unit testing", [], [], 1.0, "human")
    set_memory(clean_root, "convention", "testing_framework", "pytest", "human")

    # Search
    results = search_artifacts(clean_root, "Pytest")
    assert len(results) == 2

    # Context bundle
    bundle = get_context_bundle(clean_root)
    assert "**Workspace Name:** TestApp" in bundle
    assert "Use Pytest" in bundle
    assert "testing_framework" in bundle
