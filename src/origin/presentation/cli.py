"""Typer command-line interface for Origin.

Provides user commands to interact with Origin's memory and decision log.
"""

import json
import os
import sys
from typing import List, Optional
import typer

from rich.console import Console
from rich.table import Table

from origin.application import use_cases
from origin.exceptions import OriginError, WorkspaceNotInitializedError
from origin.adapters.flat_file import export_flat_file

app = typer.Typer(
    name="origin",
    help="Origin: A local-first, git-friendly persistent memory layer for AI agents.",
)
decision_app = typer.Typer(name="decision", help="Manage architecture decision records (ADR).")
memory_app = typer.Typer(name="memory", help="Manage project conventions and stack memory.")

app.add_typer(decision_app)
app.add_typer(memory_app)


def find_workspace_root() -> str:
    """Traverse upwards to find the first directory containing a .origin folder.

    Defaults to the current working directory if not found.
    """
    curr = os.path.abspath(os.getcwd())
    while True:
        if os.path.isdir(os.path.join(curr, ".origin")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:  # Reached filesystem root
            break
        curr = parent
    return os.getcwd()


def prompt_decision_interactive(
    title: Optional[str],
    rationale: Optional[str],
    confidence: Optional[float],
    alternatives: Optional[List[str]],
    files: Optional[List[str]],
) -> tuple[str, str, float, List[str], List[str]]:
    """Prompt the user interactively for missing decision fields."""
    typer.echo("Recording architectural decision...")

    if not title:
        title = typer.prompt("Decision Title").strip()
        while not title:
            typer.echo("Error: Title cannot be empty.")
            title = typer.prompt("Decision Title").strip()

    if not rationale:
        rationale = typer.prompt("Rationale (Why was this decision made?)").strip()
        while not rationale:
            typer.echo("Error: Rationale cannot be empty.")
            rationale = typer.prompt("Rationale (Why was this decision made?)").strip()

    if confidence is None:
        confidence_val: float = typer.prompt(
            "Confidence level (0.0 to 1.0)", type=float, default=1.0
        )
        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence_val))

    if not alternatives:
        alternatives = []
        typer.echo("Enter alternatives considered (leave empty to finish):")
        while True:
            alt = typer.prompt("Alternative", default="", show_default=False).strip()
            if not alt:
                break
            alternatives.append(alt)

    if not files:
        files = []
        typer.echo("Enter files affected (leave empty to finish):")
        while True:
            f = typer.prompt("Affected File", default="", show_default=False).strip()
            if not f:
                break
            files.append(f)

    return title, rationale, confidence, alternatives, files


@app.command("init")
def init(
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name for the workspace. Defaults to folder name."
    ),
    with_hooks: bool = typer.Option(
        False, "--with-hooks", help="Install git pre-commit hook to auto-run origin export."
    ),
    import_stack: bool = typer.Option(
        False, "--import", help="Import stack recommendations from project files during setup."
    ),
) -> None:
    """Initialize a new Origin workspace in the current directory."""
    cwd = os.getcwd()
    workspace_name = name or os.path.basename(os.path.abspath(cwd))

    try:
        use_cases.init_workspace(cwd, workspace_name, with_hooks)
        typer.secho(
            f"Initialized empty Origin workspace in {os.path.join(cwd, '.origin/')}",
            fg=typer.colors.GREEN,
        )
        if with_hooks:
            typer.secho("Git pre-commit hooks successfully installed.", fg=typer.colors.CYAN)

        if import_stack:
            typer.echo("\nScanning for project manifest recommendations...")
            recommendations = use_cases.import_conventions(cwd)
            if not recommendations:
                typer.secho("No clear tech stack recommendations found.", fg=typer.colors.YELLOW)
            else:
                typer.secho(f"Found {len(recommendations)} recommendations. Reviewing interactively:", fg=typer.colors.CYAN)
                for rec in recommendations:
                    cat = rec["category"]
                    key = rec["key"]
                    val = rec["value"]
                    confirm = typer.confirm(f"Save memory entry: {cat}.{key} = '{val}'?")
                    if confirm:
                        use_cases.set_memory(cwd, cat, key, val, originating_agent="human")
                        typer.secho(f"Saved: {cat}.{key} = '{val}'", fg=typer.colors.GREEN)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@decision_app.command("add")
