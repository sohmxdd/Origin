"""Visual regression tests for the Origin TUI using pytest-textual-snapshot.

Captures the boot splash screen, the empty dashboard state, and
a populated dashboard state with frozen timestamps and git branch.
"""

import os
import shutil
import re
from datetime import datetime, timezone
from unittest.mock import patch
from origin.presentation.tui import OriginTUI
from origin.application.use_cases import init_workspace, add_decision, set_memory


class FrozenOriginTUI(OriginTUI):
    """A version of OriginTUI with frozen timestamps and IDs for visual snapshot testing."""

    CSS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/origin/presentation/theme.tcss"))

    def _load_all_data(self) -> None:
        super()._load_all_data()
        fixed_dt = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
        
        # Sort deterministically by title first to assign stable indices
        self._all_decisions.sort(key=lambda d: d.title)
        
        for i, d in enumerate(self._all_decisions):
            d.id = f"dec_test_id_{i}"
            d.created_at = fixed_dt
            d.updated_at = fixed_dt
            if d.superseded_by:
                d.superseded_by = "dec_test_id_superseded"
                
        # Set self._decisions with sorted list
        self._all_decisions.sort(key=lambda d: d.id, reverse=True)
        self._decisions = list(self._all_decisions)
        
        for i, e in enumerate(self._memories):
            e.id = f"mem_test_id_{i}"
            
        # Sort timeline deterministically by summary first
        self._timeline.sort(key=lambda e: e.summary)
        for i, e in enumerate(self._timeline):
            e.id = f"evt_test_id_{i}"
            e.created_at = fixed_dt
            # Normalize dynamic ULID hashes in event summaries
            e.summary = re.sub(r'dec_[a-zA-Z0-9]+', 'dec_test_id_X', e.summary)
            
        self._timeline.sort(key=lambda e: e.id, reverse=True)


def get_static_test_workspace(name: str) -> str:
    """Create or reset a static test workspace directory inside the project."""
    workspace_root = os.path.abspath(f"tmp_snapshot_{name}")
    if os.path.exists(workspace_root):
        shutil.rmtree(workspace_root, ignore_errors=True)
    os.makedirs(workspace_root, exist_ok=True)
    return workspace_root


def test_boot_screen_snapshot(snap_compare):
    """Capture the concentric ring pixel-art black hole splash screen."""
    workspace_root = get_static_test_workspace("boot")
    init_workspace(workspace_root, "SplashTest", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=True)
        assert snap_compare(app)


def test_empty_dashboard_snapshot(snap_compare):
    """Capture the dashboard layout in its empty state (no decisions/memory)."""
    workspace_root = get_static_test_workspace("empty")
    init_workspace(workspace_root, "EmptyTest", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app)


def test_populated_dashboard_snapshot(snap_compare):
    """Capture the dashboard layout with decisions, memory, and timeline events."""
    workspace_root = get_static_test_workspace("populated")
    init_workspace(workspace_root, "PopulatedTest", with_hooks=False)

    # Seed test data manually so it has a static path
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
    set_memory(workspace_root, "tech_stack", "framework", "fastapi", "human")

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app)
