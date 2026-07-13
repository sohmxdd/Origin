"""Origin TUI — Interactive terminal workspace.

A keyboard-first, responsive terminal dashboard featuring a persistent HeaderBar
with custom 8-bit atom logo, a ContentSwitcher main area, and an always-focused
bottom CommandInput bar. Every action delegates to use_cases.py.
"""

import os
import re
from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Optional, Any, Dict, Set
from rich.table import Table

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Input,
    ListItem,
    ListView,
    Static,
    ContentSwitcher,
    Markdown,
)
from textual.timer import Timer

from origin.application import use_cases
from origin.config import get_origin_dir, load_config
from origin.domain.models import Decision, MemoryEntry, TimelineEvent
from origin.infrastructure.database import ArtifactRepository
from origin.infrastructure.git import GitHelper
from origin.adapters.flat_file import export_flat_file


# ── Status and Timeline Glyph Config ───────────────────────
STATUS_GLYPHS = {
    "active": "●",
    "proposed": "◌",
    "rejected": "✕",
    "superseded": "↺",
}

STATUS_STYLES = {
    "active": "bold #00ffd2",
    "proposed": "#005555",
    "rejected": "bold #e25555",
    "superseded": "#444444",
}

TIMELINE_GLYPHS = {
    "decision_created": "◌",
    "decision_accepted": "●",
    "decision_rejected": "✕",
    "decision_superseded": "↺",
    "memory_updated": "◆",
    "commit": "■",
}

# ── Pixel Art Atom Logos (based on reference PNG) ──────────
# 8-bit Atom logo using our cyan HSL color scheme
HEADER_ATOM_LOGO = """
       [#00ffd2]▄██▄[/]    [#00ffd2]▄██▄[/]
     [#00aaaa]▄█▀▀██▀▀██▄[/]
    [#005555]██▀[/]  [#00ffd2]▄██▄[/]  [#005555]▀██[/]
     [#00aaaa]▀█▄▄██▄▄██▀[/]
       [#00ffd2]▀██▀[/]    [#00ffd2]▀██▀[/]
"""

WELCOME_ATOM_LOGO = """
         [#00ffd2]▄▄████▄▄[/]
     [#00ffd2]▄████▀[/]  [#00aaaa]██[/]  [#00ffd2]▀▀██▄[/]
   [#00ffd2]▄██▀▀[/] [#00aaaa]▄██▀▀██▀▀██▄[/] [#00ffd2]████▄[/]
  [#00ffd2]██▀[/]   [#00aaaa]██▀[/]  [#00ffd2]▄████▄[/]  [#00aaaa]▀██[/]   [#00ffd2]▀██[/]
  [#00ffd2]██[/]    [#00aaaa]██[/]   [#00ffd2]██████[/]   [#00aaaa]██[/]    [#00ffd2]██[/]
  [#00ffd2]██▄[/]   [#00aaaa]██▄[/]  [#00ffd2]▀████▀[/]  [#00aaaa]▄██[/]   [#00ffd2]▄██[/]
   [#00ffd2]▀████▄[/] [#00aaaa]▀██▄▄██▄▄██▀[/] [#00ffd2]▀▀██▄[/]
     [#00ffd2]▀▀▀██▄[/]  [#00aaaa]██[/]  [#00ffd2]▄████▀[/]
         [#00ffd2]▀▀████▀▀[/]
"""

SPLASH_ART = WELCOME_ATOM_LOGO + "\n\n       [bold #00ffd2]O R I G I N[/]\n"


# ── Splash Screen ──────────────────────────────────────────
class SplashScreen(Screen):
    """Full-screen splash screen showing the cyan Atom logo."""

    def compose(self) -> ComposeResult:
        yield Static(SPLASH_ART, id="splash-art")

    def on_mount(self) -> None:
        self.set_timer(1.5, self.action_dismiss_splash)

    def on_key(self, event) -> None:
        self.action_dismiss_splash()

    def action_dismiss_splash(self) -> None:
        self.app.pop_screen()


# ── Custom List View Items ─────────────────────────────────
class GroupHeaderItem(ListItem):
    """A list item that acts as a toggleable section header."""

    def __init__(self, title: str, category: str, collapsed: bool = False) -> None:
        super().__init__()
        self.title = title
        self.category = category
        self.collapsed = collapsed

    def compose(self) -> ComposeResult:
        sign = "▸" if self.collapsed else "▾"
        yield Static(f"[bold #00ffd2]{sign} {self.title}[/]", id="header-label", markup=True)

    def update_label(self) -> None:
        sign = "▸" if self.collapsed else "▾"
        self.query_one("#header-label", Static).update(f"[bold #00ffd2]{sign} {self.title}[/]")


class DecisionItem(ListItem):
    """A list item wrapping a Decision."""

    def __init__(self, decision: Decision, category: str) -> None:
        super().__init__()
        self.decision = decision
        self.category = category

    def compose(self) -> ComposeResult:
        dec = self.decision
        glyph = STATUS_GLYPHS.get(dec.status, "?")
        style = STATUS_STYLES.get(dec.status, "")
        short_id = dec.id[:8]
        
        title = dec.title
        if len(title) > 35:
            title = title[:32] + "..."
            
        label_text = f"  [{style}]{glyph}[/]  [{style}]{title}[/]  [dim #444444]{dec.confidence:.2f}  {short_id}[/]"
        if dec.superseded_by:
            label_text += f"\n     [#444444]└─ superseded by {dec.superseded_by[:8]}[/]"
            
        yield Static(label_text, markup=True)