def decision_add(
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Title of the decision."),
    rationale: Optional[str] = typer.Option(None, "--rationale", "-r", help="Why it was made."),
    confidence: Optional[float] = typer.Option(None, "--confidence", "-c", help="Confidence 0.0-1.0."),
    alternatives: Optional[List[str]] = typer.Option(
        None, "--alternative", "-a", help="Alternatives considered. Can specify multiple times."
    ),
    files: Optional[List[str]] = typer.Option(
        None, "--file", "-f", help="Affected file path. Can specify multiple times."
    ),
    propose: bool = typer.Option(False, "--propose", help="Record decision as proposed instead of active."),
) -> None:
    """Record a new architectural decision (interactive by default)."""
    root = find_workspace_root()
    status = "proposed" if propose else "active"
    try:
        title, rationale, confidence, alternatives, files = prompt_decision_interactive(
            title, rationale, confidence, alternatives, files
        )

        dec = use_cases.add_decision(
            workspace_root=root,
            title=title,
            rationale=rationale,
            alternatives_considered=alternatives,
            affected_files=files,
            confidence=confidence,
            originating_agent="human",
            status=status,
        )

        typer.secho(f"Successfully recorded Decision {dec.id} ({status}): '{dec.title}'", fg=typer.colors.GREEN)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@decision_app.command("accept")
def decision_accept(
    decision_id: str = typer.Argument(..., help="The ID of the proposed decision to accept.")
) -> None:
    """Accept and activate a proposed decision."""
    root = find_workspace_root()
    try:
        dec = use_cases.accept_decision(root, decision_id, agent="human")
        typer.secho(f"Successfully accepted proposed Decision {dec.id}: '{dec.title}'", fg=typer.colors.GREEN)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@decision_app.command("reject")
def decision_reject(
    decision_id: str = typer.Argument(..., help="The ID of the proposed decision to reject.")
) -> None:
    """Reject a proposed decision."""
    root = find_workspace_root()
    try:
        dec = use_cases.reject_decision(root, decision_id, agent="human")
        typer.secho(f"Successfully rejected proposed Decision {dec.id}: '{dec.title}'", fg=typer.colors.RED)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@decision_app.command("list")
def decision_list(
    status: Optional[str] = typer.Option(
        "active", "--status", "-s", help="Filter by status (active, superseded, proposed, or rejected)."
    ),
    affects: Optional[str] = typer.Option(
        None, "--affects", help="Filter decisions affecting a specific file."
    )
) -> None:
    """List recorded decisions in this workspace."""
    root = find_workspace_root()
    try:
        config = use_cases.load_config(root)
        origin_dir = os.path.join(root, ".origin")
        from origin.infrastructure.database import ArtifactRepository
        repo = ArtifactRepository(os.path.join(origin_dir, "workspace.db"))

        decisions = repo.list_decisions(status=status)
        if affects:
            decisions = [dec for dec in decisions if affects in dec.affected_files]

        if not decisions:
            typer.echo(f"No decisions found with status '{status}'" + (f" affecting '{affects}'" if affects else "") + ".")
            return

        console = Console()
        table = Table(title=f"Origin Decisions ({status})")
        table.add_column("ID", style="dim", width=30)
        table.add_column("Title", style="bold cyan")
        table.add_column("Confidence", justify="right")
        table.add_column("Details", style="green")

        for dec in decisions:
            superseded_str = f"\nSuperseded by: {dec.superseded_by}" if dec.superseded_by else ""
            affected_str = f"Files: {', '.join(dec.affected_files)}" if dec.affected_files else "No files listed"
            table.add_row(
                dec.id,
                dec.title,
                f"{dec.confidence:.2f}",
                affected_str + superseded_str
            )
        console.print(table)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@decision_app.command("supersede")
def decision_supersede(
    old_id: str = typer.Argument(..., help="The ID of the decision to supersede."),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Title of the new decision."),
    rationale: Optional[str] = typer.Option(None, "--rationale", "-r", help="Why it was made."),
    confidence: Optional[float] = typer.Option(None, "--confidence", "-c", help="Confidence 0.0-1.0."),
    alternatives: Optional[List[str]] = typer.Option(
        None, "--alternative", "-a", help="Alternatives considered. Can specify multiple times."
    ),
    files: Optional[List[str]] = typer.Option(
        None, "--file", "-f", help="Affected file path. Can specify multiple times."
    ),
) -> None:
    """Supersede an old decision with a new one."""
    root = find_workspace_root()
    try:
        title, rationale, confidence, alternatives, files = prompt_decision_interactive(
            title, rationale, confidence, alternatives, files
        )

        new_dec = use_cases.supersede_decision(
            workspace_root=root,
            old_decision_id=old_id,
            title=title,
            rationale=rationale,
            alternatives_considered=alternatives,
            affected_files=files,
            confidence=confidence,
            originating_agent="human",
        )

        typer.secho(
            f"Successfully superseded {old_id} with Decision {new_dec.id}: '{new_dec.title}'",
            fg=typer.colors.GREEN,
        )
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@memory_app.command("set")
def memory_set(
    category: str = typer.Argument(
        ...,
        help="Memory category (architecture, convention, tech_stack, glossary, deployment).",
    ),
    key: str = typer.Argument(..., help="Key namespace identifier."),
    value: str = typer.Argument(..., help="Content associated with the key."),
) -> None:
    """Store or update a project memory value."""
    root = find_workspace_root()
    try:
        entry = use_cases.set_memory(
            workspace_root=root,
            category=category,
            key=key,
            value=value,
            originating_agent="human",
        )
        typer.secho(
            f"Saved Memory Entry [{entry.id}]: {category}.{key} = '{value}'",
            fg=typer.colors.GREEN,
        )
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@memory_app.command("get")
def memory_get(
    category: str = typer.Argument(..., help="Memory category."),
    key: str = typer.Argument(..., help="Key identifier."),
) -> None:
    """Retrieve a project memory value."""
    root = find_workspace_root()
    try:
        entry = use_cases.get_memory(root, category, key)
        if not entry:
            typer.secho(f"No memory entry found for {category}.{key}", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)
        typer.echo(entry.value)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("context")
