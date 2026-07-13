"""Snapshot tests for flat-file exporters.

Ensures that updating the context block does not clobber existing contents
and matches golden snapshots.
"""

import os
from typing import Any
import pytest

from origin.application.use_cases import init_workspace, set_memory
from origin.adapters.flat_file import export_flat_file


def test_flat_file_exporter_preserves_content(tmp_path: Any) -> None:
    """Verify that export_flat_file preserves non-Origin developer content in CLAUDE.md."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "PreservationTest", with_hooks=False)

    # 1. Simulate a developer writing their own guidelines in CLAUDE.md
    claude_md_path = os.path.join(workspace_root, "CLAUDE.md")
    developer_content = (
        "# Custom Developer Guidelines\n\n"
        "Please follow these instructions:\n"
        "- Run pytest for test suites.\n"
        "- Maintain type hints everywhere.\n\n"
    )
    with open(claude_md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(developer_content)

    # 2. Add some memory entry in Origin
    set_memory(workspace_root, "tech_stack", "framework", "fastapi", "human")

    # 3. Export flat-file context for claude-code
    export_flat_file(workspace_root, "claude-code")

    # Read back to ensure developer guidelines exist and the block was appended
    with open(claude_md_path, "r", encoding="utf-8") as f:
        content_after_first_export = f.read()

    assert developer_content in content_after_first_export
    assert "<!-- ORIGIN:START -->" in content_after_first_export
    assert "**framework**: fastapi" in content_after_first_export
    assert "<!-- ORIGIN:END -->" in content_after_first_export

    # 4. Update memory entry to verify only the block updates
    set_memory(workspace_root, "tech_stack", "framework", "django", "human")
    export_flat_file(workspace_root, "claude-code")

    with open(claude_md_path, "r", encoding="utf-8") as f:
        content_after_second_export = f.read()

    assert developer_content in content_after_second_export
    assert "**framework**: django" in content_after_second_export
    assert "**framework**: fastapi" not in content_after_second_export

    # Compare against a golden snapshot file to ensure exact output format stability
    snapshots_dir = os.path.join(os.path.dirname(__file__), "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    golden_path = os.path.join(snapshots_dir, "claude_md_golden.md")

    # Standardize time and UUID references to make output deterministic for snapshot
    # Since decisions / timeline events have dates, but memory doesn't list dates in ORIGIN.md/context,
    # the exported context here is deterministic because we only have a MemoryEntry in memory!
    normalized_actual = content_after_second_export.replace("\r\n", "\n")

    if not os.path.exists(golden_path):
        with open(golden_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(normalized_actual)
        pytest.fail("Golden snapshot for CLAUDE.md did not exist. Created it. Re-run tests to pass.")

    with open(golden_path, "r", encoding="utf-8") as f:
        expected = f.read().replace("\r\n", "\n")

    assert normalized_actual == expected, "CLAUDE.md golden snapshot mismatch"
