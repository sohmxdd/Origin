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


@pytest.mark.asyncio
async def test_mcp_accept_reject(mcp_workspace: str) -> None:
    """Verify origin_accept_decision and origin_reject_decision via MCP."""
    # 1. Propose decision
    add_response = await mcp.call_tool(
        "origin_add_decision",
        arguments={
            "title": "Use Redis",
            "rationale": "For caching",
            "status": "proposed",
        },
    )
    content_blocks = add_response[0]
    dec_id = content_blocks[0].text.split("Decision ")[1].split(":")[0].strip()

    # 2. Reject decision
    reject_response = await mcp.call_tool(
        "origin_reject_decision",
        arguments={"id": dec_id},
    )
    assert "Successfully rejected" in reject_response[0][0].text

    # 3. Propose another
    add_response2 = await mcp.call_tool(
        "origin_add_decision",
        arguments={
            "title": "Use Memcached",
            "rationale": "Alternative caching",
            "status": "proposed",
        },
    )
    dec_id2 = add_response2[0][0].text.split("Decision ")[1].split(":")[0].strip()

    # 4. Accept decision
    accept_response = await mcp.call_tool(
        "origin_accept_decision",
        arguments={"id": dec_id2},
    )
    assert "Successfully accepted" in accept_response[0][0].text


def test_mcp_stdio_json_rpc(mcp_workspace):
    """Verify that launching the MCP server on stdio transport responds only with valid JSON-RPC."""
    import subprocess
    import sys
    import json

    proc = subprocess.Popen(
        [sys.executable, "-m", "origin.presentation.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    req = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        },
        "id": 1
    }

    try:
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()

        # Read the first line of output
        resp_line = proc.stdout.readline().strip()
        assert resp_line, "MCP server exited without returning JSON-RPC"

        # Verify it is valid JSON
        resp_json = json.loads(resp_line)
        assert resp_json.get("jsonrpc") == "2.0"
        assert resp_json.get("id") == 1
        assert "result" in resp_json

    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_mcp_full_tool_call_under_tui_load(mcp_workspace):
    """Verify that MCP tool calls (add, reject) succeed end-to-end under concurrent TUI polling."""
    import subprocess
    import sys
    import json
    import time
    import threading

    # Create a concurrent background reader thread to simulate TUI polling/loading
    stop_event = threading.Event()
    def tui_reader():
        from origin.infrastructure.database import ArtifactRepository
        db_path = os.path.join(mcp_workspace, ".origin", "workspace.db")
        repo = ArtifactRepository(db_path)
        while not stop_event.is_set():
            try:
                repo.list_decisions()
                repo.list_memory()
                repo.list_timeline()
                # Read config and YAMLs
                config_path = os.path.join(mcp_workspace, ".origin", "config.yaml")
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        f.read()
                dec_dir = os.path.join(mcp_workspace, ".origin", "decisions")
                if os.path.exists(dec_dir):
                    for name in os.listdir(dec_dir):
                        with open(os.path.join(dec_dir, name), "r", encoding="utf-8") as f:
                            f.read()
            except Exception:
                pass
            time.sleep(0.05)  # Fast poll

    thread = threading.Thread(target=tui_reader, daemon=True)
    thread.start()

    # Launch MCP server
    proc = subprocess.Popen(
        [sys.executable, "-m", "origin.presentation.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        # 1. Initialize
        init_req = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            },
            "id": 1
        }
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.flush()
        proc.stdout.readline()  # consume init response

        # 2. Call origin_add_decision (proposed)
        add_req = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "origin_add_decision",
                "arguments": {
                    "title": "Use Redis Cache",
                    "rationale": "In-memory cache layer",
                    "status": "proposed",
                    "confidence": 0.8,
                    "alternatives": ["Memcached"],
                    "affected_files": ["src/cache.py"]
                }
            },
            "id": 2
        }
        proc.stdin.write(json.dumps(add_req) + "\n")
        proc.stdin.flush()

        resp_line = proc.stdout.readline().strip()
        assert resp_line, "MCP server hung or exited on add decision call"
        resp = json.loads(resp_line)
        assert resp.get("id") == 2
        assert "error" not in resp, f"Tool call returned error: {resp}"
        
        # Extract decision ID from the success text
        result_text = resp["result"]["content"][0]["text"]
        dec_id = result_text.split("Decision ")[1].split(" ")[0].strip().rstrip(":")

        # 3. Call origin_reject_decision
        reject_req = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "origin_reject_decision",
                "arguments": {
                    "id": dec_id
                }
            },
            "id": 3
        }
        proc.stdin.write(json.dumps(reject_req) + "\n")
        proc.stdin.flush()

        resp_line2 = proc.stdout.readline().strip()
        assert resp_line2, "MCP server hung or exited on reject decision call"
        resp2 = json.loads(resp_line2)
        assert resp2.get("id") == 3
        assert "error" not in resp2, f"Tool call returned error: {resp2}"
        assert "Successfully rejected" in resp2["result"]["content"][0]["text"]

    finally:
        stop_event.set()
        thread.join(timeout=2)
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.asyncio
async def test_mcp_secrets_guard_blocking(mcp_workspace: str) -> None:
    """Verify MCP tools cleanly block secret patterns and return client-facing error strings."""
    # 1. Propose decision with AWS Key pattern
    response = await mcp.call_tool(
        "origin_add_decision",
        arguments={
            "title": "Use Redis",
            "rationale": "Redis key details here: AKIAIOSFODNN7EXAMPLE",
        },
    )
    content_blocks = response[0]
    assert len(content_blocks) == 1
    # Check that it returns a clean error string back to client instead of throwing or hanging
    assert "Error adding decision: Write rejected: content appears to contain a credential pattern" in content_blocks[0].text
    assert "(AWS Access Key ID)" in content_blocks[0].text
@pytest.mark.asyncio
async def test_mcp_blame(mcp_workspace: str) -> None:
    """Verify that origin_blame tool works correctly and returns Markdown formatted trace."""
    # 1. Propose decision affecting a file
    await mcp.call_tool(
        "origin_add_decision",
        arguments={
            "title": "Use SQL Database",
            "rationale": "For structured storage",
            "affected_files": ["db.py"],
        },
    )

    # 2. Call blame tool
    response = await mcp.call_tool(
        "origin_blame",
        arguments={
            "file_path": "db.py"
        },
    )
    content_blocks = response[0]
    assert len(content_blocks) == 1
    text = content_blocks[0].text
    assert "# Origin Blame: `db.py`" in text
    assert "Decision" in text
    assert "dec_" in text
    assert "Use SQL Database" in text
    assert "ACTIVE" in text