def context() -> None:
    """Print the current compiled context bundle to stdout."""
    root = find_workspace_root()
    try:
        bundle = use_cases.get_context_bundle(root)
        typer.echo(bundle)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("search")
def search(query: str = typer.Argument(..., help="Keyword query string.")) -> None:
    """Search across active decisions and memory entries."""
    root = find_workspace_root()
    try:
        results = use_cases.search_artifacts(root, query)
        if not results:
            typer.echo("No matching artifacts found.")
            return

        console = Console()
        table = Table(title=f"Origin Search Results: '{query}'")
        table.add_column("Type", style="bold magenta")
        table.add_column("ID / Key", style="dim", width=30)
        table.add_column("Title / Value", style="cyan")
        table.add_column("Status", justify="center")

        for art in results:
            if art.type == "decision":
                status_style = "green" if art.status == "active" else "yellow" if art.status == "proposed" else "red"
                table.add_row("Decision", art.id, art.title, f"[{status_style}]{art.status}[/{status_style}]")
            elif art.type == "memory":
                table.add_row("Memory", f"{art.category}.{art.key}", art.value, "[green]active[/green]")
        console.print(table)
    except OriginError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("export")
def export(
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="Export target format (claude-code, cursor, generic).",
    )
) -> None:
    """Refresh and export flat-file context files."""
    root = find_workspace_root()
    try:
        # Sync git commits to record trailers
        use_cases.sync_git_commits(root)
        dest = export_flat_file(root, target)
        typer.secho(f"Successfully exported context to {dest}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Automatically repair index drift and refresh mirrors.")
) -> None:
    """Sanity check the integrity, configurations, and schema of the workspace."""
    root = find_workspace_root()
    origin_dir = os.path.join(root, ".origin")

    if not os.path.isdir(origin_dir):
        typer.secho("Error: Not inside an Origin workspace (no .origin folder found).", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if fix:
        typer.secho("Fixing workspace index and mirrors...", fg=typer.colors.CYAN)
        try:
            config = use_cases.load_config(root)
            from origin.infrastructure.database import ArtifactRepository
            repo = ArtifactRepository(os.path.join(origin_dir, "workspace.db"))
            repo.sync_index(force=True)

            from origin.infrastructure.mirror import MirrorWriter
            mirror = MirrorWriter(origin_dir, config.workspace_name, config.schema_version)
            mirror.refresh_all(repo)

            export_flat_file(root, "generic")
            export_flat_file(root, "claude-code")
            typer.secho("[OK] Rebuilt SQLite index cache and regenerated mirrors.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Error executing fix: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    errors = 0
    warnings = 0

    # 1. Check config.yaml
    config_path = os.path.join(origin_dir, "config.yaml")
    if not os.path.exists(config_path):
        typer.secho("[FAIL] config.yaml is missing.", fg=typer.colors.RED)
        errors += 1
    else:
        try:
            config = use_cases.load_config(root)
            if config.schema_version != "2.0":
                typer.secho(
                    f"[FAIL] schema_version mismatch: expected '2.0', found '{config.schema_version}'. Run 'origin migrate' to upgrade.",
                    fg=typer.colors.RED,
                )
                errors += 1
            else:
                typer.secho(
                    f"[OK] config.yaml is valid (Workspace: '{config.workspace_name}', Schema: '{config.schema_version}').",
                    fg=typer.colors.GREEN,
                )
        except Exception as e:
            typer.secho(f"[FAIL] config.yaml failed validation: {e}", fg=typer.colors.RED)
            errors += 1

    # 2. Check SQLite db
    db_path = os.path.join(origin_dir, "workspace.db")
    if not os.path.exists(db_path):
        typer.secho("[FAIL] SQLite workspace.db file is missing.", fg=typer.colors.RED)
        errors += 1
    else:
        try:
            from origin.infrastructure.database import ArtifactRepository
            repo = ArtifactRepository(db_path)
            repo.list_decisions()
            typer.secho("[OK] SQLite workspace.db schema is readable and valid.", fg=typer.colors.GREEN)

            # Check affected files staleness
            decisions = repo.list_decisions(status="active")
            for dec in decisions:
                for f in dec.affected_files:
                    full_f_path = os.path.join(root, f)
                    if not os.path.exists(full_f_path):
                        typer.secho(
                            f"[WARN] Stale file reference: Decision '{dec.id}' affects file '{f}' which does not exist.",
                            fg=typer.colors.YELLOW,
                        )
                        warnings += 1
        except Exception as e:
            typer.secho(f"[FAIL] SQLite database integrity check failed: {e}", fg=typer.colors.RED)
            errors += 1

    # 3. Check Git Status
    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        typer.secho("[WARN] Workspace root is not a git repository.", fg=typer.colors.YELLOW)
        warnings += 1
    else:
        typer.secho("[OK] Git repository detected.", fg=typer.colors.GREEN)

    if errors > 0:
        typer.secho(f"\nDoctor found {errors} integrity issue(s) and {warnings} warning(s).", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)
    else:
        if warnings > 0:
            typer.secho(f"\nWorkspace is healthy with {warnings} warnings.", fg=typer.colors.YELLOW, bold=True)
        else:
            typer.secho("\nWorkspace is healthy and ready to go!", fg=typer.colors.GREEN, bold=True)


@app.command("migrate")
def migrate() -> None:
    """Migrate a v1.0 SQLite-only workspace to a v2.0 filesystem-first workspace."""
    root = find_workspace_root()
    try:
        use_cases.migrate_workspace(root)
        typer.secho("Successfully migrated workspace to schema version 2.0!", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Migration failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("connect")
def connect(
    target: str = typer.Argument(
        ...,
        help="Target editor/client to connect with (claude-code, cursor)."
    )
) -> None:
    """Export context and auto-configure MCP server connection for your editor."""
    root = find_workspace_root()
    try:
        export_target = "claude-code" if target == "claude-code" else "cursor"
        dest = export_flat_file(root, export_target)
        typer.secho(f"1. Context successfully exported to {dest}", fg=typer.colors.GREEN)

        import shutil
        mcp_bin = shutil.which("origin-mcp") or "origin-mcp"

        if target == "claude-code":
            config_path = os.path.expanduser("~/.claude.json")
            mcp_config = {
                "command": mcp_bin,
                "args": []
            }

            config_data = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                except Exception:
                    pass

            if "mcpServers" not in config_data:
                config_data["mcpServers"] = {}

            config_data["mcpServers"]["origin-memory"] = mcp_config

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)

            typer.secho(f"2. Auto-configured MCP server in {config_path}", fg=typer.colors.GREEN)
            typer.secho("Ready to use! Start Claude Code and it will auto-load origin tools.", fg=typer.colors.CYAN)

        elif target == "cursor":
            cursorrules_path = os.path.join(root, ".cursorrules")
            typer.secho("2. Cursor integration instructions:", fg=typer.colors.CYAN, bold=True)
            typer.echo("Open Cursor -> Settings -> Features -> MCP.")
            typer.echo("Add a new MCP server with:")
            typer.echo("  Name: origin-memory")
            typer.echo("  Type: command")
            typer.echo(f"  Command: {mcp_bin}")
            typer.secho(f"\nYour .cursorrules has been populated at {cursorrules_path}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"Unsupported connection target: {target}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    except Exception as e:
        typer.secho(f"Connection failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command("mcp-config")
def mcp_config() -> None:
    """Print registration configuration snippet for Claude Code or Claude Desktop."""
    snippet = {
        "mcpServers": {
            "origin-memory": {
                "command": "origin-mcp",
                "args": [],
                "env": {}
            }
        }
    }
    
    typer.echo("\nTo register the Origin MCP server, add this configuration snippet:")
    typer.secho("\nClaude Code (~/.claude.json) or Claude Desktop Configuration:", fg=typer.colors.CYAN, bold=True)
    typer.echo(json.dumps(snippet, indent=2))
    typer.echo("\nInstructions:")
    typer.echo("1. Ensure 'origin-cli' package is installed in your python environment.")
    typer.echo("2. Verify that 'origin-mcp' is available in your system path by running 'origin-mcp --help'.")
    typer.echo("3. If it is in a virtualenv, specify the absolute path to 'origin-mcp' in the 'command' field above.\n")


@app.command("tui")
def tui() -> None:
    """Launch the interactive Origin TUI dashboard."""
    root = find_workspace_root()
    origin_dir = os.path.join(root, ".origin")
    if not os.path.isdir(origin_dir):
        typer.secho("Error: Not inside an Origin workspace (no .origin folder found).", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    from origin.presentation.tui import run_tui
    run_tui(workspace_root=root)


def main() -> None:
    """Entry point for project script command."""
    app()


if __name__ == "__main__":
    main()
