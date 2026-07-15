"""Domain context utilities for Origin.

Provides pure functions for token estimation and context bundling
to prevent circular dependencies and maintain clean architecture.
"""

from typing import List
from origin.domain.models import Decision, MemoryEntry


def estimate_tokens(text: str) -> int:
    """Approximate LLM token count using a character-count heuristic.

    This function estimates tokens as character count divided by 4 (len(text) // 4).
    This assumes a standard rule of thumb where 1 token is roughly 4 characters
    of English text and programming source code.
    """
    return len(text) // 4


def compile_context_bundle(
    decisions: List[Decision],
    memories: List[MemoryEntry],
    workspace_name: str,
    schema_version: str,
    token_budget: int,
) -> str:
    """Compile active decisions and memories into a budget-aware Markdown string.
    
    If the full representation exceeds the token_budget, decisions are selected for full
    rendering using the following sorting hierarchy:
      1. Primary: Recency (updated_at timestamp descending, newest first)
      2. Secondary: Confidence (confidence value descending, highest first)
      3. Tertiary: Decision ID (alphabetical ascending, for determinism)
      
    Older/lower-priority decisions are compressed to a single-line reference title and ID.
    Memory entries are always rendered in full.
    
    Args:
        decisions: List of active Decision objects.
        memories: List of active MemoryEntry objects.
        workspace_name: Name of the Origin workspace.
        schema_version: Workspace schema version.
        token_budget: Character-based token budget limit.
        
    Returns:
        Markdown context bundle string.
    """
    # Sort active decisions by priority: recency desc, confidence desc, id asc
    decisions_sorted = sorted(
        decisions,
        key=lambda d: (
            -d.updated_at.timestamp() if d.updated_at else 0.0,
            -d.confidence if d.confidence is not None else 0.0,
            d.id if d.id else ""
        )
    )

    promoted_indices = set()
    
    # Helper to construct the markdown bundle given a set of promoted indices
    def _format_bundle(promoted: set[int]) -> str:
        content = [
            "# Origin Project Context\n",
            "This is the active project memory and decision history. Use this context to align with architecture and decisions.\n",
            "## Workspace Information",
            f"- **Workspace Name:** {workspace_name}",
            f"- **Schema Version:** {schema_version}\n",
            "## Active Decisions\n",
        ]
        
        if not decisions_sorted:
            content.append("No active decisions recorded yet.\n")
        else:
            full_decs = [decisions_sorted[i] for i in range(len(decisions_sorted)) if i in promoted]
            sum_decs = [decisions_sorted[i] for i in range(len(decisions_sorted)) if i not in promoted]
            
            if full_decs:
                # Retain the relative priority order for the full decisions list
                for dec in full_decs:
                    updated_str = dec.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if dec.updated_at else "N/A"
                    content.append(f"### {dec.title} (`{dec.id}`)")
                    content.append(f"- **Confidence:** {dec.confidence:.2f} | **Agent:** {dec.originating_agent} | **Updated:** {updated_str}")
                    content.append(f"- **Rationale:** {dec.rationale.strip()}")
                    if dec.alternatives_considered:
                         alts_str = ", ".join(dec.alternatives_considered)
                         content.append(f"- **Alternatives Considered:** {alts_str}")
                    if dec.affected_files:
                         files_str = ", ".join(f"`{f}`" for f in dec.affected_files)
                         content.append(f"- **Affected Files:** {files_str}")
                    content.append("")
            
            if sum_decs:
                content.append("### Other Active Decisions (Summarized)\n")
                for dec in sum_decs:
                    content.append(f"- {dec.title} (`{dec.id}`)")
                content.append("")
                
        content.append("## Active Project Memory\n")
        if not memories:
            content.append("No active memory entries recorded yet.\n")
        else:
            categories = ["architecture", "convention", "tech_stack", "glossary", "deployment"]
            for cat in categories:
                cat_entries = [e for e in memories if e.category == cat]
                if not cat_entries:
                    continue
                content.append(f"### {cat.replace('_', ' ').title()}")
                for entry in cat_entries:
                    content.append(f"- **{entry.key}**: {entry.value}")
                content.append("")
                
        # Append truncation note if there are summarized decisions
        num_summarized = len(decisions_sorted) - len(promoted)
        if num_summarized > 0:
            content.append(f"\n{num_summarized} older decisions summarized — use origin search or origin decision list for full detail")
            
        return "\n".join(content)

    # Greedily promote decisions in priority order as long as the estimated token budget allows
    for i in range(len(decisions_sorted)):
        test_promoted = promoted_indices | {i}
        test_bundle = _format_bundle(test_promoted)
        if estimate_tokens(test_bundle) <= token_budget:
            promoted_indices.add(i)
        else:
            # Once we exceed the budget, stop promoting to respect strict priority
            break
            
    return _format_bundle(promoted_indices)
