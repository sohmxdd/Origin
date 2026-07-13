"""Flat-file exporters for Origin.

Provides adapters to write or update context files for specific agents,
using block preservation to avoid overwriting developer changes.
"""

import os

from origin.application.use_cases import get_context_bundle


def update_file_with_block(file_path: str, new_content: str) -> None:
    """Update a file by replacing or appending a clearly marked block.

    Args:
        file_path: Path to the target file.
        new_content: The new context content to insert.
    """
    start_tag = "<!-- ORIGIN:START -->"
    end_tag = "<!-- ORIGIN:END -->"
    block = f"{start_tag}\n{new_content.strip()}\n{end_tag}"

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if start_tag in content and end_tag in content:
            # Replace the existing block
            start_idx = content.find(start_tag)
            end_idx = content.find(end_tag) + len(end_tag)
            updated_content = content[:start_idx] + block + content[end_idx:]
        else:
            # Append the block to the end of the file
            suffix = ""
            if content and not content.endswith("\n"):
                suffix = "\n\n"
            elif content and content.endswith("\n") and not content.endswith("\n\n"):
                suffix = "\n"
            updated_content = content + suffix + block
    else:
        # Create a new file with just the block
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        updated_content = block

    with open(file_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated_content)


def export_flat_file(workspace_root: str, target: str) -> str:
    """Export the current context bundle to the specified target file format.

    Args:
        workspace_root: The root of the workspace.
        target: The target format ('claude-code', 'cursor', or 'generic').

    Returns:
        The path of the file that was updated.

    Raises:
        ValueError: If the target format is invalid.
    """
    workspace_root = os.path.abspath(workspace_root)
    context_bundle = get_context_bundle(workspace_root)

    if target == "claude-code":
        file_path = os.path.join(workspace_root, "CLAUDE.md")
    elif target == "cursor":
        # Check if .cursor/rules exists as a directory
        cursor_rules_dir = os.path.join(workspace_root, ".cursor", "rules")
        if os.path.isdir(cursor_rules_dir):
            file_path = os.path.join(cursor_rules_dir, "origin.md")
        else:
            file_path = os.path.join(workspace_root, ".cursor", "rules")
    elif target == "generic":
        file_path = os.path.join(workspace_root, "ORIGIN.md")
    else:
        raise ValueError(
            f"Invalid export target '{target}'. Must be 'claude-code', 'cursor', or 'generic'."
        )

    update_file_with_block(file_path, context_bundle)
    return file_path
