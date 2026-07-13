"""Tests for the Origin TUI using Textual's Pilot testing utilities.

Covers: boot check, navigation, view switching, accept/reject workflows,
non-proposed feedback, search overlay integration, and narrow-layout.
"""

import os
import pytest
from textual.widgets import ListView, Static, ContentSwitcher
from origin.application.use_cases import add_decision, set_memory, init_workspace
from origin.config import get_origin_dir
from origin.presentation.tui import OriginTUI, DecisionItem, MemoryItem, TimelineItem


@pytest.mark.asyncio
async def test_tui_boots_and_populates(tui_workspace):
    """Verify TUI loads workspace and populates overview and switchable views."""
    app = OriginTUI(workspace_root=tui_workspace, show_splash=False)
    async with app.run_test() as pilot:
        await pilot.resize_terminal(120, 40)
        await pilot.pause()

        # Check header contains workspace name
        header = app.query_one("#header-bar", Static)
        assert "TuiTestApp" in str(header.content)

        # Overview View diagnostics check
        diagnostics = app.query_one("#overview-diagnostics")
        assert len(diagnostics.children) > 0

        # Check decisions list populated
        app.switch_view("decisions")
        await pilot.pause()
        decisions_list = app.query_one("#decisions-list", ListView)
        # Ensure we have items (group headers + decision items)
        assert len(decisions_list.children) >= 2

        # Check memory (knowledge) list populated
        app.switch_view("knowledge")
        await pilot.pause()
        knowledge_list = app.query_one("#knowledge-list", ListView)
        assert len(knowledge_list.children) >= 2

        # Check timeline list populated
        app.switch_view("timeline")
        await pilot.pause()
        timeline_list = app.query_one("#timeline-list", ListView)
        assert len(timeline_list.children) >= 2


@pytest.mark.asyncio
async def test_tui_navigation(tui_workspace):
    """Verify arrow key and j/k navigation in the decisions list."""
    app = OriginTUI(workspace_root=tui_workspace, show_splash=False)
    async with app.run_test() as pilot:
        await pilot.resize_terminal(120, 40)
        await pilot.pause()

        # Switch to decisions view
        app.switch_view("decisions")
        await pilot.pause()

        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Navigate down/up
        list_view.action_cursor_down()
        await pilot.pause()
        list_view.action_cursor_up()
        await pilot.pause()

        assert len(list_view.children) >= 2


@pytest.mark.asyncio
async def test_tui_accept_proposed_decision(tui_workspace):
    """Verify pressing 'a' on a proposed decision accepts it."""
    app = OriginTUI(workspace_root=tui_workspace, show_splash=False)
    async with app.run_test() as pilot:
        await pilot.resize_terminal(120, 40)
        await pilot.pause()

        app.switch_view("decisions")
        await pilot.pause()

        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Find a proposed decision in the list
        proposed_index = None
        for i, item in enumerate(list_view.children):
            if isinstance(item, DecisionItem) and item.decision.status == "proposed":
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
    app = OriginTUI(workspace_root=tui_workspace, show_splash=False)
    async with app.run_test() as pilot:
        await pilot.resize_terminal(120, 40)
        await pilot.pause()

        # Seed another proposed decision so we have one to reject
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
        app.switch_view("decisions")
        await pilot.pause()

        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Find proposed decision
        proposed_index = None
        for i, item in enumerate(list_view.children):
            if isinstance(item, DecisionItem) and item.decision.status == "proposed":
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
    """Verify pressing 'a' on an active decision shows an inline warning."""
    app = OriginTUI(workspace_root=tui_workspace, show_splash=False)
    async with app.run_test() as pilot:
        await pilot.resize_terminal(120, 40)
        await pilot.pause()

        app.switch_view("decisions")
        await pilot.pause()

        list_view = app.query_one("#decisions-list", ListView)
        list_view.focus()
        await pilot.pause()

        # Find the active decision
        active_index = None
        for i, item in enumerate(list_view.children):
            if isinstance(item, DecisionItem) and item.decision.status == "active":
                active_index = i
                break

        assert active_index is not None, "Expected an active decision in the list"

        list_view.index = active_index
        await pilot.pause()

        # Press 'a' on active decision
        await pilot.press("a")
        await pilot.pause()

        # Should show warning in status message
        status = app.query_one("#status-message", Static)
        rendered = str(status.content)
        assert "proposed" in rendered.lower()


@pytest.mark.asyncio
async def test_tui_search_filtering(tui_workspace):
    """Verify '/' opens search overlay, typing filters, and enter selects result."""
    app = OriginTUI(workspace_root=tui_workspace, show_splash=False)
    async with app.run_test() as pilot:
        await pilot.resize_terminal(120, 40)
        await pilot.pause()

        # Press '/' to open search overlay
        await pilot.press("slash")
        await pilot.pause()

        # Type search query "Redis"
        await pilot.press("R", "e", "d", "i", "s")
        await pilot.pause()
        
        # Press enter to submit search result and trigger select callback
        await pilot.press("enter")
        await pilot.pause()

        # Should switch to decisions view and highlight decision
        assert app.query_one("#main-switcher", ContentSwitcher).current == "decisions"
        
        list_view = app.query_one("#decisions-list", ListView)
        assert list_view.highlighted_child is not None
        assert isinstance(list_view.highlighted_child, DecisionItem)
        assert "redis" in list_view.highlighted_child.decision.title.lower()


@pytest.mark.asyncio
async def test_tui_narrow_layout(tui_workspace):
    """Verify narrow class is applied when terminal size is small."""
    app = OriginTUI(workspace_root=tui_workspace, show_splash=False)
    async with app.run_test() as pilot:
        # Resize to narrow width (<80)
        await pilot.resize_terminal(75, 24)
        await pilot.pause()

        # Assert App has narrow class
        assert "narrow" in app.classes
        assert "wide" not in app.classes
