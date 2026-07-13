"""Git integration module for Origin.

Provides utilities for querying Git status, retrieving commit SHAs,
and installing hooks.
"""

import os
import subprocess
from typing import Optional


class GitHelper:
    """Helper class for interacting with Git repository features."""

    def __init__(self, workspace_path: str) -> None:
        """Initialize GitHelper for a specific workspace.

        Args:
            workspace_path: Path to the workspace root directory.
        """
        self.workspace_path = os.path.abspath(workspace_path)

    def get_current_commit_sha(self) -> Optional[str]:
        """Retrieve the current commit SHA of the repository.

        Returns:
            The 40-character commit SHA, or None if not in a git repo
            or if no commit exists yet.
        """
        git_dir = os.path.join(self.workspace_path, ".git")
        if not os.path.isdir(git_dir):
            return None

        try:
            # Run git rev-parse HEAD in the workspace directory
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )
            sha = result.stdout.strip()
            return sha if len(sha) == 40 else None
        except (subprocess.SubprocessError, FileNotFoundError):
            return None

    def install_hooks(self) -> bool:
        """Install a git pre-commit hook to automatically keep context files fresh.

        Writes a hook script to .git/hooks/pre-commit.

        Returns:
            True if hook was successfully installed, False if not a git repository.
        """
        git_dir = os.path.join(self.workspace_path, ".git")
        if not os.path.isdir(git_dir):
            return False

        hooks_dir = os.path.join(git_dir, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)

        hook_path = os.path.join(hooks_dir, "pre-commit")

        # Basic POSIX shell script. Git for Windows uses bash to execute hooks.
        hook_content = """#!/bin/sh
# Auto-update Origin context on commit
echo "Origin: Auto-exporting context..."
origin export --target generic || true
origin export --target claude-code || true
"""

        with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(hook_content)

        # Make hook executable on POSIX systems
        try:
            os.chmod(hook_path, 0o755)
        except AttributeError:
            pass  # os.chmod doesn't support execution permissions on Windows standard filesystems

        return True
