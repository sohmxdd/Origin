"""Unit tests for build-site static site builder command."""

import json
import os
import pytest
from typer.testing import CliRunner
from origin.presentation.cli import app
from origin.application.use_cases import init_workspace, add_decision, set_memory

runner = CliRunner()


def test_build_site_populated_workspace(tmp_path):
    """Verify that build-site produces HTML pages and badge.json for a populated workspace."""
    workspace_root = str(tmp_path)
    
    # Init workspace
    init_workspace(workspace_root, "PopulatedWorkspace", with_hooks=False)
    
    # Add decisions and memory
    dec = add_decision(
        workspace_root=workspace_root,
        title="MySQL Database",
        rationale="For standard schema persistence.",
        alternatives_considered=["PostgreSQL"],
        affected_files=["db.py"],
        confidence=1.0,
        originating_agent="human",
    )
    
    set_memory(
        workspace_root=workspace_root,
        category="tech_stack",
        key="database",
        value="MySQL 8.0",
        originating_agent="human",
    )

    output_dir = os.path.join(workspace_root, "generated_site")

    # Run build-site command
    # Use find_workspace_root mocking implicitly by changing directory to workspace_root
    # CLI command needs to run in the workspace directory context
    os.chdir(workspace_root)
    result = runner.invoke(app, ["build-site", "--output", output_dir])
    assert result.exit_code == 0
    assert "Successfully generated static site" in result.output

    # Check generated files
    assert os.path.exists(os.path.join(output_dir, "index.html"))
    assert os.path.exists(os.path.join(output_dir, "decisions.html"))
    assert os.path.exists(os.path.join(output_dir, "knowledge.html"))
    assert os.path.exists(os.path.join(output_dir, "timeline.html"))
    assert os.path.exists(os.path.join(output_dir, "badge.json"))
    
    # Check decision detail page
    detail_path = os.path.join(output_dir, "decisions", f"{dec.id}.html")
    assert os.path.exists(detail_path)

    # Validate index content
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        index_content = f.read()
        assert "System Diagnostics" in index_content
        assert "PopulatedWorkspace" in index_content
        assert "Healthy" in index_content

    # Validate badge.json format
    with open(os.path.join(output_dir, "badge.json"), "r", encoding="utf-8") as f:
        badge = json.load(f)
        assert badge["schemaVersion"] == 1
        assert badge["label"] == "Origin"
        assert "1 active" in badge["message"]


def test_build_site_empty_workspace(tmp_path):
    """Verify that build-site produces HTML pages with empty state messages for an empty workspace."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "EmptyWorkspace", with_hooks=False)

    output_dir = os.path.join(workspace_root, "generated_site")

    os.chdir(workspace_root)
    result = runner.invoke(app, ["build-site", "--output", output_dir])
    assert result.exit_code == 0

    assert os.path.exists(os.path.join(output_dir, "index.html"))
    assert os.path.exists(os.path.join(output_dir, "decisions.html"))
    assert os.path.exists(os.path.join(output_dir, "knowledge.html"))
    assert os.path.exists(os.path.join(output_dir, "timeline.html"))
    assert os.path.exists(os.path.join(output_dir, "badge.json"))

    # Validate empty state message on decisions page
    with open(os.path.join(output_dir, "decisions.html"), "r", encoding="utf-8") as f:
        decisions_content = f.read()
        assert "No active decisions found" in decisions_content
        assert "No proposed decisions pending review" in decisions_content

    # Validate empty state message on knowledge page
    with open(os.path.join(output_dir, "knowledge.html"), "r", encoding="utf-8") as f:
        knowledge_content = f.read()
        assert "No knowledge entries recorded" in knowledge_content
