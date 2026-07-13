"""Snapshot tests for the MirrorWriter markdown output."""

import os
from datetime import datetime, timezone
from typing import Any
import pytest

from origin.domain.models import Decision, MemoryEntry
from origin.infrastructure.mirror import MirrorWriter


def get_deterministic_data() -> tuple[list[Decision], list[MemoryEntry]]:
    """Helper to return deterministic Decisions and MemoryEntries for snapshot comparisons."""
    dt = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
    
    dec = Decision(
        id="dec_01HXYZ00000000000000000000",
        type="decision",
        created_at=dt,
        updated_at=dt,
        originating_agent="human",
        status="active",
        title="Use PostgreSQL",
        rationale="We need ACID compliance and support for JSON columns.",
        alternatives_considered=["MongoDB", "MySQL"],
        affected_files=["src/db.py", "src/models.py"],
        confidence=0.95,
    )
    
    mem = MemoryEntry(
        id="mem_01HXYZ00000000000000000000",
        type="memory",
        created_at=dt,
        updated_at=dt,
        originating_agent="claude-code",
        status="active",
        category="tech_stack",
        key="database",
        value="postgresql",
    )
    
    return [dec], [mem]


def test_mirror_writer_snapshots(tmp_path: Any) -> None:
    """Verify that MirrorWriter generates markdown matches corresponding golden snapshots."""
    # Initialize MirrorWriter
    writer = MirrorWriter(
        origin_dir=str(tmp_path),
        workspace_name="TestWorkspace",
        schema_version="1.0"
    )
    
    decisions, memories = get_deterministic_data()
    
    decisions_md = writer.generate_decisions_md(decisions)
    memory_md = writer.generate_memory_md(memories)
    context_md = writer.generate_context_bundle(decisions, memories)
    
    snapshots_dir = os.path.join(os.path.dirname(__file__), "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    
    decisions_golden_path = os.path.join(snapshots_dir, "decisions_golden.md")
    memory_golden_path = os.path.join(snapshots_dir, "memory_golden.md")
    context_golden_path = os.path.join(snapshots_dir, "context_golden.md")
    
    # Helper to assert or bootstrap golden files
    def assert_snapshot(actual: str, golden_path: str) -> None:
        # Standardize newlines for cross-platform robustness
        normalized_actual = actual.replace("\r\n", "\n")
        
        if not os.path.exists(golden_path):
            with open(golden_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(normalized_actual)
            pytest.fail(f"Golden snapshot file did not exist. Created: {os.path.basename(golden_path)}. Re-run tests to pass.")
            
        with open(golden_path, "r", encoding="utf-8") as f:
            expected = f.read().replace("\r\n", "\n")
            
        assert normalized_actual == expected, f"Snapshot mismatch for {os.path.basename(golden_path)}"

    assert_snapshot(decisions_md, decisions_golden_path)
    assert_snapshot(memory_md, memory_golden_path)
    assert_snapshot(context_md, context_golden_path)