class MemoryItem(ListItem):
    """A list item wrapping a MemoryEntry."""

    def __init__(self, memory: MemoryEntry, category: str) -> None:
        super().__init__()
        self.memory = memory
        self.category = category

    def compose(self) -> ComposeResult:
        mem = self.memory
        key_str = mem.key
        if len(key_str) > 25:
            key_str = key_str[:22] + "..."
        val_str = mem.value
        if len(val_str) > 30:
            val_str = val_str[:27] + "..."
            
        label_text = f"    [#777777]{key_str}[/] = [#c0c0c0]{val_str}[/]"
        yield Static(label_text, markup=True)


class TimelineItem(ListItem):
    """A list item wrapping a TimelineEvent."""

    def __init__(self, event: TimelineEvent, related_decision: Optional[Decision] = None) -> None:
        super().__init__()
        self.event = event
        self.related_decision = related_decision
        self.is_header = False

    def compose(self) -> ComposeResult:
        event = self.event
        time_str = event.created_at.strftime("%H:%M")
        glyph = TIMELINE_GLYPHS.get(event.event_type, "●")
        
        if "rejected" in event.event_type or "rejected" in event.summary.lower():
            color = "#e25555"
        elif "accepted" in event.event_type or "accepted" in event.summary.lower():
            color = "#00ffd2"
        elif "superseded" in event.event_type or "superseded" in event.summary.lower():
            color = "#444444"
        elif "memory" in event.event_type:
            color = "#00ffd2"
        elif "commit" in event.event_type:
            color = "#005555"
        else:
            color = "#444444"

        label = f"  [#444444]{time_str}[/]  [bold {color}]{glyph}[/]  [#c0c0c0]{event.summary}[/]"
        yield Static(label, markup=True)


# ── Shared Inspector Widget ────────────────────────────────
class InspectorPanel(VerticalScroll):
    """Shared, reactive side panel for detail inspector views."""

    def compose(self) -> ComposeResult:
        yield Static("Select an item to inspect", id="inspector-content", markup=True)

    def update_decision(self, dec: Decision) -> None:
        glyph = STATUS_GLYPHS.get(dec.status, "?")
        style = STATUS_STYLES.get(dec.status, "")
        alts = ", ".join(dec.alternatives_considered) if dec.alternatives_considered else "None"
        files = ", ".join(dec.affected_files) if dec.affected_files else "None"
        
        superseded = ""
        if dec.superseded_by:
            superseded = f"\n[bold #444444]Superseded by:[/] [#00ffd2]{dec.superseded_by}[/]"

        content = (
            f"[#777777]Decision details[/]\n"
            f"[bold {style}]{glyph} {dec.title}[/]\n\n"
            f"[bold #444444]ID:[/] [#c0c0c0]{dec.id}[/]\n"
            f"[bold #444444]Status:[/] [#c0c0c0]{dec.status}[/]\n"
            f"[bold #444444]Confidence:[/] [#c0c0c0]{dec.confidence:.2f}[/]\n"
            f"[bold #444444]Agent:[/] [#c0c0c0]{dec.originating_agent}[/]\n"
            f"[bold #444444]Created:[/] [#c0c0c0]{dec.created_at.strftime('%Y-%m-%d %H:%M UTC')}[/]\n"
            f"[bold #444444]Updated:[/] [#c0c0c0]{dec.updated_at.strftime('%Y-%m-%d %H:%M UTC')}[/]"
            f"{superseded}\n\n"
            f"[#777777]Rationale[/]\n[#c0c0c0]{dec.rationale}[/]\n\n"
            f"[#777777]Alternatives considered[/]\n[#c0c0c0]{alts}[/]\n\n"
            f"[#777777]Affected files[/]\n[#c0c0c0]{files}[/]"
        )
        self.query_one("#inspector-content", Static).update(content)

    def update_memory(self, mem: MemoryEntry) -> None:
        content = (
            f"[#777777]Memory details[/]\n"
            f"[bold #00ffd2]{mem.category}.{mem.key}[/]\n\n"
            f"[bold #444444]Value:[/] [#c0c0c0]{mem.value}[/]\n"
            f"[bold #444444]ID:[/] [#c0c0c0]{mem.id}[/]\n"
            f"[bold #444444]Agent:[/] [#c0c0c0]{mem.originating_agent}[/]\n"
            f"[bold #444444]Created:[/] [#c0c0c0]{mem.created_at.strftime('%Y-%m-%d %H:%M UTC')}[/]\n"
            f"[bold #444444]Updated:[/] [#c0c0c0]{mem.updated_at.strftime('%Y-%m-%d %H:%M UTC')}[/]"
        )
        self.query_one("#inspector-content", Static).update(content)

    def update_timeline_event(self, event: TimelineEvent, related_dec: Optional[Decision] = None) -> None:
        content = (
            f"[#777777]Event details[/]\n"
            f"[bold #00ffd2]{event.summary}[/]\n\n"
            f"[bold #444444]Event Type:[/] [#c0c0c0]{event.event_type}[/]\n"
            f"[bold #444444]ID:[/] [#c0c0c0]{event.id}[/]\n"
            f"[bold #444444]Agent:[/] [#c0c0c0]{event.originating_agent}[/]\n"
            f"[bold #444444]Commit SHA:[/] [#c0c0c0]{event.commit_sha or 'None'}[/]\n"
            f"[bold #444444]Time:[/] [#c0c0c0]{event.created_at.strftime('%Y-%m-%d %H:%M UTC')}[/]"
        )
        if related_dec:
            content += f"\n\n[bold #444444]Related Decision Title:[/] [#c0c0c0]{related_dec.title}[/]"
        self.query_one("#inspector-content", Static).update(content)

    def update_empty(self, message: str = "Select an item to inspect") -> None:
        self.query_one("#inspector-content", Static).update(f"[#444444]{message}[/]")


