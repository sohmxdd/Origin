"""Demo script that sets up a populated workspace and launches the TUI.

Usage:
    python demo_tui.py

This creates a demo_workspace directory with seeded decisions, memory,
and timeline events, then opens the Origin TUI dashboard against it.
"""

import os
import shutil
import stat
import subprocess
import sys


def remove_readonly(func, path, _):
    """Handle read-only files on Windows (git objects)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def run_cli(args: list[str], cwd: str) -> str:
    """Run an origin CLI command."""
    result = subprocess.run(
        [sys.executable, "-m", "origin.presentation.cli"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> None:
    """Set up demo workspace and launch TUI."""
    root_dir = os.path.abspath(os.path.dirname(__file__))
    workspace_dir = os.path.join(root_dir, "demo_workspace")

    # Clean up previous runs
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir, onexc=remove_readonly)
    os.makedirs(workspace_dir, exist_ok=True)

    # Init git repo
    subprocess.run(["git", "init"], cwd=workspace_dir, capture_output=True, check=True)
    dummy_file = os.path.join(workspace_dir, "dummy.txt")
    with open(dummy_file, "w", encoding="utf-8") as f:
        f.write("Initial project files")
    subprocess.run(["git", "add", "dummy.txt"], cwd=workspace_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace_dir, capture_output=True, check=True)

    print("Setting up demo workspace...")

    # Init Origin
    run_cli(["init", "--name", "DemoApp"], cwd=workspace_dir)

    # Add some proposed decisions
    run_cli([
        "decision", "add",
        "--title", "Use PostgreSQL for primary data store",
        "--rationale", "Strong ACID compliance and relational query support.",
        "--confidence", "0.9",
        "--alternative", "MongoDB",
        "--alternative", "SQLite",
        "--file", "src/db/connection.py",
        "--propose",
    ], cwd=workspace_dir)

    run_cli([
        "decision", "add",
        "--title", "Adopt FastAPI as the web framework",
        "--rationale", "Async-first, OpenAPI generation, and great performance.",
        "--confidence", "0.95",
        "--alternative", "Flask",
        "--alternative", "Django",
        "--file", "src/api/main.py",
        "--propose",
    ], cwd=workspace_dir)

    # Add an active decision
    run_cli([
        "decision", "add",
        "--title", "Use Docker for containerized deployments",
        "--rationale", "Consistent environments across dev, staging, and production.",
        "--confidence", "1.0",
        "--alternative", "Bare metal",
        "--file", "Dockerfile",
        "--file", "docker-compose.yml",
    ], cwd=workspace_dir)

    # Add some memory entries
    run_cli(["memory", "set", "tech_stack", "language", "python"], cwd=workspace_dir)
    run_cli(["memory", "set", "tech_stack", "database", "postgresql"], cwd=workspace_dir)
    run_cli(["memory", "set", "convention", "testing", "pytest with fixtures"], cwd=workspace_dir)
    run_cli(["memory", "set", "deployment", "platform", "docker-compose"], cwd=workspace_dir)

    # Export context
    run_cli(["export", "--target", "claude-code"], cwd=workspace_dir)

    print("Demo workspace ready! Launching TUI...\n")
    print("Keys: ↑/↓ or j/k to navigate, Enter to view, a to accept, r to reject, / to search, d for doctor, q to quit\n")

    # Launch TUI
    subprocess.run(
        [sys.executable, "-m", "origin.presentation.cli", "tui"],
        cwd=workspace_dir,
    )


if __name__ == "__main__":
    main()
