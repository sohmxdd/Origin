"""Demo script running the Origin v1 scenario end-to-end.

Simulates workspace initialization, recording decisions, exporting to CLAUDE.md,
superseding decisions, and inspecting the resulting metadata history.
"""

import os
import shutil
import subprocess
import sys


def print_step(title: str) -> None:
    """Print a step header to the console."""
    border = "=" * 60
    print(f"\n{border}")
    print(f" DEMO STEP: {title}")
    print(f"{border}\n")


def run_cli_command(args: list[str], cwd: str, input_str: str = "") -> str:
    """Run an Origin CLI command in the target directory."""
    env = os.environ.copy()
    # Add 'src' directory to python path so it runs without installation
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
    env["PYTHONPATH"] = src_dir

    # Use sys.executable to run CLI module
    cmd = [sys.executable, "-m", "origin.presentation.cli"] + args
    print(f"Executing: python -m origin.presentation.cli {' '.join(args)}")

    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        input=input_str,
    )

    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}", file=sys.stderr)
        print(f"Error output:\n{result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

    return result.stdout


def main() -> None:
    """Run the end-to-end scenario."""
    # Define paths
    root_dir = os.path.abspath(os.path.dirname(__file__))
    workspace_dir = os.path.join(root_dir, "demo_workspace")

    # Clean up previous runs
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir)

    # Initialize a git repository and make a dummy commit so git-integration paths function
    subprocess.run(["git", "init"], cwd=workspace_dir, capture_output=True, check=True)
    dummy_file = os.path.join(workspace_dir, "dummy.txt")
    with open(dummy_file, "w", encoding="utf-8") as f:
        f.write("Initial project files")
    subprocess.run(["git", "add", "dummy.txt"], cwd=workspace_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace_dir, capture_output=True, check=True)

    print_step("1. Initialize Origin Workspace")
    # Initialize a new workspace named 'DemoApp'
    init_out = run_cli_command(["init", "--name", "DemoApp"], cwd=workspace_dir)
    print(init_out)

    print_step("2. Record first architectural decision")
    # Add a decision: Use Postgres over MongoDB
    add_out = run_cli_command(
        [
            "decision",
            "add",
            "--title",
            "Use PostgreSQL over MongoDB for the data layer",
            "--rationale",
            "We need strong ACID guarantees, transaction integrity, and robust relational querying support.",
            "--confidence",
            "0.9",
            "--alternative",
            "MongoDB",
            "--alternative",
            "SQLite",
            "--file",
            "src/db/connection.py",
        ],
        cwd=workspace_dir,
    )
    print(add_out)

    # Extract decision ID from output
    # Sample output: "Successfully recorded Decision dec_01HXYZ...: '...'"
    dec_id = ""
    for line in add_out.splitlines():
        if "Successfully recorded Decision" in line:
            parts = line.split("Decision ")
            if len(parts) > 1:
                dec_id = parts[1].split(":")[0].strip()
    
    if not dec_id:
        print("Error: Could not extract decision ID from output.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracted Decision ID: {dec_id}")

    print_step("3. Export context to CLAUDE.md")
    # Export flat-file context block to CLAUDE.md
    export_out = run_cli_command(["export", "--target", "claude-code"], cwd=workspace_dir)
    print(export_out)

    print_step("4. Inspect the generated CLAUDE.md (Simulating fresh agent session)")
    claude_md_path = os.path.join(workspace_dir, "CLAUDE.md")
    with open(claude_md_path, "r", encoding="utf-8") as f:
        print(f.read())

    print_step("5. Record a second decision superseding the first")
    # Supersede PostgreSQL choice with PostgreSQL + pgvector
    supersede_out = run_cli_command(
        [
            "decision",
            "supersede",
            dec_id,
            "--title",
            "PostgreSQL + pgvector for embedding support",
            "--rationale",
            "The product requirements changed, needing vector search features. pgvector is a reliable SQL solution.",
            "--confidence",
            "0.95",
            "--alternative",
            "Pinecone",
            "--alternative",
            "ChromaDB",
            "--file",
            "src/db/connection.py",
            "--file",
            "src/embeddings/store.py",
        ],
        cwd=workspace_dir,
    )
    print(supersede_out)

    print_step("6. List decisions displaying the supersession chain")
    # List active decisions
    active_out = run_cli_command(["decision", "list", "--status", "active"], cwd=workspace_dir)
    print(active_out)

    # List superseded decisions
    superseded_out = run_cli_command(["decision", "list", "--status", "superseded"], cwd=workspace_dir)
    print(superseded_out)

    print_step("7. Refresh CLAUDE.md and verify the updated context")
    # Export flat-file context block again
    run_cli_command(["export", "--target", "claude-code"], cwd=workspace_dir)
    with open(claude_md_path, "r", encoding="utf-8") as f:
        print(f.read())

    print_step("8. Exercise Memory Entry Set/Get and Search")
    # Set memory
    mem_set_out = run_cli_command(["memory", "set", "tech_stack", "database", "postgresql"], cwd=workspace_dir)
    print(mem_set_out)

    # Get memory
    mem_get_out = run_cli_command(["memory", "get", "tech_stack", "database"], cwd=workspace_dir)
    print(f"Retrieved memory value: {mem_get_out.strip()}")

    # Search artifacts
    search_out = run_cli_command(["search", "postgresql"], cwd=workspace_dir)
    print(search_out)

    print_step("9. Run Origin doctor diagnostics")
    doctor_out = run_cli_command(["doctor"], cwd=workspace_dir)
    print(doctor_out)

    print("\n" + "=" * 60)
    print(" DEMO COMPLETED SUCCESSFULLY!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
