"""MCP server implementation for Origin using FastMCP.

Exposes tools for AI agents to interact with Origin's memory and decision log,
communicating via the Model Context Protocol stdio transport.
"""

import os
from typing import List

from mcp.server.fastmcp import FastMCP

from origin.application import use_cases
from origin.exceptions import OriginError


# Initialize the FastMCP server
mcp = FastMCP("origin-memory")


def find_workspace_root() -> str:
    """Traverse upwards from the current working directory to find a .origin workspace."""
    curr = os.path.abspath(os.getcwd())
    while True:
        if os.path.isdir(os.path.join(curr, ".origin")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return os.getcwd()


@mcp.tool()
def origin_get_context() -> str:
    """Retrieve the current compiled context bundle of active decisions and memory entries.

    Returns:
        A Markdown-formatted context bundle ready to be injected into a system prompt.
    """
    root = find_workspace_root()
    try:
        return use_cases.get_context_bundle(root)
    except OriginError as e:
        return f"Error loading context: {e}"


@mcp.tool()
def origin_add_decision(
    title: str,
    rationale: str,
    alternatives: List[str] = [],
    affected_files: List[str] = [],
    confidence: float = 1.0,
) -> str:
    """Record a new architectural or project decision.

    Args:
        title: Short title of the decision.
        rationale: Explanation of the logic behind this choice.
        alternatives: Alternative solutions evaluated.
        affected_files: Files or components affected by this decision.
        confidence: Agent's confidence score (0.0 to 1.0).

    Returns:
        A success message with the new decision ID.
    """
    root = find_workspace_root()
    try:
        conf = max(0.0, min(1.0, confidence))
        dec = use_cases.add_decision(
            workspace_root=root,
            title=title,
            rationale=rationale,
            alternatives_considered=alternatives,
            affected_files=affected_files,
            confidence=conf,
            originating_agent="mcp-server",
        )
        return f"Successfully recorded Decision {dec.id}: '{dec.title}' (Confidence: {dec.confidence:.2f})"
    except OriginError as e:
        return f"Error adding decision: {e}"


@mcp.tool()
def origin_list_decisions(status: str = "active") -> str:
    """List decisions matching a given status filter.

    Args:
        status: The decision status to filter by ('active' or 'superseded').

    Returns:
        A formatted list of decisions.
    """
    root = find_workspace_root()
    try:
        # Load db connection
        config = use_cases.load_config(root)
        origin_dir = os.path.join(root, ".origin")
        from origin.infrastructure.database import ArtifactRepository
        repo = ArtifactRepository(os.path.join(origin_dir, "workspace.db"))

        decisions = repo.list_decisions(status=status)
        if not decisions:
            return f"No decisions found with status '{status}'."

        lines = [f"--- Decisions List ({status}) ---"]
        for dec in decisions:
            superseded_str = f" (superseded by {dec.superseded_by})" if dec.superseded_by else ""
            lines.append(f"[{dec.id}] {dec.title} (Confidence: {dec.confidence:.2f}){superseded_str}")
        return "\n".join(lines)
    except OriginError as e:
        return f"Error listing decisions: {e}"


@mcp.tool()
def origin_supersede_decision(
    id: str,
    title: str,
    rationale: str,
    alternatives: List[str] = [],
    affected_files: List[str] = [],
    confidence: float = 1.0,
) -> str:
    """Supersede an old decision with a new decision.

    Args:
        id: The ID of the decision to supersede.
        title: Title of the new decision.
        rationale: Rationale of the new decision.
        alternatives: Alternatives considered.
        affected_files: Files affected.
        confidence: Confidence level 0.0-1.0.

    Returns:
        A success message with the new decision ID.
    """
    root = find_workspace_root()
    try:
        conf = max(0.0, min(1.0, confidence))
        dec = use_cases.supersede_decision(
            workspace_root=root,
            old_decision_id=id,
            title=title,
            rationale=rationale,
            alternatives_considered=alternatives,
            affected_files=affected_files,
            confidence=conf,
            originating_agent="mcp-server",
        )
        return f"Successfully superseded {id} with Decision {dec.id}: '{dec.title}'"
    except OriginError as e:
        return f"Error superseding decision: {e}"


@mcp.tool()
def origin_set_memory(category: str, key: str, value: str) -> str:
    """Store or update a key-value pair in project memory.

    Args:
        category: Memory category ('architecture', 'convention', 'tech_stack', 'glossary', 'deployment').
        key: The key identifier.
        value: The value content.

    Returns:
        A success message reporting the update.
    """
    root = find_workspace_root()
    try:
        entry = use_cases.set_memory(
            workspace_root=root,
            category=category,
            key=key,
            value=value,
            originating_agent="mcp-server",
        )
        return f"Saved Memory Entry [{entry.id}]: {category}.{key} = '{value}'"
    except OriginError as e:
        return f"Error setting memory: {e}"


@mcp.tool()
def origin_search(query: str) -> str:
    """Search across active decisions and memory entries using a keyword query.

    Args:
        query: The search term keyword.

    Returns:
        A formatted list of matching search results.
    """
    root = find_workspace_root()
    try:
        results = use_cases.search_artifacts(root, query)
        if not results:
            return "No matching artifacts found."

        lines = [f"--- Search Results for '{query}' ---"]
        for art in results:
            if art.type == "decision":
                lines.append(f"[{art.id}] Decision: '{art.title}' (Status: {art.status})")
            elif art.type == "memory":
                lines.append(f"[{art.id}] Memory: {art.category}.{art.key} = '{art.value}'")
        return "\n".join(lines)
    except OriginError as e:
        return f"Error performing search: {e}"


def main() -> None:
    """Main CLI entrypoint for origin-mcp script. Runs the FastMCP server on stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
