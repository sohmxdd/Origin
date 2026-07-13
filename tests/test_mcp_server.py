"""Tests for the MCP server presentation layer."""

import os
from typing import Any
import pytest

from origin.application.use_cases import init_workspace
from origin.presentation.mcp_server import mcp


@pytest.fixture
def mcp_workspace(tmp_path: Any) -> str:
    """Fixture that initializes a workspace and changes directory to it for testing MCP tools."""
    workspace_root = str(tmp_path)
    init_workspace(workspace_root, "McpTest", with_hooks=False)

    old_cwd = os.getcwd()
    os.chdir(workspace_root)
    yield workspace_root
    os.chdir(old_cwd)


@pytest.mark.asyncio
async def test_mcp_add_and_list_decisions(mcp_workspace: str) -> None:
    """Verify origin_add_decision and origin_list_decisions via the MCP interface."""
    # 1. Call add decision tool
    add_response = await mcp.call_tool(
        "origin_add_decision",
        arguments={
            "title": "Use SQLite",
            "rationale": "Simple config database",
            "alternatives": ["JSON"],
            "affected_files": ["db.py"],
            "confidence": 0.95,
        },
    )
    content_blocks = add_response[0]
    assert len(content_blocks) == 1
    assert "Successfully recorded Decision dec_" in content_blocks[0].text

    # 2. Call list decisions tool
    list_response = await mcp.call_tool(
        "origin_list_decisions",
        arguments={"status": "active"},
    )
    content_blocks = list_response[0]
    assert len(content_blocks) == 1
    assert "Use SQLite" in content_blocks[0].text
    assert "dec_" in content_blocks[0].text


@pytest.mark.asyncio
async def test_mcp_set_memory_and_get_context(mcp_workspace: str) -> None:
    """Verify origin_set_memory and origin_get_context via the MCP interface."""
    # 1. Set Memory
    set_response = await mcp.call_tool(
        "origin_set_memory",
        arguments={
            "category": "tech_stack",
            "key": "language",
            "value": "python",
        },
    )
    content_blocks = set_response[0]
    assert len(content_blocks) == 1
    assert "Saved Memory Entry" in content_blocks[0].text

    # 2. Get Context
    context_response = await mcp.call_tool("origin_get_context", arguments={})
    content_blocks = context_response[0]
    assert len(content_blocks) == 1
    assert "**language**: python" in content_blocks[0].text


@pytest.mark.asyncio
async def test_mcp_supersede_decision(mcp_workspace: str) -> None:
    """Verify origin_supersede_decision works via the MCP interface."""
    # Add initial decision
    add_response = await mcp.call_tool(
        "origin_add_decision",
        arguments={
            "title": "SQLite",
            "rationale": "Simple choice",
        },
    )
    content_blocks = add_response[0]
    dec_id = content_blocks[0].text.split("Decision ")[1].split(":")[0]

    # Supersede via individual params
    sub_response = await mcp.call_tool(
        "origin_supersede_decision",
        arguments={
            "id": dec_id,
            "title": "Postgres",
            "rationale": "Scaling needs",
            "confidence": 0.8,
        },
    )
    content_blocks = sub_response[0]
    assert "Successfully superseded" in content_blocks[0].text

    # Check that postgres is in the active list
    list_response = await mcp.call_tool(
        "origin_list_decisions",
        arguments={"status": "active"},
    )
    content_blocks = list_response[0]
    assert "Postgres" in content_blocks[0].text
    assert "SQLite" not in content_blocks[0].text


@pytest.mark.asyncio
async def test_mcp_search(mcp_workspace: str) -> None:
    """Verify origin_search via the MCP interface."""
    await mcp.call_tool(
        "origin_set_memory",
        arguments={
            "category": "tech_stack",
            "key": "framework",
            "value": "fastapi",
        },
    )

    search_response = await mcp.call_tool(
        "origin_search",
        arguments={"query": "fastapi"},
    )
    content_blocks = search_response[0]
    assert "Memory: tech_stack.framework = 'fastapi'" in content_blocks[0].text
