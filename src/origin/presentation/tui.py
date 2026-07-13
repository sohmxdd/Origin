"""Origin TUI — Interactive terminal dashboard.

A read/act surface over the existing application layer.
Every action delegates to the same use_cases.py functions
the CLI and MCP server already call.
"""

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Footer,
    Input,
    ListItem,
    ListView,
    Static,
    Collapsible,
    TabbedContent,
    TabPane,
)
from textual.timer import Timer

from origin.application import use_cases
from origin.config import get_origin_dir, load_config
from origin.domain.models import Decision, MemoryEntry, TimelineEvent
from origin.infrastructure.database import ArtifactRepository
from origin.infrastructure.git import GitHelper


# ── Status glyphs ──────────────────────────────────────────
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


# ── Detail Modal ───────────────────────────────────────────
class DecisionDetailModal(ModalScreen[None]):
    """Modal showing full decision details."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(self, decision: Decision) -> None:
        super().__init__()
        self.decision = decision

    def compose(self) -> ComposeResult:
        dec = self.decision
        glyph = STATUS_GLYPHS.get(dec.status, "?")
        alts = ", ".join(dec.alternatives_considered) if dec.alternatives_considered else "None"
        files = ", ".join(dec.affected_files) if dec.affected_files else "None"
        superseded = f"\n  Superseded by: {dec.superseded_by}" if dec.superseded_by else ""

        content = (
            f"[bold #00ffd2]{glyph} {dec.title}[/]\n\n"
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

        with Vertical(id="detail-modal"):
            yield Static(content, markup=True)
            yield Static("\n[dim #4d4d4d]Press ESC to close[/]", markup=True)


# ── Doctor Detail Modal ────────────────────────────────────
class DoctorDetailModal(ModalScreen[None]):
    """Modal showing full doctor diagnostics."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(self, workspace_root: str) -> None:
        super().__init__()
        self.workspace_root = workspace_root

    def compose(self) -> ComposeResult:
        lines = self._run_doctor()
        content = "\n".join(lines)
        with Vertical(id="detail-modal"):
            yield Static(f"[bold #00ffd2]Origin Doctor Diagnostics[/]\n\n{content}", markup=True)
            yield Static("\n[dim #4d4d4d]Press ESC to close[/]", markup=True)

    def _run_doctor(self) -> list[str]:
        results: list[str] = []
        root = self.workspace_root
        origin_dir = os.path.join(root, ".origin")

        # Config check
        config_path = os.path.join(origin_dir, "config.yaml")
        if not os.path.exists(config_path):
            results.append("[#e25555][FAIL][/] config.yaml is missing.")
        else:
            try:
                config = load_config(root)
                if config.schema_version != "2.0":
                    results.append(f"[#e25555][FAIL][/] schema_version mismatch: expected '2.0', found '{config.schema_version}'.")
                else:
                    results.append(f"[#00ffd2][OK][/] config.yaml valid (Workspace: '{config.workspace_name}', Schema: '{config.schema_version}').")
            except Exception as e:
                results.append(f"[#e25555][FAIL][/] config.yaml failed: {e}")

        # DB check
        db_path = os.path.join(origin_dir, "workspace.db")
        if not os.path.exists(db_path):
            results.append("[#e25555][FAIL][/] workspace.db is missing.")
        else:
            try:
                repo = ArtifactRepository(db_path)
                repo.list_decisions()
                results.append("[#00ffd2][OK][/] workspace.db schema is readable.")
                # File staleness
                decisions = repo.list_decisions(status="active")
                for dec in decisions:
                    for f in dec.affected_files:
                        if not os.path.exists(os.path.join(root, f)):
                            results.append(f"[#e2a855][WARN][/] Stale file: '{f}' (Decision '{dec.id[:16]}…')")
            except Exception as e:
                results.append(f"[#e25555][FAIL][/] database check failed: {e}")

        # Git check
        if not os.path.isdir(os.path.join(root, ".git")):
            results.append("[#e2a855][WARN][/] Not a git repository.")
        else:
            results.append("[#00ffd2][OK][/] Git repository detected.")

        return results


