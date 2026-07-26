"""Unit tests for non-mutating get_origin_diff use case."""

import os
import subprocess
import pytest
from origin.exceptions import OriginError
from origin.application.use_cases import init_workspace, add_decision, supersede_decision, get_origin_diff


def test_origin_diff_non_mutating(tmp_path) -> None:
    """Verify get_origin_diff compares commits non-mutatively using git plumbing."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "DiffTestWorkspace", with_hooks=False)

    # Initialize git repo and commit 1
    subprocess.run(["git", "init"], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace_root, check=True, capture_output=True)
    
    subprocess.run(["git", "add", "."], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace_root, check=True, capture_output=True)
    
    rev1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace_root, check=True, capture_output=True, text=True).stdout.strip()

    # Add decision in commit 2
    dec1 = add_decision(
        workspace_root=workspace_root,
        title="First Architecture Choice",
        rationale="Testing git diff feature",
        alternatives_considered=[],
        affected_files=["src/main.py"],
        confidence=1.0,
        originating_agent="human",
    )
    subprocess.run(["git", "add", "."], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add decision 1"], cwd=workspace_root, check=True, capture_output=True)

    rev2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace_root, check=True, capture_output=True, text=True).stdout.strip()

    # Test get_origin_diff between rev1 and rev2
    diff_res = get_origin_diff(workspace_root, rev1, rev2)
    assert diff_res["rev1"] == rev1
    assert diff_res["rev2"] == rev2
    assert len(diff_res["added"]) == 1
    assert diff_res["added"][0]["id"] == dec1.id
    assert diff_res["added"][0]["title"] == "First Architecture Choice"
    assert len(diff_res["modified"]) == 0
    assert len(diff_res["deleted"]) == 0

    # Test diffing same revision
    same_diff = get_origin_diff(workspace_root, rev2, rev2)
    assert len(same_diff["added"]) == 0
    assert len(same_diff["modified"]) == 0
    assert len(same_diff["deleted"]) == 0

    # Test commit with changes outside .origin/ entirely
    non_origin_file = os.path.join(workspace_root, "src", "utils.py")
    os.makedirs(os.path.dirname(non_origin_file), exist_ok=True)
    with open(non_origin_file, "w", encoding="utf-8") as f:
        f.write("# Non origin code change\n")
    subprocess.run(["git", "add", "."], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Modify code outside .origin"], cwd=workspace_root, check=True, capture_output=True)
    rev3 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace_root, check=True, capture_output=True, text=True).stdout.strip()

    outside_diff = get_origin_diff(workspace_root, rev2, rev3)
    assert len(outside_diff["added"]) == 0
    assert len(outside_diff["modified"]) == 0
    assert len(outside_diff["deleted"]) == 0

    # Test invalid revision error
    with pytest.raises(OriginError):
        get_origin_diff(workspace_root, "invalid_sha_123", rev2)


def test_origin_diff_modified_and_superseded_decisions(tmp_path) -> None:
    """Verify get_origin_diff tracks modified titles and superseded status across revisions."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "DiffModWorkspace", with_hooks=False)

    subprocess.run(["git", "init"], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace_root, check=True, capture_output=True)
    rev1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace_root, check=True, capture_output=True, text=True).stdout.strip()

    dec1 = add_decision(
        workspace_root=workspace_root,
        title="Initial Architecture",
        rationale="Base design",
        alternatives_considered=[],
        affected_files=["src/app.py"],
        confidence=0.9,
        originating_agent="human",
    )
    subprocess.run(["git", "add", "."], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add decision 1"], cwd=workspace_root, check=True, capture_output=True)
    rev2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace_root, check=True, capture_output=True, text=True).stdout.strip()

    # Supersede dec1 with dec2
    dec2 = supersede_decision(
        workspace_root=workspace_root,
        old_decision_id=dec1.id,
        title="Superseding Architecture",
        rationale="Upgraded design",
        alternatives_considered=[],
        affected_files=["src/app.py"],
        confidence=1.0,
        originating_agent="human",
    )
    subprocess.run(["git", "add", "."], cwd=workspace_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Supersede decision 1 with 2"], cwd=workspace_root, check=True, capture_output=True)
    rev3 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace_root, check=True, capture_output=True, text=True).stdout.strip()

    diff_res = get_origin_diff(workspace_root, rev2, rev3)
    assert len(diff_res["added"]) == 1
    assert diff_res["added"][0]["id"] == dec2.id
    assert len(diff_res["modified"]) == 1
    assert diff_res["modified"][0]["id"] == dec1.id
    assert diff_res["modified"][0]["old_status"] == "active"
    assert diff_res["modified"][0]["new_status"] == "superseded"