class HeaderBar(Static):
    """The persistent top HeaderBar showing logo and current view status."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._info_text = ""

    @property
    def content(self) -> str:
        return self._info_text

    def update_header(self, ws_name: str, branch: str, health_glyph: str, health_style: str, view_label: str) -> None:
        info_text = (
            f"[bold #00ffd2]● ORIGIN[/]  [#444444]v1.0[/]  "
            f"[#777777]Workspace:[/] [#00ffd2]{ws_name}[/]  "
            f"[#777777]Branch:[/] [#00ffd2]{branch}[/]  "
            f"[#777777]Health:[/] [{health_style}]{health_glyph}[/]"
        )
        view_text = f"[bold #00ffd2]{view_label.upper()}[/]  [#444444]·[/]  [#777777]Unified memory for your agents.[/]"
        self._info_text = info_text

        # Vertical layout on left
        left_layout = f"{info_text}\n\n{view_text}"

        # If narrow, hide the atom logo
        if self.app and self.app.is_narrow:
            self.update(left_layout)
            return

        # Table grid for side-by-side layout
        table = Table.grid(expand=True)
        table.add_column(justify="left", ratio=1)
        table.add_column(justify="right", width=28)
        
        table.add_row(
            left_layout,
            HEADER_ATOM_LOGO.strip("\n")
        )
        self.update(table)


# ── Welcome Screen (Claude Code Style) ──────────────────────
WELCOME_TITLE_MARKUP = """[bold white]Welcome back to[/]
[bold #00ffd2] ▄██▄  ████▄  ██  ▄████  ██  ███ █[/]
[bold #00ffd2]██  ██ ██▄██  ██ ██  ▄▄  ██  █████[/]
[bold #00ffd2] ▀██▀  ██ ▀▄  ██  ▀████  ██  ██ ██[/]"""


class WelcomeCard(Container):
    """Main card widget on Home screen."""

    def compose(self) -> ComposeResult:
        yield Static(WELCOME_TITLE_MARKUP, id="welcome-title", markup=True)
        with Horizontal(id="welcome-content"):
            with Vertical(id="welcome-brand"):
                yield Static(WELCOME_ATOM_LOGO, id="welcome-art", markup=True)
                yield Static("[bold #00ffd2]● ORIGIN[/]", id="welcome-logo", markup=True)
                yield Static("Unified memory for your agent", id="welcome-tagline")
            with Vertical(id="welcome-stats-pane"):
                yield Static(id="welcome-metadata", markup=True)
                yield Static(id="welcome-metrics", markup=True)
                yield Static("[bold #888888]Recent activity[/]", id="welcome-activity-header", markup=True)
                yield Vertical(id="welcome-timeline-feed")

    def update_data(self, workspace_name: str, branch: str, health_glyph: str, health_style: str,
                    proposed_cnt: int, active_cnt: int, memory_cnt: int, timeline: list[TimelineEvent]) -> None:
        metadata = (
            f"[#777777]Workspace:[/] [#00ffd2]{workspace_name}[/]\n"
            f"[#777777]Branch:[/]    [#00ffd2]{branch}[/]\n"
            f"[#777777]Health:[/]    [{health_style}]{health_glyph} ok[/]"
        )
        self.query_one("#welcome-metadata", Static).update(metadata)

        metrics = (
            f"[#777777]Proposed:[/] [bold #00ffd2]{proposed_cnt}[/]\n"
            f"[#777777]Active:[/]   [bold #00ffd2]{active_cnt}[/]\n"
            f"[#777777]Memory:[/]   [bold #00ffd2]{memory_cnt}[/]"
        )
        self.query_one("#welcome-metrics", Static).update(metrics)

        feed = self.query_one("#welcome-timeline-feed", Vertical)
        feed.remove_children()
        if not timeline:
            feed.mount(Static("[#444444]No recent activity.[/]", markup=True))
        else:
            for event in timeline[:3]:
                time_str = event.created_at.strftime("%H:%M")
                glyph = TIMELINE_GLYPHS.get(event.event_type, "●")
                line = f"[#444444]{time_str}[/]  [bold #00ffd2]{glyph}[/]  [#c0c0c0]{event.summary[:30]}[/]"
                feed.mount(Static(line, markup=True))


COMMAND_HINTS = """
  [bold #00ffd2]/decisions[/]     Show all decisions and manage proposals
  [bold #00ffd2]/knowledge[/]     Browse and inspect memory entries
  [bold #00ffd2]/timeline[/]      Chronological event history
  [bold #00ffd2]/context[/]       View the AI context bundle
  [bold #00ffd2]/doctor[/]        Run workspace health diagnostics
  [bold #00ffd2]/export[/]        Write ORIGIN.md flat file
  [bold #00ffd2]/quit[/]          Exit Origin TUI

  Type anything to search across decisions, memory and timeline.
"""


class HomeView(VerticalScroll):
    """The Home Landing Dashboard (Overview)."""

    def compose(self) -> ComposeResult:
        yield WelcomeCard(id="welcome-card")
        yield Static(COMMAND_HINTS, id="command-hints", markup=True)
        yield Static("[bold #888888]System diagnostics[/]", id="diagnostics-header", classes="section-header", markup=True)
        yield VerticalScroll(id="overview-diagnostics", classes="diagnostics-panel")

    def run_doctor_checks(self) -> None:
        """Run system diagnostics inline and render results."""
        diag = self.query_one("#overview-diagnostics", VerticalScroll)
        diag.remove_children()
        
        root = self.app.workspace_root
        origin_dir = os.path.join(root, ".origin")
        
        errors = 0
        warnings = 0
        results = []

        # 1. Config check
        config_path = os.path.join(origin_dir, "config.yaml")
        if not os.path.exists(config_path):
            results.append("[#e25555][FAIL][/] config.yaml is missing.")
            errors += 1
        else:
            try:
                config = load_config(root)
                if config.schema_version != "2.0":
                    results.append(f"[#e25555][FAIL][/] schema_version mismatch: expected '2.0', found '{config.schema_version}'.")
                    errors += 1
                else:
                    results.append(f"[#4d4d4d][OK] config.yaml valid (Workspace: '{config.workspace_name}', Schema: '{config.schema_version}').[/]")
            except Exception as e:
                results.append(f"[#e25555][FAIL][/] config.yaml validation error: {e}")
                errors += 1

        # 2. Database check
        db_path = os.path.join(origin_dir, "workspace.db")
        if not os.path.exists(db_path):
            results.append("[#e25555][FAIL][/] workspace.db file is missing.")
            errors += 1
        else:
            try:
                repo = ArtifactRepository(db_path)
                repo.list_decisions()
                results.append("[#4d4d4d][OK] workspace.db schema is valid.[/]")
                # Affected files staleness
                decisions = repo.list_decisions(status="active")
                for dec in decisions:
                    for f in dec.affected_files:
                        if not os.path.exists(os.path.join(root, f)):
                            results.append(f"[#e2a855][WARN][/] Stale file reference: Decision '{dec.id[:8]}' affects '{f}' which does not exist.")
                            warnings += 1
            except Exception as e:
                results.append(f"[#e25555][FAIL][/] workspace.db read error: {e}")
                errors += 1

        # 3. Git repository check
        if not os.path.isdir(os.path.join(root, ".git")):
            results.append("[#e2a855][WARN][/] Not a git repository.")
            warnings += 1
        else:
            results.append("[#4d4d4d][OK] Git repository detected.[/]")

        for res in results:
            diag.mount(Static(res, markup=True))
            
        if errors > 0:
            summary = f"\n[bold #e25555]Doctor found {errors} integrity issues and {warnings} warnings.[/]"
        else:
            if warnings > 0:
                summary = f"\n[bold #e2a855]Workspace is healthy with {warnings} warnings.[/]"
            else:
                summary = f"\n[bold #00ffd2]Workspace is healthy and ready to go![/]"
        diag.mount(Static(summary, markup=True))


# ── Prompt Context View ────────────────────────────────────
class ContextView(VerticalScroll):
    """The Prompt Context View."""

    def compose(self) -> ComposeResult:
        yield Markdown(id="context-markdown")

    def update_data(self, context_bundle: str) -> None:
        self.query_one("#context-markdown", Markdown).update(context_bundle)


# ── Decisions View ─────────────────────────────────────────
class DecisionsView(Horizontal):
    """The Decisions Management View."""

    def compose(self) -> ComposeResult:
        with Vertical(id="decisions-list-pane", classes="list-pane"):
            yield ListView(id="decisions-list")
        yield InspectorPanel(id="decisions-inspector", classes="inspector-pane")

    def populate(self, decisions: list[Decision]) -> None:
        lst = self.query_one("#decisions-list", ListView)
        
        # Capture previous group header collapsed states
        collapsed_states = {}
        for item in lst.children:
            if isinstance(item, GroupHeaderItem):
                collapsed_states[item.category] = item.collapsed

        lst.clear()
        
        if not decisions:
            item = ListItem(Static("[#444444]No decisions recorded. Try: origin decision add[/]", markup=True))
            item.is_empty_state = True
            lst.append(item)
            return

        active_decs = [d for d in decisions if d.status == "active"]
        proposed_decs = [d for d in decisions if d.status == "proposed"]
        rejected_decs = [d for d in decisions if d.status in ["rejected", "superseded"]]

        groups = [
            ("Active Decisions", "active", active_decs, False),
            ("Proposed Decisions", "proposed", proposed_decs, False),
            ("Rejected & Superseded Decisions", "rejected", rejected_decs, True),
        ]

        for title, cat, items, default_collapsed in groups:
            collapsed = collapsed_states.get(cat, default_collapsed)
            header = GroupHeaderItem(title, cat, collapsed)
            lst.append(header)

            for dec in items:
                dec_item = DecisionItem(dec, cat)
                if collapsed:
                    dec_item.display = False
                lst.append(dec_item)
                
        if lst.children and lst.index is None:
            lst.index = 0
        self.update_inspector()

    def get_selected_decision(self) -> Optional[Decision]:
        lst = self.query_one("#decisions-list", ListView)
        if lst.highlighted_child and isinstance(lst.highlighted_child, DecisionItem):
            return lst.highlighted_child.decision
        return None

    def select_decision(self, dec_id: str) -> None:
        """Select a decision and expand its group header if collapsed."""
        lst = self.query_one("#decisions-list", ListView)
        found_idx = None
        found_header = None
        
        for idx, child in enumerate(lst.children):
            if isinstance(child, DecisionItem) and child.decision.id == dec_id:
                found_idx = idx
                for parent_idx in range(idx - 1, -1, -1):
                    p_child = lst.children[parent_idx]
                    if isinstance(p_child, GroupHeaderItem) and p_child.category == child.category:
                        found_header = p_child
                        break
                break

        if found_idx is not None:
            if found_header and found_header.collapsed:
                found_header.collapsed = False
                found_header.update_label()
                for child in lst.children:
                    if isinstance(child, DecisionItem) and child.category == found_header.category:
                        child.display = True
            
            lst.index = found_idx
            lst.focus()
            self.update_inspector()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self.update_inspector()

    def update_inspector(self) -> None:
        lst = self.query_one("#decisions-list", ListView)
        inspector = self.query_one("#decisions-inspector", InspectorPanel)
        if lst.highlighted_child and isinstance(lst.highlighted_child, DecisionItem):
            inspector.update_decision(lst.highlighted_child.decision)
        else:
            inspector.update_empty("Select a decision to inspect")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, GroupHeaderItem):
            header = event.item
            header.collapsed = not header.collapsed
            header.update_label()
            
            lst = self.query_one("#decisions-list", ListView)
            for child in lst.children:
                if isinstance(child, DecisionItem) and child.category == header.category:
                    child.display = not header.collapsed


# ── Knowledge View ─────────────────────────────────────────
class KnowledgeView(Horizontal):
    """The Knowledge Base (Memory) View."""

    def compose(self) -> ComposeResult:
        with Vertical(id="knowledge-list-pane", classes="list-pane"):
            yield ListView(id="knowledge-list")
        yield InspectorPanel(id="knowledge-inspector", classes="inspector-pane")

    def populate(self, memories: list[MemoryEntry]) -> None:
        lst = self.query_one("#knowledge-list", ListView)
        
        collapsed_states = {}
        for item in lst.children:
            if isinstance(item, GroupHeaderItem):
                collapsed_states[item.category] = item.collapsed

        lst.clear()

        if not memories:
            item = ListItem(Static("[#444444]No memory entries recorded. Try: origin memory set <cat> <key> <val>[/]", markup=True))
            item.is_empty_state = True
            lst.append(item)
            return

        groups = defaultdict(list)
        for mem in memories:
            groups[mem.category].append(mem)

        valid_categories = ["tech_stack", "convention", "architecture", "glossary", "deployment"]
        for cat in valid_categories:
            items = groups.get(cat, [])
            if not items:
                continue
                
            title = f"{cat.replace('_', ' ').title()} ({len(items)})"
            collapsed = collapsed_states.get(cat, False)
            header = GroupHeaderItem(title, cat, collapsed)
            lst.append(header)

            for mem in items:
                mem_item = MemoryItem(mem, cat)
                if collapsed:
                    mem_item.display = False
                lst.append(mem_item)

        if lst.children and lst.index is None:
            lst.index = 0
        self.update_inspector()

    def select_memory(self, category: str, key: str) -> None:
        """Select a memory entry and expand its group header if collapsed."""
        lst = self.query_one("#knowledge-list", ListView)
        found_idx = None
        found_header = None
        
        for idx, child in enumerate(lst.children):
            if isinstance(child, MemoryItem) and child.memory.category == category and child.memory.key == key:
                found_idx = idx
                for parent_idx in range(idx - 1, -1, -1):
                    p_child = lst.children[parent_idx]
                    if isinstance(p_child, GroupHeaderItem) and p_child.category == child.category:
                        found_header = p_child
                        break
                break

        if found_idx is not None:
            if found_header and found_header.collapsed:
                found_header.collapsed = False
                found_header.update_label()
                for child in lst.children:
                    if isinstance(child, MemoryItem) and child.category == found_header.category:
                        child.display = True
            
            lst.index = found_idx
            lst.focus()
            self.update_inspector()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self.update_inspector()

    def update_inspector(self) -> None:
        lst = self.query_one("#knowledge-list", ListView)
        inspector = self.query_one("#knowledge-inspector", InspectorPanel)
        if lst.highlighted_child and isinstance(lst.highlighted_child, MemoryItem):
            inspector.update_memory(lst.highlighted_child.memory)
        else:
            inspector.update_empty("Select a memory entry to inspect")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, GroupHeaderItem):
            header = event.item
            header.collapsed = not header.collapsed
            header.update_label()
            
            lst = self.query_one("#knowledge-list", ListView)
            for child in lst.children:
                if isinstance(child, MemoryItem) and child.category == header.category:
                    child.display = not header.collapsed


# ── Timeline View ──────────────────────────────────────────
class TimelineView(Horizontal):
    """The Chronological Timeline View."""

    def compose(self) -> ComposeResult:
        with Vertical(id="timeline-list-pane", classes="list-pane"):
            yield ListView(id="timeline-list")
        with Vertical(id="timeline-info-panel", classes="inspector-pane"):
            yield Static(
                "[#777777]Timeline Overview[/]\n\n"
                "[bold #00ffd2]Chronological Activity Log[/]\n\n"
                "This pane lists all events in your workspace memory:\n\n"
                "  ● [#00ffd2]Decisions proposed, accepted, or rejected[/]\n"
                "  ◆ [#00ffd2]Memory entries updated[/]\n"
                "  ■ [#00ffd2]Git commits synced with workspace[/]\n\n"
                "Origin automatically captures these changes to maintain a continuous, auditable history of your agent's context.",
                id="timeline-info-content",
                markup=True
            )

    def populate(self, events: list[TimelineEvent], decisions: list[Decision]) -> None:
        lst = self.query_one("#timeline-list", ListView)
        lst.clear()

        if not events:
            item = ListItem(Static("[#444444]No timeline events recorded yet.[/]", markup=True))
            item.is_header = True
            lst.append(item)
            return

        dec_map = {d.id: d for d in decisions}
        
        groups = defaultdict(list)
        for event in events:
            day_str = event.created_at.strftime("%B %d, %Y")
            groups[day_str].append(event)

        days = sorted(groups.keys(), key=lambda d: datetime.strptime(d, "%B %d, %Y"), reverse=True)

        for day in days:
            header = Static(f"[bold #444444]──── {day} ────[/]", classes="day-header")
            item_header = ListItem(header)
            item_header.is_header = True
            lst.append(item_header)

            for event in groups[day]:
                item = TimelineItem(event, dec_map.get(event.ref_artifact_id))
                item.is_header = False
                lst.append(item)

        if lst.children and lst.index is None:
            lst.index = 0


# ── Live Search Results View ───────────────────────────────
class SearchResultsView(Horizontal):
    """View to display live search results."""

    def compose(self) -> ComposeResult:
        with Vertical(id="search-list-pane", classes="list-pane"):
            yield ListView(id="search-list")
        yield InspectorPanel(id="search-inspector", classes="inspector-pane")

    def populate(self, results: list[Any]) -> None:
        lst = self.query_one("#search-list", ListView)
        lst.clear()

        if not results:
            item = ListItem(Static("[#444444]No matching results found.[/]", markup=True))
            item.result_data = None
            lst.append(item)
            return

        for art in results:
            if art.type == "decision":
                style = STATUS_STYLES.get(art.status, "")
                glyph = STATUS_GLYPHS.get(art.status, "")
                label = f"[bold #00ffd2]Decision:[/] [{style}]{glyph} {art.title}[/] [dim #444444]({art.id[:8]})[/]"
            else:
                label = f"[bold #00ffd2]Memory:[/] [#00ffd2]{art.category}.{art.key}[/] = [dim #444444]{art.value}[/]"
            
            item = ListItem(Static(label, markup=True))
            item.result_data = art
            lst.append(item)

        if lst.children:
            lst.index = 0
        self.update_inspector()

    def get_selected_result(self) -> Optional[Any]:
        lst = self.query_one("#search-list", ListView)
        if lst.highlighted_child and getattr(lst.highlighted_child, "result_data", None):
            return lst.highlighted_child.result_data
        return None

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self.update_inspector()

    def update_inspector(self) -> None:
        lst = self.query_one("#search-list", ListView)
        inspector = self.query_one("#search-inspector", InspectorPanel)
        
        if lst.highlighted_child and getattr(lst.highlighted_child, "result_data", None):
            res = lst.highlighted_child.result_data
            if res.type == "decision":
                inspector.update_decision(res)
            else:
                inspector.update_memory(res)
        else:
            inspector.update_empty("Select a search result to inspect")


# ── Command Input Container ────────────────────────────────
class CommandInput(Container):
    """The always-focused command and search input at the bottom."""

    def compose(self) -> ComposeResult:
        yield Static(" › ", id="input-prefix")
        yield Input(placeholder="Type command or search...", id="input-field")


# ── Main App ───────────────────────────────────────────────
class OriginTUI(App):
    """The complete Origin TUI workspace App."""

    CSS_PATH = "theme.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "escape_action", "Escape", show=False),
        Binding("slash", "focus_input", "Search", show=False),
        Binding("a", "accept_decision", "Accept", show=False),
        Binding("r", "reject_decision", "Reject", show=False),
        Binding("i", "toggle_inspector", "Toggle Inspector", show=False),
    ]

    show_inspector_narrow = reactive(False)

    def __init__(self, workspace_root: Optional[str] = None, show_splash: bool = True) -> None:
        super().__init__()
        self.workspace_root = workspace_root or os.getcwd()
        self.show_splash = show_splash
        
        self._decisions: list[Decision] = []
        self._all_decisions: list[Decision] = []
        self._memories: list[MemoryEntry] = []
        self._timeline: list[TimelineEvent] = []
        
        self._last_dir_state: dict[str, tuple[int, float]] = {}
        self._refresh_timer: Optional[Timer] = None
        self._status_clear_timer: Optional[Timer] = None
        
        self.views_cycle = ["overview", "context", "decisions", "knowledge", "timeline"]
        self.current_view_idx = 0

    @property
    def is_narrow(self) -> bool:
        """Dynamically evaluate whether the layout drops below 80 columns."""
        return self.size.width < 80

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        
        with ContentSwitcher(initial="overview", id="main-switcher"):
            yield HomeView(id="overview")
            yield ContextView(id="context")
            yield DecisionsView(id="decisions")
            yield KnowledgeView(id="knowledge")
            yield TimelineView(id="timeline")
            yield SearchResultsView(id="search")
            
        yield Static("", id="status-message")
        yield CommandInput(id="command-input")

    def on_mount(self) -> None:
        if self.show_splash:
            self.push_screen(SplashScreen())

        self._load_all_data()
        self._render_all()
        self._update_layout_classes()

        # Initialize dir change state to prevent false positive reload on first poll
        self._check_dir_changes()

        # Check doctor inline output initially
        self.query_one("#overview", HomeView).run_doctor_checks()

        # Focus input field immediately and keep it focused
        self.query_one("#input-field", Input).focus()

        # Polling for data refreshes
        self._refresh_timer = self.set_interval(2.0, self._poll_for_changes)

    def on_resize(self, event=None) -> None:
        if event and hasattr(event, "size"):
            self._update_layout_classes(event.size.width)
        else:
            self._update_layout_classes()

    def _update_layout_classes(self, width: Optional[int] = None) -> None:
        w = width if width is not None else self.size.width
        if w < 80:
            self.add_class("narrow")
            self.remove_class("wide")
        else:
            self.add_class("wide")
            self.remove_class("narrow")

    def watch_show_inspector_narrow(self, val: bool) -> None:
        if val:
            self.add_class("show-inspector")
        else:
            self.remove_class("show-inspector")

    # ── Key Handling for Navigation ───────────────────────────
    def on_key(self, event) -> None:
        if event.key in ("up", "down"):
            current_view_id = self.query_one("#main-switcher", ContentSwitcher).current
            if current_view_id == "decisions":
                lst = self.query_one("#decisions-list", ListView)
                if event.key == "up":
                    lst.action_cursor_up()
                else:
                    lst.action_cursor_down()
                event.prevent_default()
            elif current_view_id == "knowledge":
                lst = self.query_one("#knowledge-list", ListView)
                if event.key == "up":
                    lst.action_cursor_up()
                else:
                    lst.action_cursor_down()
                event.prevent_default()
            elif current_view_id == "timeline":
                lst = self.query_one("#timeline-list", ListView)
                if event.key == "up":
                    lst.action_cursor_up()
                else:
                    lst.action_cursor_down()
                event.prevent_default()
            elif current_view_id == "search":
                lst = self.query_one("#search-list", ListView)
                if event.key == "up":
                    lst.action_cursor_up()
                else:
                    lst.action_cursor_down()
                event.prevent_default()

    # ── Input Bar Event Handlers ──────────────────────────────
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "input-field":
            return
        
        val = event.value.strip()
        if not val:
            current_view_id = self.query_one("#main-switcher", ContentSwitcher).current
            if current_view_id == "search":
                self.switch_view("overview")
            return

        # Check if it starts with "/" and is a prefix of or matches a known command
        is_known_command = False
        for cmd in ["/d", "/decisions", "/k", "/knowledge", "/t", "/timeline", "/c", "/context", "/doctor", "/export", "/accept", "/reject", "/help", "/q", "/quit"]:
            if cmd.startswith(val) or val.startswith(cmd):
                is_known_command = True
                break

        if val.startswith("/") and is_known_command:
            return

        # Search mode
        query_val = val
        if query_val.startswith("/"):
            query_val = query_val[1:]

        self.switch_view("search")
        try:
            results = use_cases.search_artifacts(self.workspace_root, query_val)
            self.query_one("#search", SearchResultsView).populate(results)
        except Exception as e:
            self.query_one("#search", SearchResultsView).populate([])
            self._show_status(f"Search error: {e}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "input-field":
            return
        
        val = event.value.strip()
        if not val:
            return

        if val.startswith("/"):
            parts = val.split(maxsplit=1)
            cmd = parts[0]

            is_known = cmd in ("/d", "/decisions", "/k", "/knowledge", "/t", "/timeline", "/c", "/context", "/doctor", "/export", "/accept", "/reject", "/help", "/q", "/quit")
            if is_known:
                if cmd in ("/d", "/decisions"):
                    self.switch_view("decisions")
                    event.input.value = ""
                elif cmd in ("/k", "/knowledge"):
                    self.switch_view("knowledge")
                    event.input.value = ""
                elif cmd in ("/t", "/timeline"):
                    self.switch_view("timeline")
                    event.input.value = ""
                elif cmd in ("/c", "/context"):
                    self.switch_view("context")
                    event.input.value = ""
                elif cmd == "/doctor":
                    self.switch_view("overview")
                    self.query_one("#overview", HomeView).run_doctor_checks()
                    event.input.value = ""
                elif cmd == "/export":
                    target = "generic"
                    if len(parts) > 1:
                        val_target = parts[1].strip().lower()
                        if val_target in ("claude-code", "claude", "cc"):
                            target = "claude-code"
                        elif val_target in ("cursor", "cur"):
                            target = "cursor"
                        elif val_target in ("generic", "gen"):
                            target = "generic"
                    try:
                        dest = export_flat_file(self.workspace_root, target)
                        self._show_status(f"Exported to {os.path.basename(dest)}")
                    except Exception as e:
                        self._show_status(f"Export failed: {e}")
                    event.input.value = ""
                elif cmd == "/accept":
                    self.action_accept_decision()
                    event.input.value = ""
                elif cmd == "/reject":
                    self.action_reject_decision()
                    event.input.value = ""
                elif cmd in ("/q", "/quit"):
                    self.exit()
                elif cmd == "/help":
                    self.switch_view("overview")
                    event.input.value = ""
                return

        current_view_id = self.query_one("#main-switcher", ContentSwitcher).current
        if current_view_id == "search":
            selected = self.query_one("#search", SearchResultsView).get_selected_result()
            if selected:
                self._handle_search_result(selected)
                event.input.value = ""
        elif current_view_id == "decisions":
            lst = self.query_one("#decisions-list", ListView)
            if lst.highlighted_child:
                lst.select(lst.highlighted_child)
        elif current_view_id == "knowledge":
            lst = self.query_one("#knowledge-list", ListView)
            if lst.highlighted_child:
                lst.select(lst.highlighted_child)

    # ── Data loading and polling ───────────────────────────
    def _load_all_data(self) -> None:
        try:
            origin_dir = get_origin_dir(self.workspace_root)
            db_path = os.path.join(origin_dir, "workspace.db")
            repo = ArtifactRepository(db_path)

            self._all_decisions = []
            for status in ["active", "proposed", "superseded", "rejected"]:
                self._all_decisions.extend(repo.list_decisions(status=status))
            
            # Sort newest first
            self._all_decisions.sort(key=lambda d: d.created_at, reverse=True)
            self._decisions = list(self._all_decisions)

            self._memories = repo.list_memory()
            self._timeline = repo.list_timeline()
            self._timeline.sort(key=lambda e: e.created_at, reverse=True)
        except Exception:
            self._decisions = []
            self._all_decisions = []
            self._memories = []
            self._timeline = []

    def _render_all(self) -> None:
        # Get workspace metrics
        try:
            config = load_config(self.workspace_root)
            ws_name = config.workspace_name
        except Exception:
            ws_name = "Unknown"
            
        git = GitHelper(self.workspace_root)
        branch = git.get_current_branch() or "no git"

        # Update HeaderBar
        health_glyph, health_style = self._compute_health()
        view_label = self.views_cycle[self.current_view_idx]
        self.query_one("#header-bar", HeaderBar).update_header(
            ws_name, branch, health_glyph, health_style, view_label
        )

        # Update HomeView (overview)
        proposed_cnt = len([d for d in self._all_decisions if d.status == "proposed"])
        active_cnt = len([d for d in self._all_decisions if d.status == "active"])
        memory_cnt = len(self._memories)
        
        self.query_one("#overview", HomeView).query_one("#welcome-card", WelcomeCard).update_data(
            ws_name, branch, health_glyph, health_style,
            proposed_cnt, active_cnt, memory_cnt, self._timeline
        )

        # Update Context View
        try:
            bundle = use_cases.get_context_bundle(self.workspace_root)
        except Exception as e:
            bundle = f"Failed to load context bundle: {e}"
        self.query_one("#context", ContextView).update_data(bundle)

        # Update Decisions View
        self.query_one("#decisions", DecisionsView).populate(self._all_decisions)

        # Update Knowledge View
        self.query_one("#knowledge", KnowledgeView).populate(self._memories)

        # Update Timeline View
        self.query_one("#timeline", TimelineView).populate(self._timeline, self._all_decisions)

    def _render_header(self) -> None:
        try:
            config = load_config(self.workspace_root)
            ws_name = config.workspace_name
        except Exception:
            ws_name = "Unknown"

        git = GitHelper(self.workspace_root)
        branch = git.get_current_branch() or "no git"

        health_glyph, health_style = self._compute_health()
        view_label = self.views_cycle[self.current_view_idx]
        self.query_one("#header-bar", HeaderBar).update_header(
            ws_name, branch, health_glyph, health_style, view_label
        )

    def _compute_health(self) -> tuple[str, str]:
        origin_dir = os.path.join(self.workspace_root, ".origin")
        errors = 0
        warnings = 0

        if not os.path.exists(os.path.join(origin_dir, "config.yaml")):
            errors += 1
        else:
            try:
                config = load_config(self.workspace_root)
                if config.schema_version != "2.0":
                    errors += 1
            except Exception:
                errors += 1

        if not os.path.exists(os.path.join(origin_dir, "workspace.db")):
            errors += 1

        if not os.path.isdir(os.path.join(self.workspace_root, ".git")):
            warnings += 1

        if errors > 0:
            return "●", "#e25555"
        elif warnings > 0:
            return "●", "#e2a855"
        else:
            return "●", "#00ffd2"

    def _poll_for_changes(self) -> None:
        if self._check_dir_changes():
            self._load_all_data()
            self._render_all()
            self.query_one("#overview", HomeView).run_doctor_checks()
        else:
            self._render_header()

    def _check_dir_changes(self) -> bool:
        origin_dir = get_origin_dir(self.workspace_root)
        dirs_to_check = ["decisions", "memory", "timeline"]
        changed = False

        for dirname in dirs_to_check:
            dir_path = os.path.join(origin_dir, dirname)
            if not os.path.isdir(dir_path):
                continue

            try:
                entries = os.listdir(dir_path)
                file_count = len(entries)
                max_mtime = 0.0
                for entry in entries:
                    entry_path = os.path.join(dir_path, entry)
                    try:
                        st = os.stat(entry_path)
                        if st.st_mtime > max_mtime:
                            max_mtime = st.st_mtime
                    except OSError:
                        pass

                current_state = (file_count, max_mtime)
                if dirname not in self._last_dir_state or self._last_dir_state[dirname] != current_state:
                    self._last_dir_state[dirname] = current_state
                    changed = True
            except OSError:
                pass

        return changed

    def _show_status(self, message: str, duration: float = 3.0) -> None:
        status = self.query_one("#status-message", Static)
        status.update(f"[#e2a855]{message}[/]")
        if self._status_clear_timer:
            self._status_clear_timer.stop()
        self._status_clear_timer = self.set_timer(duration, self._clear_status)

    def _clear_status(self) -> None:
        status = self.query_one("#status-message", Static)
        status.update("")

    # ── Keybinding and Navigation Actions ──────────────────
    def switch_view(self, view_name: str) -> None:
        if view_name in self.views_cycle or view_name == "search":
            if view_name != "search":
                self.current_view_idx = self.views_cycle.index(view_name)
            self.query_one("#main-switcher", ContentSwitcher).current = view_name
            self._render_header()

    def action_focus_input(self) -> None:
        inp = self.query_one("#input-field", Input)
        inp.focus()
        if not inp.value.startswith("/"):
            inp.value = "/"
            inp.cursor_position = 1

    def action_escape_action(self) -> None:
        inp = self.query_one("#input-field", Input)
        if inp.value:
            inp.value = ""
            self.switch_view("overview")
        else:
            self.switch_view("overview")

    def _handle_search_result(self, result: Any) -> None:
        if not result:
            return
            
        if hasattr(result, "type") and result.type == "decision":
            self.switch_view("decisions")
            self.query_one("#decisions", DecisionsView).select_decision(result.id)
        elif hasattr(result, "type") and result.type == "memory":
            self.switch_view("knowledge")
            self.query_one("#knowledge", KnowledgeView).select_memory(result.category, result.key)

    def action_accept_decision(self) -> None:
        dec_view = self.query_one("#decisions", DecisionsView)
        dec = dec_view.get_selected_decision()
        if not dec:
            self._show_status("No decision selected.")
            return

        if dec.status != "proposed":
            self._show_status("Only proposed decisions can be accepted.")
            return

        try:
            use_cases.accept_decision(self.workspace_root, dec.id, agent="human")
            self._show_status(f"Accepted: '{dec.title}'")
            self._load_all_data()
            self._render_all()
        except Exception as e:
            self._show_status(f"Error accepting: {e}")

    def action_reject_decision(self) -> None:
        dec_view = self.query_one("#decisions", DecisionsView)
        dec = dec_view.get_selected_decision()
        if not dec:
            self._show_status("No decision selected.")
            return

        if dec.status != "proposed":
            self._show_status("Only proposed decisions can be rejected.")
            return

        try:
            use_cases.reject_decision(self.workspace_root, dec.id, agent="human")
            self._show_status(f"Rejected: '{dec.title}'")
            self._load_all_data()
            self._render_all()
        except Exception as e:
            self._show_status(f"Error rejecting: {e}")

    def action_toggle_inspector(self) -> None:
        self.show_inspector_narrow = not self.show_inspector_narrow
        status_word = "ON" if self.show_inspector_narrow else "OFF"
        self._show_status(f"Narrow inspector toggled {status_word}")


def run_tui(workspace_root: Optional[str] = None) -> None:
    """Launch the Origin TUI dashboard."""
    app = OriginTUI(workspace_root=workspace_root)
    app.run()