# ── Main App ───────────────────────────────────────────────
class OriginTUI(App):
    """Origin interactive TUI dashboard."""

    CSS_PATH = "theme.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "view_detail", "View Detail"),
        Binding("a", "accept_decision", "Accept"),
        Binding("r", "reject_decision", "Reject"),
        Binding("slash", "open_search", "Search", key_display="/"),
        Binding("d", "doctor_detail", "Doctor"),
    ]

    def __init__(self, workspace_root: Optional[str] = None, show_splash: bool = True) -> None:
        super().__init__()
        self.workspace_root = workspace_root or os.getcwd()
        self.show_splash = show_splash
        self._singularity_frame = 0
        self._pulse_phase = True  # True = pulse-a, False = pulse-b
        self._search_active = False
        self._search_query = ""
        self._decisions: list[Decision] = []
        self._all_decisions: list[Decision] = []
        self._memories: list[MemoryEntry] = []
        self._timeline: list[TimelineEvent] = []
        self._last_dir_state: dict[str, tuple[int, float]] = {}
        self._refresh_timer: Optional[Timer] = None
        self._pulse_timer: Optional[Timer] = None
        self._status_clear_timer: Optional[Timer] = None

    @property
    def is_narrow(self) -> bool:
        """Dynamically evaluate narrow display layout size threshold."""
        return self.size.width < 100

    def compose(self) -> ComposeResult:
        yield Static("", id="header-bar")
        
        # Wide Layout
        with Horizontal(id="wide-layout"):
            with Vertical(id="decisions-panel-wide", classes="panel pulse-a"):
                yield Static("[bold #00ffd2]DECISIONS[/]", classes="panel-title", markup=True)
                yield Input(placeholder="Search… (ESC to clear)", id="search-input-wide")
                yield ListView(id="decisions-list-wide")
            with Vertical(id="right-column-wide"):
                with VerticalScroll(id="memory-panel-wide", classes="panel"):
                    yield Static("[bold #00ffd2]MEMORY[/]", classes="panel-title", markup=True)
                    yield Vertical(id="memory-content-wide")
                with VerticalScroll(id="timeline-panel-wide", classes="panel"):
                    yield Static("[bold #00ffd2]TIMELINE[/]", classes="panel-title", markup=True)
                    yield Vertical(id="timeline-content-wide")

        # Narrow Layout
        with TabbedContent(id="narrow-layout"):
            with TabPane("Decisions", id="decisions-tab"):
                with Vertical(id="decisions-panel-narrow", classes="panel"):
                    yield Static("[bold #00ffd2]DECISIONS[/]", classes="panel-title", markup=True)
                    yield Input(placeholder="Search… (ESC to clear)", id="search-input-narrow")
                    yield ListView(id="decisions-list-narrow")
            with TabPane("Memory", id="memory-tab"):
                with VerticalScroll(id="memory-panel-narrow", classes="panel"):
                    yield Static("[bold #00ffd2]MEMORY[/]", classes="panel-title", markup=True)
                    yield Vertical(id="memory-content-narrow")
            with TabPane("Timeline", id="timeline-tab"):
                with VerticalScroll(id="timeline-panel-narrow", classes="panel"):
                    yield Static("[bold #00ffd2]TIMELINE[/]", classes="panel-title", markup=True)
                    yield Vertical(id="timeline-content-narrow")

        yield Static("", id="status-message")
        yield Footer()

    def on_mount(self) -> None:
        """Load initial data and start timers."""
        if self.show_splash:
            self.push_screen(SplashScreen())
        
        self._load_all_data()
        self._render_all()
        
        # Initial check for resize/layout configuration
        self._update_layout_visibility()

        # Data refresh every 2 seconds
        self._refresh_timer = self.set_interval(2.0, self._poll_for_changes)
        # Pulse toggle every 1 second
        self._pulse_timer = self.set_interval(1.0, self._toggle_pulse)

    def on_resize(self, event=None) -> None:
        """Handle screen resize dynamically."""
        self._update_layout_visibility()

    def _update_layout_visibility(self) -> None:
        """Toggle wide vs narrow layouts based on size."""
        narrow = self.is_narrow
        self.query_one("#wide-layout").display = not narrow
        self.query_one("#narrow-layout").display = narrow

    # ── Data loading ───────────────────────────────────────
    def _load_all_data(self) -> None:
        """Load decisions, memory, timeline from repository."""
        try:
            origin_dir = get_origin_dir(self.workspace_root)
            db_path = os.path.join(origin_dir, "workspace.db")
            repo = ArtifactRepository(db_path)

            # Load all decisions
            self._all_decisions = []
            for status in ["active", "proposed", "superseded", "rejected"]:
                self._all_decisions.extend(repo.list_decisions(status=status))
            
            # Sort newest first
            self._all_decisions.sort(key=lambda d: d.created_at, reverse=True)

            self._memories = repo.list_memory()
            self._timeline = repo.list_timeline()
            self._timeline.sort(key=lambda e: e.created_at, reverse=True)

            # Apply search filter if active
            if self._search_active and self._search_query:
                q = self._search_query.lower()
                self._decisions = [
                    d for d in self._all_decisions
                    if q in d.title.lower() or q in d.rationale.lower() or q in d.id.lower()
                ]
            else:
                self._decisions = list(self._all_decisions)
        except Exception:
            self._decisions = []
            self._all_decisions = []
            self._memories = []
            self._timeline = []

    # ── Rendering ──────────────────────────────────────────
    def _render_all(self) -> None:
        """Re-render all panels."""
        self._render_header()
        self._render_decisions()
        self._render_memory()
        self._render_timeline()

    def _render_header(self) -> None:
        """Render header bar with workspace info, git branch, health, and singularity."""
        header = self.query_one("#header-bar", Static)
        try:
            config = load_config(self.workspace_root)
            ws_name = config.workspace_name
        except Exception:
            ws_name = "Unknown"

        git = GitHelper(self.workspace_root)
        branch = git.get_current_branch() or "no git"

        # Health indicator
        health_glyph, health_style = self._compute_health()

        # Singularity
        singularity = SINGULARITY_FRAMES[self._singularity_frame % len(SINGULARITY_FRAMES)]

        header.update(
            f"  [{health_style}]{health_glyph}[/]  "
            f"[bold #00ffd2]{ws_name}[/]  "
            f"[#0a4a42]⎇ {branch}[/]  "
            f"[bold #00ffd2]{singularity}[/]"
        )

    def _compute_health(self) -> tuple[str, str]:
        """Run lightweight doctor checks and return (glyph, style)."""
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

    def _render_decisions(self) -> None:
        """Render decisions list panel for both layouts."""
        for suffix in ["wide", "narrow"]:
            list_view = self.query_one(f"#decisions-list-{suffix}", ListView)
            list_view.clear()

            if not self._decisions:
                item = ListItem(Static("[#0a4a42]No decisions recorded yet. Try: origin decision add[/]", markup=True))
                item.data = None
                list_view.append(item)
                continue

            for dec in self._decisions:
                glyph = STATUS_GLYPHS.get(dec.status, "?")
                style = STATUS_STYLES.get(dec.status, "")
                short_id = dec.id[:20] + "…"
                
                title = dec.title
                if len(title) > 40:
                    title = title[:37] + "..."

                label_text = f"[{style}]{glyph}[/]  [{style}]{title}[/]  [#0a4a42]{dec.confidence:.2f}  {short_id}[/]"

                # Add supersession indicator
                if dec.superseded_by:
                    sup_short = dec.superseded_by[:16] + "…"
                    label_text += f"\n   [#0a4a42]└─ superseded by {sup_short}[/]"

                item = ListItem(Static(label_text, markup=True))
                item.data = dec  # Store decision reference
                list_view.append(item)

    def _render_memory(self) -> None:
        """Render memory panel with collapsible categories for both layouts."""
        for suffix in ["wide", "narrow"]:
            content = self.query_one(f"#memory-content-{suffix}", Vertical)
            content.remove_children()

            # Group by category
            groups: dict[str, list[MemoryEntry]] = defaultdict(list)
            for mem in self._memories:
                groups[mem.category].append(mem)

            if not groups:
                content.mount(Static("[#0a4a42]No memory entries recorded yet. Try: origin memory set <cat> <key> <val>[/]", markup=True))
                continue

            for category, entries in sorted(groups.items()):
                items_text = "\n".join(
                    f"  [#4d4d4d]{e.key}[/] = [#00ffd2]{e.value}[/]" for e in entries
                )
                collapsible = Collapsible(
                    Static(items_text, markup=True),
                    title=f"  {category} ({len(entries)})",
                    collapsed=False,
                )
                content.mount(collapsible)

    def _render_timeline(self) -> None:
        """Render timeline panel with recent events for both layouts."""
        for suffix in ["wide", "narrow"]:
            content = self.query_one(f"#timeline-content-{suffix}", Vertical)
            content.remove_children()

            if not self._timeline:
                content.mount(Static("[#0a4a42]No timeline events recorded yet.[/]", markup=True))
                continue

            # Show last 20 events
            for event in self._timeline[:20]:
                time_str = event.created_at.strftime("%m-%d %H:%M")
                event_icon = "📝" if "decision" in event.event_type else "🔧" if "memory" in event.event_type else "📦" if "commit" in event.event_type else "📋"
                line = f"[#0a4a42]{time_str}[/]  {event_icon}  [#4d4d4d]{event.summary}[/]"
                content.mount(Static(line, markup=True, classes="timeline-event"))

    # ── Polling ────────────────────────────────────────────
    def _poll_for_changes(self) -> None:
        """Check filesystem for changes and refresh if needed."""
        # Rotate singularity glyph
        self._singularity_frame = (self._singularity_frame + 1) % len(SINGULARITY_FRAMES)

        changed = self._check_dir_changes()
        if changed:
            self._load_all_data()
            self._render_all()
        else:
            # Still update header for singularity rotation
            self._render_header()

    def _check_dir_changes(self) -> bool:
        """Check if any artifact directory has changed since last check."""
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

    # ── Pulse animation ────────────────────────────────────
    def _toggle_pulse(self) -> None:
        """Toggle pulse CSS class on the focused panel."""
        self._pulse_phase = not self._pulse_phase
        panels = self.query(".panel")
        for panel in panels:
            panel.remove_class("pulse-a")
            panel.remove_class("pulse-b")
            if self._pulse_phase:
                panel.add_class("pulse-a")
            else:
                panel.add_class("pulse-b")

    # ── Status message ─────────────────────────────────────
    def _show_status(self, message: str, duration: float = 3.0) -> None:
        """Show a temporary status message in the status bar."""
        status = self.query_one("#status-message", Static)
        status.update(f"[#e2a855]{message}[/]")
        # Clear after duration
        if self._status_clear_timer:
            self._status_clear_timer.stop()
        self._status_clear_timer = self.set_timer(duration, self._clear_status)

    def _clear_status(self) -> None:
        """Clear the status message."""
        status = self.query_one("#status-message", Static)
        status.update("")

    # ── Keybinding actions ─────────────────────────────────
    def _get_selected_decision(self) -> Optional[Decision]:
        """Get the currently highlighted decision from the active layout list."""
        suffix = "narrow" if self.is_narrow else "wide"
        list_view = self.query_one(f"#decisions-list-{suffix}", ListView)
        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if hasattr(item, "data"):
                return item.data
        return None

    def action_cursor_down(self) -> None:
        """Move cursor down in the active decisions list."""
        suffix = "narrow" if self.is_narrow else "wide"
        list_view = self.query_one(f"#decisions-list-{suffix}", ListView)
        list_view.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the active decisions list."""
        suffix = "narrow" if self.is_narrow else "wide"
        list_view = self.query_one(f"#decisions-list-{suffix}", ListView)
        list_view.action_cursor_up()

    def action_view_detail(self) -> None:
        """Show detail modal for the selected decision."""
        dec = self._get_selected_decision()
        if dec:
            self.push_screen(DecisionDetailModal(dec))
        else:
            self._show_status("No decision selected.")

    def action_accept_decision(self) -> None:
        """Accept the selected proposed decision."""
        dec = self._get_selected_decision()
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
        """Reject the selected proposed decision."""
        dec = self._get_selected_decision()
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

    def action_open_search(self) -> None:
        """Toggle search input visibility."""
        suffix = "narrow" if self.is_narrow else "wide"
        search_input = self.query_one(f"#search-input-{suffix}", Input)
        if self._search_active:
            # Clear search
            self._search_active = False
            self._search_query = ""
            search_input.add_class("hidden")
            search_input.value = ""
            self._decisions = list(self._all_decisions)
            self._render_decisions()
            self._show_status("Search cleared.")
        else:
            self._search_active = True
            search_input.remove_class("hidden")
            search_input.display = True
            search_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission."""
        if event.input.id in ["search-input-wide", "search-input-narrow"]:
            self._search_query = event.value.strip()
            if self._search_query:
                q = self._search_query.lower()
                self._decisions = [
                    d for d in self._all_decisions
                    if q in d.title.lower() or q in d.rationale.lower() or q in d.id.lower()
                ]
                self._render_decisions()
                self._show_status(f"Found {len(self._decisions)} result(s) for '{self._search_query}'.")
                # Refocus list
                suffix = "narrow" if self.is_narrow else "wide"
                list_view = self.query_one(f"#decisions-list-{suffix}", ListView)
                list_view.focus()
            else:
                self._search_active = False
                self._decisions = list(self._all_decisions)
                self._render_decisions()

    def on_key(self, event) -> None:
        """Handle ESC to clear search."""
        if event.key == "escape" and self._search_active:
            self._search_active = False
            self._search_query = ""
            for suffix in ["wide", "narrow"]:
                search_input = self.query_one(f"#search-input-{suffix}", Input)
                search_input.add_class("hidden")
                search_input.value = ""
            self._decisions = list(self._all_decisions)
            self._render_decisions()
            self._show_status("Search cleared.")
            # Refocus list
            suffix = "narrow" if self.is_narrow else "wide"
            list_view = self.query_one(f"#decisions-list-{suffix}", ListView)
            list_view.focus()
            event.prevent_default()

    def action_doctor_detail(self) -> None:
        """Show full doctor diagnostics in a modal."""
        self.push_screen(DoctorDetailModal(self.workspace_root))


def run_tui(workspace_root: Optional[str] = None) -> None:
    """Launch the Origin TUI dashboard."""
    app = OriginTUI(workspace_root=workspace_root)
    app.run()
