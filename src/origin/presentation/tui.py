"""Origin TUI — Interactive terminal workspace.

A keyboard-first, responsive terminal dashboard featuring six views,
a command palette, a search overlay, and a reactive sidebar inspector.
Every action delegates to the same use_cases.py functions the CLI and MCP
server already call.
"""

import os
import re
from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Optional, Any, Dict, Set

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Footer,
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
    "proposed": "#0a4a42",
    "rejected": "bold #e25555",
    "superseded": "#4d4d4d",
}

TIMELINE_GLYPHS = {
    "decision_created": "◌",
    "decision_accepted": "●",
    "decision_rejected": "✕",
    "decision_superseded": "↺",
    "memory_updated": "◆",
    "commit": "■",
}

SINGULARITY_FRAMES = ["◐", "◓", "◑", "◒"]

# ── Splash Screen Art ──────────────────────────────────────
SPLASH_ART = """
                     [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
                 [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████████████████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
              [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓█████▓▓▒▒░░  ░░▒▒▓▓█████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
            [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████▓▓▒▒░          ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
          [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████▓▓▒▒░              ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
        [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████▓▒░     ░░▒▒▓▓██▓▒░    ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░[/#0a4a42]
       [#0a4a42]░▒▒[/#0a4a42][#00ffd2]▓▓█████▓▒░     ░▒▓████████▓▒░    ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░[/#0a4a42]
      [#0a4a42]░▒[/#0a4a42][#00ffd2]▓▓██████▒░      ░▒▓███    ███▓▒░     ▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒[/#0a4a42]
      [#0a4a42]▒[/#0a4a42][#00ffd2]▓███████▓░       ▒▓██        ██▓▒      ▓████████▓[/#00ffd2][#0a4a42]▒[/#0a4a42]
  [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████████████████████        ████████████████████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
  [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████████████████████        ████████████████████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
      [#0a4a42]▒[/#0a4a42][#00ffd2]▓███████▓░       ▒▓██        ██▓▒      ▓████████▓[/#00ffd2][#0a4a42]▒[/#0a4a42]
      [#0a4a42]░▒[/#0a4a42][#00ffd2]▓▓██████▒░      ░▒▓███    ███▓▒░     ▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒[/#0a4a42]
       [#0a4a42]░▒▒[/#0a4a42][#00ffd2]▓▓█████▓▒░     ░▒▓████████▓▒░    ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░[/#0a4a42]
        [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████▓▒░     ░░▒▒▓▓██▓▒░    ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░[/#0a4a42]
          [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████▓▓▒▒░              ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
            [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████▓▓▒▒░          ░▒▓██████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
              [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓█████▓▓▒▒░░  ░░▒▒▓▓█████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
                 [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████████████████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]
                     [#0a4a42]░░▒▒[/#0a4a42][#00ffd2]▓▓████████▓▓[/#00ffd2][#0a4a42]▒▒░░[/#0a4a42]

                               [bold #00ffd2]O R I G I N[/]
"""


