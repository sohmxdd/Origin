"""Tests for the Git integration helper."""

import os
import subprocess
from typing import Any
import pytest
from origin.infrastructure.git import GitHelper


def test_git_helper_non_git_dir(tmp_path: Any) -> None:
    """Verify GitHelper returns None/False in a non-git directory."""
    helper = GitHelper(str(tmp_path))
    assert helper.get_current_commit_sha() is None
    assert helper.install_hooks() is False


def test_git_helper_valid_git_dir(tmp_path: Any) -> None:
    """Verify GitHelper can install hooks and query git in a initialized git dir."""
    repo_path = str(tmp_path)
    # Init a git repo in the temp path
    try:
        subprocess.run(["git", "init"], cwd=repo_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        try:
            subprocess.run("git init", cwd=repo_path, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            pytest.skip("git CLI is not available in this test environment")

    helper = GitHelper(repo_path)
    # No commits yet, so SHA should be None
    assert helper.get_current_commit_sha() is None

    # Install hook
    assert helper.install_hooks() is True

    hook_file = tmp_path / ".git" / "hooks" / "pre-commit"
    assert hook_file.exists()
    content = hook_file.read_text(encoding="utf-8")
    assert "origin export --target generic" in content
