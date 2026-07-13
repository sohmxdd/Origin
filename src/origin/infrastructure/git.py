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

    def get_current_branch(self) -> Optional[str]:
        """Retrieve the current branch name.

        Returns:
            The branch name, or None if not in a git repo or detached HEAD.
        """
        git_dir = os.path.join(self.workspace_path, ".git")
        if not os.path.isdir(git_dir):
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )
            branch = result.stdout.strip()
            return branch if branch and branch != "HEAD" else None
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

    def get_commits_with_trailer(self) -> list[dict]:
        """Scan git log looking for Origin-Decision: <id> trailers.

        Returns:
            A list of dicts with 'sha', 'subject', and 'decision_ids'.
        """
        import re
        git_dir = os.path.join(self.workspace_path, ".git")
        if not os.path.isdir(git_dir):
            return []

        try:
            result = subprocess.run(
                ["git", "log", "--grep=Origin-Decision:", "--pretty=format:%H%n%s%n%b%n---"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )
            commits = []
            raw_log = result.stdout.strip()
            if not raw_log:
                return []

            # Split by newlines separating commits with boundary '---'
            parts = raw_log.split("\n---\n")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                lines = part.split("\n", 2)
                if len(lines) < 2:
                    continue
                sha = lines[0].strip()
                subject = lines[1].strip()
                
                dec_ids = re.findall(r"Origin-Decision:\s*(dec_[a-zA-Z0-9_]+)", part)
                if dec_ids:
                    commits.append({
                        "sha": sha,
                        "subject": subject,
                        "decision_ids": list(set(dec_ids)),
                    })
            return commits
        except Exception:
            return []
