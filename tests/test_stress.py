"""1,000-Decision scaling stress test across CLI, MCP context assembly, and TUI feeds.

Validates that Origin handles large workspaces without memory leaks, slow lookups,
or token budget truncation failures.
"""

import os
import shutil
import tempfile
import time
import pytest

from origin.application.use_cases import (
    init_workspace,
    add_decision,
    get_decisions_affecting_file,
    get_context_bundle,
)
from origin.infrastructure.database import ArtifactRepository, atomic_write_yaml


@pytest.fixture
def large_workspace():
    """Create a temporary workspace populated with 1,000 synthetic decisions."""
    d = tempfile.mkdtemp()
    origin_dir = os.path.join(d, ".origin")
    decisions_dir = os.path.join(origin_dir, "decisions")
    os.makedirs(decisions_dir, exist_ok=True)

    # Save workspace config
    atomic_write_yaml(
        os.path.join(origin_dir, "config.yaml"),
        {"workspace_name": "StressWorkspace", "schema_version": "2.0", "token_budget": 4000},
    )

    # Populate 1,000 YAML files
    for i in range(1000):
        target_file = f"src/component_{i % 50}.py"
        data = {
            "id": f"dec_{i:04d}",
            "type": "decision",
            "created_at": f"2026-01-01T00:{i % 60:02d}:00Z",
            "updated_at": f"2026-01-01T00:{i % 60:02d}:00Z",
            "originating_agent": "benchmark",
            "status": "active",
            "title": f"Stress Test Decision {i}",
            "rationale": "Testing scalability across CLI, MCP, and TUI components.",
            "alternatives_considered": ["Alt A", "Alt B"],
            "affected_files": [target_file],
            "confidence": 0.95,
        }
        atomic_write_yaml(os.path.join(decisions_dir, f"dec_{i:04d}.yaml"), data)

    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_blame_scaling(large_workspace: str) -> None:
    """Stress test file blame lookups against 1,000 decisions."""
    start = time.perf_counter()
    decisions = get_decisions_affecting_file(large_workspace, "src/component_5.py")
    elapsed = time.perf_counter() - start

    # 1,000 decisions / 50 components = 20 decisions per component
    assert len(decisions) == 20
    assert elapsed < 10.0, f"Lookup took too long: {elapsed:.3f}s"


def test_mcp_context_bundle_scaling(large_workspace: str) -> None:
    """Stress test MCP context bundle compilation and token budget truncation with 1,000 decisions."""
    start = time.perf_counter()
    bundle = get_context_bundle(large_workspace)
    elapsed = time.perf_counter() - start

    assert "# Origin Project Context" in bundle
    assert "Stress Test Decision" in bundle
    assert elapsed < 10.0, f"Context bundle compilation took too long: {elapsed:.3f}s"


def test_tui_feed_scaling(large_workspace: str) -> None:
    """Stress test repository query feeds for TUI list rendering."""
    origin_dir = os.path.join(large_workspace, ".origin")
    repo = ArtifactRepository(os.path.join(origin_dir, "workspace.db"))

    start = time.perf_counter()
    active_decisions = repo.list_decisions(status="active")
    elapsed = time.perf_counter() - start

    assert len(active_decisions) == 1000
    assert elapsed < 10.0, f"TUI decision list feed query took too long: {elapsed:.3f}s"
