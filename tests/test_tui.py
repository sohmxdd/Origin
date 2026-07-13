"""Tests for the Origin TUI using Textual's Pilot testing utilities.

Covers: boot check, navigation, accept/reject workflows,
non-proposed feedback, and search filtering.
"""

import os
import pytest
from textual.widgets import ListView, Static

from origin.application.use_cases import add_decision, set_memory, init_workspace
from origin.config import get_origin_dir
from origin.presentation.tui import OriginTUI


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


@pytest.mark.asyncio
async def test_tui_boots_and_populates(tui_workspace):
    """Verify TUI loads workspace and populates decisions, memory, and timeline widgets."""
    app = OriginTUI(workspace_root=tui_workspace)
    async with app.run_test() as pilot:
        # Check header contains workspace name
        header = app.query_one("#header-bar", Static)
        assert "TuiTestApp" in str(header.content)

        # Check decisions list is populated
        list_view = app.query_one("#decisions-list", ListView)
        assert len(list_view.children) >= 2  # At least our 2 seeded decisions

        # Check memory content is populated
        memory_content = app.query_one("#memory-content")
        assert len(memory_content.children) > 0

        # Check timeline content is populated
        timeline_content = app.query_one("#timeline-content")
        assert len(timeline_content.children) > 0


@pytest.mark.asyncio
async def test_tui_navigation(tui_workspace):
    """Verify arrow key and j/k navigation in the decisions list."""
    app = OriginTUI(workspace_root=tui_workspace)
    async with app.run_test() as pilot:
        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Navigate down
        await pilot.press("j")
        await pilot.pause()

        # Navigate up
        await pilot.press("k")
        await pilot.pause()

        # The list should still be responsive
        assert len(list_view.children) >= 2


@pytest.mark.asyncio
async def test_tui_accept_proposed_decision(tui_workspace):
    """Verify pressing 'a' on a proposed decision accepts it."""
    app = OriginTUI(workspace_root=tui_workspace)
    async with app.run_test() as pilot:
        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Find the proposed decision in the list
        proposed_index = None
        for i, item in enumerate(list_view.children):
            if hasattr(item, "data") and item.data.status == "proposed":
                proposed_index = i
                break

        assert proposed_index is not None, "Expected a proposed decision in the list"

        # Navigate to it
        list_view.index = proposed_index
        await pilot.pause()

        # Press 'a' to accept
        await pilot.press("a")
        await pilot.pause()

        # Check status message confirms acceptance
        status = app.query_one("#status-message", Static)
        rendered = str(status.content)
        assert "Accepted" in rendered or "accepted" in rendered.lower()


@pytest.mark.asyncio
async def test_tui_reject_proposed_decision(tui_workspace):
    """Verify pressing 'r' on a proposed decision rejects it."""
    app = OriginTUI(workspace_root=tui_workspace)
    async with app.run_test() as pilot:
        # First, add another proposed decision so we have one to reject
        add_decision(
            workspace_root=tui_workspace,
            title="Use Memcached instead",
            rationale="Simpler caching.",
            alternatives_considered=["Redis"],
            affected_files=["src/cache.py"],
            confidence=0.5,
            originating_agent="agent",
            status="proposed",
        )

        # Reload data
        app._load_all_data()
        app._render_all()
        await pilot.pause()

        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Find the proposed decision
        proposed_index = None
        for i, item in enumerate(list_view.children):
            if hasattr(item, "data") and item.data.status == "proposed":
                proposed_index = i
                break

        assert proposed_index is not None, "Expected a proposed decision in the list"

        list_view.index = proposed_index
        await pilot.pause()

        # Press 'r' to reject
        await pilot.press("r")
        await pilot.pause()

        # Check status message confirms rejection
        status = app.query_one("#status-message", Static)
        rendered = str(status.content)
        assert "Rejected" in rendered or "rejected" in rendered.lower()


@pytest.mark.asyncio
async def test_tui_non_proposed_feedback(tui_workspace):
    """Verify pressing 'a' on an active decision shows an inline message."""
    app = OriginTUI(workspace_root=tui_workspace)
    async with app.run_test() as pilot:
        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Find the active decision
        active_index = None
        for i, item in enumerate(list_view.children):
            if hasattr(item, "data") and item.data.status == "active":
                active_index = i
                break

        assert active_index is not None, "Expected an active decision in the list"

        list_view.index = active_index
        await pilot.pause()

        # Press 'a' on active decision
        await pilot.press("a")
        await pilot.pause()

        # Should show "Only proposed decisions can be accepted"
        status = app.query_one("#status-message", Static)
        rendered = str(status.content)
        assert "proposed" in rendered.lower()


@pytest.mark.asyncio
async def test_tui_search_filtering(tui_workspace):
    """Verify '/' opens search and filters the decisions list."""
    app = OriginTUI(workspace_root=tui_workspace)
    async with app.run_test() as pilot:
        # Press '/' to open search
        await pilot.press("slash")
        await pilot.pause()

        # Type search query and submit
        await pilot.press("R", "e", "d", "i", "s")
        await pilot.press("enter")
        await pilot.pause()

        # Check that the decisions list was filtered
        list_view = app.query_one("#decisions-list", ListView)
        # Should show only the Redis decision
        for item in list_view.children:
            if hasattr(item, "data"):
                assert "redis" in item.data.title.lower() or "Redis" in item.data.title
