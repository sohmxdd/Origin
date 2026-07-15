"""Unit tests for token-budgeted context bundling and conflict heuristics."""

from datetime import datetime, timezone, timedelta
import pytest
from origin.domain.models import Decision, MemoryEntry
from origin.domain.context import (
    estimate_tokens,
    compile_context_bundle,
)
from origin.application.use_cases import (
    check_conflicting_decisions,
)


def test_estimate_tokens():
    """Verify character-count token estimation heuristic."""
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 40) == 10


def test_compile_context_bundle_under_budget():
    """Verify context bundle is not truncated if under budget."""
    base_time = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    decisions = [
        Decision(
            id="dec_01",
            title="Decision One",
            rationale="Short rationale here.",
            alternatives_considered=["alt1"],
            affected_files=["f1.py"],
            confidence=0.9,
            originating_agent="human",
            created_at=base_time,
            updated_at=base_time,
            status="active",
        )
    ]
    memories = [
        MemoryEntry(
            id="mem_01",
            category="tech_stack",
            key="db",
            value="sqlite",
            originating_agent="human",
            created_at=base_time,
            updated_at=base_time,
            status="active",
        )
    ]
    
    # Set a large budget (e.g. 500 tokens)
    bundle = compile_context_bundle(decisions, memories, "TestWS", "2.0", 500)
    
    assert "Decision One" in bundle
    assert "Short rationale here" in bundle
    assert "**db**: sqlite" in bundle
    assert "older decisions summarized" not in bundle


def test_compile_context_bundle_over_budget_sorting_and_truncation():
    """Verify context bundle truncates older/lower-confidence decisions first.
    
    Sorting rules for active decisions (highest priority to lowest):
      1. Primary: Recency (updated_at timestamp descending, newest first)
      2. Secondary: Confidence (confidence value descending, highest first)
      3. Tertiary: Decision ID (alphabetical ascending, for determinism)
    """
    base_time = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    # Let's create four decisions:
    # d1: newest (t=base_time), confidence=0.8
    # d2: middle (t=base_time - 1 hour), confidence=0.95
    # d3: middle (t=base_time - 1 hour), confidence=0.7 (same time as d2 but lower confidence)
    # d4: oldest (t=base_time - 2 hours), confidence=0.9
    
    d1 = Decision(
        id="dec_01",
        title="D1 Newest",
        rationale="Newest decision details here. This is very long rationale to consume budget.",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.8,
        originating_agent="human",
        created_at=base_time,
        updated_at=base_time,
        status="active",
    )
    d2 = Decision(
        id="dec_02",
        title="D2 Mid High Confidence",
        rationale="Mid high confidence rationale details here. Very long rationale to consume budget.",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.95,
        originating_agent="human",
        created_at=base_time - timedelta(hours=1),
        updated_at=base_time - timedelta(hours=1),
        status="active",
    )
    d3 = Decision(
        id="dec_03",
        title="D3 Mid Low Confidence",
        rationale="Mid low confidence rationale details here. Very long rationale to consume budget.",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.7,
        originating_agent="human",
        created_at=base_time - timedelta(hours=1),
        updated_at=base_time - timedelta(hours=1),
        status="active",
    )
    d4 = Decision(
        id="dec_04",
        title="D4 Oldest",
        rationale="Oldest decision details here. Very long rationale to consume budget.",
        alternatives_considered=[],
        affected_files=[],
        confidence=0.9,
        originating_agent="human",
        created_at=base_time - timedelta(hours=2),
        updated_at=base_time - timedelta(hours=2),
        status="active",
    )
    
    decisions = [d3, d1, d4, d2]
    memories = [
        MemoryEntry(
            id="mem_01",
            category="tech_stack",
            key="db",
            value="sqlite",
            originating_agent="human",
            created_at=base_time,
            updated_at=base_time,
            status="active",
        )
    ]
    
    # Priority order should be:
    # 1. d1 (newest: updated_at = base_time)
    # 2. d2 (updated_at = base_time - 1 hour, confidence = 0.95)
    # 3. d3 (updated_at = base_time - 1 hour, confidence = 0.7)
    # 4. d4 (updated_at = base_time - 2 hours, confidence = 0.9)
    
    # Let's set a small budget (e.g. 250 tokens) to force some truncation
    bundle = compile_context_bundle(decisions, memories, "TestWS", "2.0", 250)
    
    # Verify that d1 and d2 (highest priority) are kept full, while others are summarized
    assert "D1 Newest" in bundle
    assert "Newest decision details here" in bundle
    
    assert "D2 Mid High Confidence" in bundle
    assert "Mid high confidence rationale" in bundle
    
    # d3 and d4 should be summarized (title and ID only, no rationale)
    assert "D3 Mid Low Confidence" in bundle
    assert "Mid low confidence rationale" not in bundle
    assert "- D3 Mid Low Confidence (`dec_03`)" in bundle
    
    assert "D4 Oldest" in bundle
    assert "Oldest decision details here" not in bundle
    assert "- D4 Oldest (`dec_04`)" in bundle
    
    # Memory should be full
    assert "**db**: sqlite" in bundle
    
    # Truncation note must exist at the end
    assert "2 older decisions summarized — use origin search or origin decision list for full detail" in bundle


def test_check_conflicting_decisions_heuristic():
    """Verify conflict detection heuristic flags overlapping affected files."""
    base_time = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    # 1. Non-overlapping decisions
    d1 = Decision(
        id="dec_01",
        title="D1",
        rationale="R1",
        affected_files=["src/main.py"],
        originating_agent="human",
        status="active",
        created_at=base_time,
        updated_at=base_time,
    )
    d2 = Decision(
        id="dec_02",
        title="D2",
        rationale="R2",
        affected_files=["src/db.py"],
        originating_agent="human",
        status="active",
        created_at=base_time,
        updated_at=base_time,
    )
    
    assert len(check_conflicting_decisions([d1, d2])) == 0
    
    # 2. Overlapping decisions
    d3 = Decision(
        id="dec_03",
        title="D3",
        rationale="R3",
        affected_files=["src/main.py", "src/shared.py"],
        originating_agent="human",
        status="active",
        created_at=base_time,
        updated_at=base_time,
    )
    
    # Overlaps on 'src/main.py' between dec_01 and dec_03
    conflicts = check_conflicting_decisions([d1, d2, d3])
    assert len(conflicts) == 1
    assert conflicts[0] == ("dec_01", "dec_03", "src/main.py")
    
    # 3. Ignored if one superseded the other
    d1_superseded = Decision(
        id="dec_01",
        title="D1",
        rationale="R1",
        affected_files=["src/main.py"],
        originating_agent="human",
        status="superseded",
        superseded_by="dec_03",
        created_at=base_time,
        updated_at=base_time,
    )
    # Even if they overlap and status is active (dec_03 is active, dec_01 is superseded),
    # it shouldn't show up in conflicts list because:
    #   a) check_conflicting_decisions only inspects active decisions
    #   b) even if they were active, superseded links are explicitly skipped
    conflicts_superseded = check_conflicting_decisions([d1_superseded, d3])
    assert len(conflicts_superseded) == 0