# ── Splash Screen ──────────────────────────────────────────
class SplashScreen(Screen):
    """Full-screen splash screen showing the 8-bit black hole."""

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
        sign = "[+]" if self.collapsed else "[-]"
        yield Static(f"[bold #00ffd2]{sign} {self.title}[/]", id="header-label", markup=True)

    def update_label(self) -> None:
        sign = "[+]" if self.collapsed else "[-]"
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
            
        label_text = f"[{style}]{glyph}[/]  [{style}]{title}[/]  [#0a4a42]{dec.confidence:.2f}  {short_id}[/]"
        if dec.superseded_by:
            label_text += f"\n   [#4d4d4d]└─ superseded by {dec.superseded_by[:8]}[/]"
            
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
            
        label_text = f"  [#4d4d4d]{key_str}[/] = [#00ffd2]{val_str}[/]"
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
            color = "#4d4d4d"
        elif "memory" in event.event_type:
            color = "#00ffd2"
        elif "commit" in event.event_type:
            color = "#0a4a42"
        else:
            color = "#4d4d4d"

        label = f"[#0a4a42]{time_str}[/]  [bold {color}]{glyph}[/]  [#4d4d4d]{event.summary}[/]"
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
            superseded = f"\n[bold #0a4a42]Superseded by:[/] [#00ffd2]{dec.superseded_by}[/]"

        content = (
            f"[bold #00ffd2]DECISION INSPECTOR[/]\n\n"
            f"[bold {style}]{glyph} {dec.title}[/]\n\n"
            f"[bold #0a4a42]ID:[/] {dec.id}\n"
            f"[bold #0a4a42]Status:[/] {dec.status}\n"
            f"[bold #0a4a42]Confidence:[/] {dec.confidence:.2f}\n"
            f"[bold #0a4a42]Agent:[/] {dec.originating_agent}\n"
            f"[bold #0a4a42]Created:[/] {dec.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"[bold #0a4a42]Updated:[/] {dec.updated_at.strftime('%Y-%m-%d %H:%M UTC')}"
            f"{superseded}\n\n"
            f"[bold #00ffd2]Rationale[/]\n{dec.rationale}\n\n"
            f"[bold #00ffd2]Alternatives Considered[/]\n{alts}\n\n"
            f"[bold #00ffd2]Affected Files[/]\n{files}"
        )
        self.query_one("#inspector-content", Static).update(content)

    def update_memory(self, mem: MemoryEntry) -> None:
        content = (
            f"[bold #00ffd2]MEMORY INSPECTOR[/]\n\n"
            f"[bold #00ffd2]{mem.category}.{mem.key}[/]\n\n"
            f"[bold #0a4a42]Value:[/] {mem.value}\n"
            f"[bold #0a4a42]ID:[/] {mem.id}\n"
            f"[bold #0a4a42]Agent:[/] {mem.originating_agent}\n"
            f"[bold #0a4a42]Created:[/] {mem.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"[bold #0a4a42]Updated:[/] {mem.updated_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        self.query_one("#inspector-content", Static).update(content)

    def update_timeline_event(self, event: TimelineEvent, related_dec: Optional[Decision] = None) -> None:
        content = (
            f"[bold #00ffd2]TIMELINE EVENT INSPECTOR[/]\n\n"
            f"[bold #00ffd2]{event.summary}[/]\n\n"
            f"[bold #0a4a42]Event Type:[/] {event.event_type}\n"
            f"[bold #0a4a42]ID:[/] {event.id}\n"
            f"[bold #0a4a42]Agent:[/] {event.originating_agent}\n"
            f"[bold #0a4a42]Commit SHA:[/] {event.commit_sha or 'None'}\n"
            f"[bold #0a4a42]Time:[/] {event.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        if related_dec:
            content += f"\n\n[bold #0a4a42]Related Decision Title:[/] {related_dec.title}"
        self.query_one("#inspector-content", Static).update(content)

    def update_empty(self, message: str = "Select an item to inspect") -> None:
        self.query_one("#inspector-content", Static).update(f"[#4d4d4d]{message}[/]")


# ── Core Views ─────────────────────────────────────────────
class OverviewView(VerticalScroll):
    """The Overview Landing Dashboard View."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="overview-card"):
            yield Static("[bold #00ffd2]WORKSPACE SUMMARY[/]\n", markup=True)
            yield Static(id="overview-info", markup=True)
            
        with Horizontal(id="overview-metrics"):
            yield Static(id="metric-proposed", classes="metric-card", markup=True)
            yield Static(id="metric-active", classes="metric-card", markup=True)
            yield Static(id="metric-memory", classes="metric-card", markup=True)
            
        with Vertical(classes="panel"):
            yield Static("[bold #00ffd2]INLINE SYSTEM DIAGNOSTICS[/]", markup=True)
            yield VerticalScroll(id="overview-diagnostics", classes="diagnostics-panel")
            
        with Vertical(classes="panel"):
            yield Static("[bold #00ffd2]RECENT ACTIVITY[/]", markup=True)
            yield Vertical(id="overview-timeline-feed")

    def update_data(self, workspace_name: str, branch: str, active_agents: int,
                    decisions: list[Decision], memories: list[MemoryEntry],
                    timeline: list[TimelineEvent]) -> None:
        
        proposed_cnt = len([d for d in decisions if d.status == "proposed"])
        active_cnt = len([d for d in decisions if d.status == "active"])
        memory_cnt = len(memories)

        # Update summary text
        info = (
            f"[bold #0a4a42]Workspace display name:[/] [#00ffd2]{workspace_name}[/]\n"
            f"[bold #0a4a42]Active branch:[/] [#00ffd2]{branch}[/]\n"
            f"[bold #0a4a42]Recently active agents:[/] [#00ffd2]{active_agents}[/]"
        )
        self.query_one("#overview-info", Static).update(info)

        # Update metric cards
        self.query_one("#metric-proposed", Static).update(f"[#0a4a42]Proposed Decisions[/]\n[bold #00ffd2]  {proposed_cnt}[/]")
        self.query_one("#metric-active", Static).update(f"[#00ffd2]Active Decisions[/]\n[bold #00ffd2]  {active_cnt}[/]")
        self.query_one("#metric-memory", Static).update(f"[#4d4d4d]Memory Entries[/]\n[bold #00ffd2]  {memory_cnt}[/]")

        # Update recent activity feed (last 5 events)
        feed = self.query_one("#overview-timeline-feed", Vertical)
        feed.remove_children()
        
        if not timeline:
            feed.mount(Static("[#4d4d4d]No recent activity logged.[/]", markup=True))
        else:
            for event in timeline[:5]:
                time_str = event.created_at.strftime("%H:%M")
                glyph = TIMELINE_GLYPHS.get(event.event_type, "●")
                line = f"[#0a4a42]{time_str}[/]  [#00ffd2]{glyph}[/]  [#4d4d4d]{event.summary}[/]"
                feed.mount(Static(line, markup=True))

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
                    results.append(f"[#00ffd2][OK][/] config.yaml valid (Workspace: '{config.workspace_name}', Schema: '{config.schema_version}').")
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
                results.append("[#00ffd2][OK][/] workspace.db schema is valid.")
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
            results.append("[#00ffd2][OK][/] Git repository detected.")

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


class ContextView(VerticalScroll):
    """The Prompt Context View."""

    def compose(self) -> ComposeResult:
        yield Static("[bold #00ffd2]PROMPT CONTEXT BUNDLE[/]\n", markup=True)
        yield Markdown(id="context-markdown")

    def update_data(self, context_bundle: str) -> None:
        self.query_one("#context-markdown", Markdown).update(context_bundle)


class DecisionsView(Horizontal):
    """The Decisions Management View."""

    def compose(self) -> ComposeResult:
        with Vertical(id="decisions-list-pane", classes="list-pane"):
            yield Static("[bold #00ffd2]DECISIONS[/]", classes="panel-title", markup=True)
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
            item = ListItem(Static("[#0a4a42]No decisions recorded. Try calling origin decision add[/]", markup=True))
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

    def on_list_view_highlighted_changed(self, event: ListView.HighlightedChanged) -> None:
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


class KnowledgeView(Horizontal):
    """The Knowledge Base (Memory) View."""

    def compose(self) -> ComposeResult:
        with Vertical(id="knowledge-list-pane", classes="list-pane"):
            yield Static("[bold #00ffd2]KNOWLEDGE BASE[/]", classes="panel-title", markup=True)
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
            item = ListItem(Static("[#0a4a42]No memory entries recorded. Try: origin memory set <cat> <key> <val>[/]", markup=True))
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

    def on_list_view_highlighted_changed(self, event: ListView.HighlightedChanged) -> None:
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


class TimelineView(Horizontal):
    """The Chronological Timeline View."""

    def compose(self) -> ComposeResult:
        with Vertical(id="timeline-list-pane", classes="list-pane"):
            yield Static("[bold #00ffd2]TIMELINE[/]", classes="panel-title", markup=True)
            yield ListView(id="timeline-list")
        yield InspectorPanel(id="timeline-inspector", classes="inspector-pane")

    def populate(self, events: list[TimelineEvent], decisions: list[Decision]) -> None:
        lst = self.query_one("#timeline-list", ListView)
        lst.clear()

        if not events:
            item = ListItem(Static("[#0a4a42]No timeline events recorded yet.[/]", markup=True))
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
            header = Static(f"[bold #0a4a42] {day} [/]", classes="day-header")
            item_header = ListItem(header)
            item_header.is_header = True
            lst.append(item_header)

            for event in groups[day]:
                item = TimelineItem(event, dec_map.get(event.ref_artifact_id))
                item.is_header = False
                lst.append(item)

        if lst.children and lst.index is None:
            lst.index = 0

    def on_list_view_highlighted_changed(self, event: ListView.HighlightedChanged) -> None:
        self.update_inspector()

    def update_inspector(self) -> None:
        lst = self.query_one("#timeline-list", ListView)
        inspector = self.query_one("#timeline-inspector", InspectorPanel)
        
        if lst.highlighted_child and getattr(lst.highlighted_child, "is_header", False) is False:
            item = lst.highlighted_child
            inspector.update_timeline_event(item.event, item.related_decision)
        else:
            inspector.update_empty("Select an event to inspect")


# ── Command Palette Overlay ────────────────────────────────
class CommandPaletteModal(ModalScreen[str]):
    """Sleek keyboard-driven command palette overlay."""

    def compose(self) -> ComposeResult:
        with Vertical(id="command-palette"):
            yield Static("[bold #00ffd2]COMMAND PALETTE[/]", id="command-palette-title")
            yield Input(placeholder="Type command... (Up/Down to navigate, Enter to run, ESC to close)", id="command-palette-input")
            yield ListView(id="command-palette-list")

    def on_mount(self) -> None:
        self.query_one("#command-palette-input", Input).focus()
        self._populate_list("")

    def _populate_list(self, filter_text: str) -> None:
        lst = self.query_one("#command-palette-list", ListView)
        lst.clear()
        
        # Toggle options depending on decisions view selection
        dec_view = self.app.query_one("#decisions", DecisionsView)
        selected_dec = dec_view.get_selected_decision()
        can_accept_reject = selected_dec is not None and selected_dec.status == "proposed"

        actions = [
            ("Jump to Overview", "jump_overview"),
            ("Jump to Context", "jump_context"),
            ("Jump to Decisions", "jump_decisions"),
            ("Jump to Knowledge Base", "jump_knowledge"),
            ("Jump to Timeline", "jump_timeline"),
            ("Accept Selected Decision", "accept_decision"),
            ("Reject Selected Decision", "reject_decision"),
            ("Search Workspace (/)", "search_workspace"),
            ("Generate Context Export (ORIGIN.md)", "generate_export"),
            ("Run Doctor Checks", "run_doctor"),
            ("Quit", "quit"),
        ]

        for label, action in actions:
            if action in ["accept_decision", "reject_decision"] and not can_accept_reject:
                item = ListItem(Static(f"[#4d4d4d]{label} (Requires selecting a proposed decision)[/]", markup=True))
                item.action_id = "disabled"
            else:
                if not filter_text or filter_text.lower() in label.lower():
                    item = ListItem(Static(f"[#00ffd2]{label}[/]", markup=True))
                    item.action_id = action
                    lst.append(item)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate_list(event.value.strip())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        action = getattr(event.item, "action_id", "disabled")
        if action != "disabled":
            self.dismiss(action)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        lst = self.query_one("#command-palette-list", ListView)
        if lst.highlighted_child:
            action = getattr(lst.highlighted_child, "action_id", "disabled")
            if action != "disabled":
                self.dismiss(action)


# ── Search Overlay ─────────────────────────────────────────
class SearchOverlay(ModalScreen[Any]):
    """Full-width workspace search overlay."""

    def compose(self) -> ComposeResult:
        with Vertical(id="search-overlay-container"):
            yield Static("[bold #00ffd2]SEARCH WORKSPACE[/]", id="search-overlay-title")
            yield Input(placeholder="Type to search decisions & memory... (ESC to close)", id="search-overlay-input")
            yield ListView(id="search-overlay-list")

    def on_mount(self) -> None:
        self.query_one("#search-overlay-input", Input).focus()
        self._perform_search("")

    def _perform_search(self, query: str) -> None:
        lst = self.query_one("#search-overlay-list", ListView)
        lst.clear()
        
        if not query:
            item = ListItem(Static("[#4d4d4d]Type to start searching...[/]", markup=True))
            item.result_data = None
            lst.append(item)
            return

        try:
            results = use_cases.search_artifacts(self.app.workspace_root, query)
            if not results:
                item = ListItem(Static("[#e25555]No matching results found.[/]", markup=True))
                item.result_data = None
                lst.append(item)
                return

            for art in results:
                if art.type == "decision":
                    style = STATUS_STYLES.get(art.status, "")
                    glyph = STATUS_GLYPHS.get(art.status, "")
                    label = f"[bold #00ffd2]Decision:[/] [{style}]{glyph} {art.title}[/] [dim #4d4d4d]({art.id[:8]})[/]"
                else:
                    label = f"[bold #00ffd2]Memory:[/] [#00ffd2]{art.category}.{art.key}[/] = [dim #4d4d4d]{art.value}[/]"
                
                item = ListItem(Static(label, markup=True))
                item.result_data = art
                lst.append(item)
        except Exception as e:
            item = ListItem(Static(f"[#e25555]Error: {e}[/]", markup=True))
            item.result_data = None
            lst.append(item)

        if lst.children and lst.index is None:
            lst.index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._perform_search(event.value.strip())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if getattr(event.item, "result_data", None):
            self.dismiss(event.item.result_data)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        lst = self.query_one("#search-overlay-list", ListView)
        if lst.highlighted_child and getattr(lst.highlighted_child, "result_data", None):
            self.dismiss(lst.highlighted_child.result_data)


# ── Main App ───────────────────────────────────────────────
class OriginTUI(App):
    """The complete Origin TUI workspace App."""

    CSS_PATH = "theme.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("tab", "next_view", "Next View"),
        Binding("shift+tab", "prev_view", "Prev View"),
        Binding("slash", "open_search", "Search", key_display="/"),
        Binding("ctrl+k", "open_palette", "Palette", key_display="Ctrl+K"),
        Binding("a", "accept_decision", "Accept"),
        Binding("r", "reject_decision", "Reject"),
        Binding("i", "toggle_inspector", "Toggle Inspector"),
    ]

    show_inspector_narrow = reactive(False)

    def __init__(self, workspace_root: Optional[str] = None, show_splash: bool = True) -> None:
        super().__init__()
        self.workspace_root = workspace_root or os.getcwd()
        self.show_splash = show_splash
        self._singularity_frame = 0
        self._pulse_phase = True
        
        self._decisions: list[Decision] = []
        self._all_decisions: list[Decision] = []
        self._memories: list[MemoryEntry] = []
        self._timeline: list[TimelineEvent] = []
        
        self._last_dir_state: dict[str, tuple[int, float]] = {}
        self._refresh_timer: Optional[Timer] = None
        self._pulse_timer: Optional[Timer] = None
        self._status_clear_timer: Optional[Timer] = None
        
        self.views_cycle = ["overview", "context", "decisions", "knowledge", "timeline"]
        self.current_view_idx = 0

    @property
    def is_narrow(self) -> bool:
        """Dynamically evaluate whether the layout drops below 80 columns."""
        return self.size.width < 80

    def compose(self) -> ComposeResult:
        yield Static("", id="header-bar")
        
        with ContentSwitcher(initial="overview", id="main-switcher"):
            yield OverviewView(id="overview")
            yield ContextView(id="context")
            yield DecisionsView(id="decisions")
            yield KnowledgeView(id="knowledge")
            yield TimelineView(id="timeline")
            
        yield Static("", id="status-message")
        yield Footer()

    def on_mount(self) -> None:
        if self.show_splash:
            self.push_screen(SplashScreen())

        self._load_all_data()
        self._render_all()
        self._update_layout_classes()

        # Check doctor inline output initially
        self.query_one("#overview", OverviewView).run_doctor_checks()

        # Polling for data refreshes
        self._refresh_timer = self.set_interval(2.0, self._poll_for_changes)
        # Pulse toggle
        self._pulse_timer = self.set_interval(1.0, self._toggle_pulse)

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
        self._render_header()
        
        # Get workspace metrics
        try:
            config = load_config(self.workspace_root)
            ws_name = config.workspace_name
        except Exception:
            ws_name = "Unknown"
            
        git = GitHelper(self.workspace_root)
        branch = git.get_current_branch() or "no git"

        # Dynamically compute recently active agents
        now = datetime.now(timezone.utc)
        recent_agents = set()
        for e in self._timeline:
            dt = e.created_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).total_seconds() < 7200:  # 2 hours
                recent_agents.add(e.originating_agent)
        active_agents = max(1, len(recent_agents))

        # 1. Update Overview View
        self.query_one("#overview", OverviewView).update_data(
            ws_name, branch, active_agents, self._all_decisions, self._memories, self._timeline
        )

        # 2. Update Context View
        try:
            bundle = use_cases.get_context_bundle(self.workspace_root)
        except Exception as e:
            bundle = f"Failed to load context bundle: {e}"
        self.query_one("#context", ContextView).update_data(bundle)

        # 3. Update Decisions View
        self.query_one("#decisions", DecisionsView).populate(self._all_decisions)

        # 4. Update Knowledge View
        self.query_one("#knowledge", KnowledgeView).populate(self._memories)

        # 5. Update Timeline View
        self.query_one("#timeline", TimelineView).populate(self._timeline, self._all_decisions)

    def _render_header(self) -> None:
        header = self.query_one("#header-bar", Static)
        try:
            config = load_config(self.workspace_root)
            ws_name = config.workspace_name
        except Exception:
            ws_name = "Unknown"

        git = GitHelper(self.workspace_root)
        branch = git.get_current_branch() or "no git"

        # Health glyph
        health_glyph, health_style = self._compute_health()
        singularity = SINGULARITY_FRAMES[self._singularity_frame % len(SINGULARITY_FRAMES)]

        # Get recent agents count
        now = datetime.now(timezone.utc)
        recent_agents = set()
        for e in self._timeline:
            dt = e.created_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).total_seconds() < 7200:
                recent_agents.add(e.originating_agent)
        agent_cnt = max(1, len(recent_agents))

        header.update(
            f"  [{health_style}]{health_glyph}[/]  "
            f"[bold #00ffd2]{ws_name}[/]  "
            f"[#0a4a42]⎇ {branch}[/]  "
            f"[bold #00ffd2]{singularity}[/]  "
            f"[dim #4d4d4d]Recently active: {agent_cnt}[/]"
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
        self._singularity_frame = (self._singularity_frame + 1) % len(SINGULARITY_FRAMES)
        
        # Only re-load data and re-render lists if files changed
        if self._check_dir_changes():
            self._load_all_data()
            self._render_all()
            # Also re-run doctor checks when data changes
            self.query_one("#overview", OverviewView).run_doctor_checks()
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

    def _toggle_pulse(self) -> None:
        self._pulse_phase = not self._pulse_phase
        panels = self.query(".panel")
        for panel in panels:
            panel.remove_class("pulse-a")
            panel.remove_class("pulse-b")
            if self._pulse_phase:
                panel.add_class("pulse-a")
            else:
                panel.add_class("pulse-b")

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
        if view_name in self.views_cycle:
            self.current_view_idx = self.views_cycle.index(view_name)
            self.query_one("#main-switcher", ContentSwitcher).current = view_name
            self._show_status(f"Switched view to {view_name.upper()}")

    def action_next_view(self) -> None:
        self.current_view_idx = (self.current_view_idx + 1) % len(self.views_cycle)
        self.switch_view(self.views_cycle[self.current_view_idx])

    def action_prev_view(self) -> None:
        self.current_view_idx = (self.current_view_idx - 1) % len(self.views_cycle)
        self.switch_view(self.views_cycle[self.current_view_idx])

    def action_open_search(self) -> None:
        self.push_screen(SearchOverlay(), self._handle_search_result)

    def _handle_search_result(self, result: Any) -> None:
        if not result:
            return
            
        if hasattr(result, "type") and result.type == "decision":
            self.switch_view("decisions")
            self.query_one("#decisions", DecisionsView).select_decision(result.id)
        elif hasattr(result, "type") and result.type == "memory":
            self.switch_view("knowledge")
            self.query_one("#knowledge", KnowledgeView).select_memory(result.category, result.key)

    def action_open_palette(self) -> None:
        self.push_screen(CommandPaletteModal(), self._handle_command_palette_action)

    def _handle_command_palette_action(self, action: Optional[str]) -> None:
        if not action:
            return

        if action.startswith("jump_"):
            target_view = action.split("_")[1]
            if target_view == "knowledge":
                target_view = "knowledge"
            self.switch_view(target_view)
        elif action == "accept_decision":
            self.action_accept_decision()
        elif action == "reject_decision":
            self.action_reject_decision()
        elif action == "search_workspace":
            self.action_open_search()
        elif action == "generate_export":
            try:
                dest = export_flat_file(self.workspace_root, "generic")
                self._show_status(f"Exported to {os.path.basename(dest)}")
            except Exception as e:
                self._show_status(f"Export failed: {e}")
        elif action == "run_doctor":
            self.switch_view("overview")
            self.query_one("#overview", OverviewView).run_doctor_checks()
        elif action == "quit":
            self.exit()

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
