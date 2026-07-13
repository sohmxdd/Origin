"""Tests for the Typer CLI presentation layer."""

import json
import os
from typing import Any
import pytest
from typer.testing import CliRunner

from origin.presentation.cli import app


@pytest.fixture
def cli_runner(tmp_path: Any) -> CliRunner:
    """Fixture returning CliRunner and runs in a temporary directory."""
    runner = CliRunner()
    # Change current working directory to tmp_path for isolation
    old_cwd = os.getcwd()
    os.chdir(str(tmp_path))
    yield runner
    os.chdir(old_cwd)


def test_cli_init(cli_runner: CliRunner) -> None:
    """Verify that 'origin init' configures the workspace."""
    result = cli_runner.invoke(app, ["init", "--name", "MyProject"])
    assert result.exit_code == 0
    assert "Initialized empty Origin workspace" in result.stdout
    assert os.path.exists(".origin/config.yaml")
    assert os.path.exists(".origin/workspace.db")


def test_cli_decision_add_and_list(cli_runner: CliRunner) -> None:
    """Verify recording and listing decisions via CLI."""
    cli_runner.invoke(app, ["init"])

    result = cli_runner.invoke(
        app,
        [
            "decision",
            "add",
            "--title",
            "Pick Postgres",
            "--rationale",
            "Relational data model",
            "--confidence",
            "0.9",
            "--alternative",
            "MongoDB",
            "--alternative",
            "MySQL",
            "--file",
            "db.py",
        ],
    )
    assert result.exit_code == 0
    assert "Successfully recorded Decision" in result.stdout

    # List active
    list_result = cli_runner.invoke(app, ["decision", "list"])
    assert list_result.exit_code == 0
    assert "Pick Postgres" in list_result.stdout
    assert "0.90" in list_result.stdout


def test_cli_decision_supersede(cli_runner: CliRunner) -> None:
    """Verify superseding a decision via CLI."""
    cli_runner.invoke(app, ["init"])

    # Create original decision
    cli_runner.invoke(
        app,
        [
            "decision",
            "add",
            "--title",
            "D1",
            "--rationale",
            "R1",
            "--confidence",
            "0.8",
        ],
        input="\n\n",
    )

    # Find the ID of the decision
    from origin.infrastructure.database import ArtifactRepository
    repo = ArtifactRepository(".origin/workspace.db")
    decisions = repo.list_decisions()
    assert len(decisions) == 1
    d1_id = decisions[0].id

    # Supersede it
    result = cli_runner.invoke(
        app,
        [
            "decision",
            "supersede",
            d1_id,
            "--title",
            "D2",
            "--rationale",
            "R2",
            "--confidence",
            "0.95",
        ],
        input="\n\n",
    )
    assert result.exit_code == 0
    assert f"Successfully superseded {d1_id}" in result.stdout

    # List active
    active_list = cli_runner.invoke(app, ["decision", "list", "--status", "active"])
    assert "D2" in active_list.stdout
    assert "D1" not in active_list.stdout

    # List superseded
    sup_list = cli_runner.invoke(app, ["decision", "list", "--status", "superseded"])
    assert "D1" in sup_list.stdout


def test_cli_memory_set_and_get(cli_runner: CliRunner) -> None:
    """Verify setting and getting memory values via CLI."""
    cli_runner.invoke(app, ["init"])

    set_result = cli_runner.invoke(
        app,
        ["memory", "set", "tech_stack", "framework", "fastapi"],
    )
    assert set_result.exit_code == 0
    assert "Saved Memory Entry" in set_result.stdout

    get_result = cli_runner.invoke(
        app,
        ["memory", "get", "tech_stack", "framework"],
    )
    assert get_result.exit_code == 0
    assert get_result.stdout.strip() == "fastapi"


def test_cli_search_and_context(cli_runner: CliRunner) -> None:
    """Verify search and context commands."""
    cli_runner.invoke(app, ["init"])
    cli_runner.invoke(app, ["memory", "set", "tech_stack", "framework", "fastapi"])

    # Test context
    context_result = cli_runner.invoke(app, ["context"])
    assert context_result.exit_code == 0
    assert "Active Project Memory" in context_result.stdout
    assert "**framework**: fastapi" in context_result.stdout

    # Test search
    search_result = cli_runner.invoke(app, ["search", "fastapi"])
    assert search_result.exit_code == 0
    assert "tech_stack.framework" in search_result.stdout
    assert "fastapi" in search_result.stdout


def test_cli_export(cli_runner: CliRunner) -> None:
    """Verify export updates files correctly."""
    cli_runner.invoke(app, ["init"])
    cli_runner.invoke(app, ["memory", "set", "tech_stack", "framework", "fastapi"])

    export_result = cli_runner.invoke(app, ["export", "--target", "claude-code"])
    assert export_result.exit_code == 0
    assert os.path.exists("CLAUDE.md")


def test_cli_doctor(cli_runner: CliRunner) -> None:
    """Verify doctor checks workspace state."""
    cli_runner.invoke(app, ["init"])
    result = cli_runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Workspace is healthy" in result.stdout

    # Now simulate a schema mismatch
    # Modify config.yaml directly
    import yaml
    config_path = ".origin/config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["schema_version"] = "3.0"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)

    doctor_result = cli_runner.invoke(app, ["doctor"])
    assert doctor_result.exit_code == 1
    assert "schema_version mismatch: expected '2.0', found '3.0'" in doctor_result.stdout


def test_cli_mcp_config(cli_runner: CliRunner) -> None:
    """Verify mcp-config outputs Claude registration JSON."""
    result = cli_runner.invoke(app, ["mcp-config"])
    assert result.exit_code == 0
    assert "origin-mcp" in result.stdout
    assert "origin-memory" in result.stdout
