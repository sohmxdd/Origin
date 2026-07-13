"""Visual regression tests for the Origin TUI v2 using pytest-textual-snapshot.

Captures all views in both empty and populated states, plus overlays.
Uses FrozenOriginTUI to freeze times, IDs, and branch names for determinism.
"""

import os
import shutil
import re
from datetime import datetime, timezone
from unittest.mock import patch
import pytest

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
            e.created_at = fixed_dt
            e.updated_at = fixed_dt
            
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


# ── Overview View Snapshots ────────────────────────────────
def test_overview_empty_snapshot(snap_compare):
    """Capture the Overview dashboard in its empty state."""
    workspace_root = get_static_test_workspace("overview_empty")
    init_workspace(workspace_root, "EmptyWS", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app)


def test_overview_populated_snapshot(snap_compare):
    """Capture the Overview dashboard in its populated state."""
    workspace_root = get_static_test_workspace("overview_populated")
    init_workspace(workspace_root, "PopulatedWS", with_hooks=False)
    
    add_decision(workspace_root, "Database setup", "Postgres rationale", [], [], 0.9, "agent", "proposed")
    set_memory(workspace_root, "tech_stack", "db", "postgres", "human")

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app)


# ── Context View Snapshots ─────────────────────────────────
def test_context_empty_snapshot(snap_compare):
    """Capture the Context view in empty state."""
    workspace_root = get_static_test_workspace("context_empty")
    init_workspace(workspace_root, "EmptyWS", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab",))


def test_context_populated_snapshot(snap_compare):
    """Capture the Context view in populated state."""
    workspace_root = get_static_test_workspace("context_populated")
    init_workspace(workspace_root, "PopulatedWS", with_hooks=False)
    
    add_decision(workspace_root, "Database setup", "Postgres rationale", [], [], 0.9, "agent", "active")
    set_memory(workspace_root, "tech_stack", "db", "postgres", "human")

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab",))


# ── Decisions View Snapshots ───────────────────────────────
def test_decisions_empty_snapshot(snap_compare):
    """Capture Decisions view in empty state."""
    workspace_root = get_static_test_workspace("dec_empty")
    init_workspace(workspace_root, "EmptyWS", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab", "tab"))


def test_decisions_populated_snapshot(snap_compare):
    """Capture Decisions view in populated state."""
    workspace_root = get_static_test_workspace("dec_populated")
    init_workspace(workspace_root, "PopulatedWS", with_hooks=False)
    
    add_decision(workspace_root, "Redis caching", "Cache rationale", ["Memcached"], ["src/cache.py"], 0.8, "agent", "proposed")
    add_decision(workspace_root, "Database setup", "Postgres rationale", [], [], 0.9, "human", "active")

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab", "tab"))


# ── Knowledge View Snapshots ───────────────────────────────
def test_knowledge_empty_snapshot(snap_compare):
    """Capture Knowledge view in empty state."""
    workspace_root = get_static_test_workspace("know_empty")
    init_workspace(workspace_root, "EmptyWS", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab", "tab", "tab"))


def test_knowledge_populated_snapshot(snap_compare):
    """Capture Knowledge view in populated state."""
    workspace_root = get_static_test_workspace("know_populated")
    init_workspace(workspace_root, "PopulatedWS", with_hooks=False)
    
    set_memory(workspace_root, "tech_stack", "db", "postgres", "human")
    set_memory(workspace_root, "convention", "linter", "ruff", "agent")

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab", "tab", "tab"))


# ── Timeline View Snapshots ────────────────────────────────
def test_timeline_empty_snapshot(snap_compare):
    """Capture Timeline view in empty state."""
    workspace_root = get_static_test_workspace("time_empty")
    init_workspace(workspace_root, "EmptyWS", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab", "tab", "tab", "tab"))


def test_timeline_populated_snapshot(snap_compare):
    """Capture Timeline view in populated state."""
    workspace_root = get_static_test_workspace("time_populated")
    init_workspace(workspace_root, "PopulatedWS", with_hooks=False)
    
    add_decision(workspace_root, "Database setup", "Postgres rationale", [], [], 0.9, "human", "active")

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("tab", "tab", "tab", "tab"))


# ── Overlay Snapshots ──────────────────────────────────────
def test_command_palette_overlay_snapshot(snap_compare):
    """Capture the Command Palette overlay."""
    workspace_root = get_static_test_workspace("palette")
    init_workspace(workspace_root, "PopulatedWS", with_hooks=False)

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("ctrl+k",))


def test_search_overlay_snapshot(snap_compare):
    """Capture the Search overlay with typed input."""
    workspace_root = get_static_test_workspace("search")
    init_workspace(workspace_root, "PopulatedWS", with_hooks=False)
    
    add_decision(workspace_root, "Database setup", "Postgres rationale", [], [], 0.9, "human", "active")

    with patch("origin.presentation.tui.GitHelper.get_current_branch", return_value="main"):
        app = FrozenOriginTUI(workspace_root=workspace_root, show_splash=False)
        assert snap_compare(app, press=("slash", "D", "a", "t", "a"))
