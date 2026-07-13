# Origin

Origin is a local-first, git-friendly persistent memory layer for AI coding agents.

## The Problem

Every AI coding assistant (Claude Code, Cursor, Codex CLI, etc.) starts every chat session with zero knowledge of the project's architecture, historical decisions, and current work. Developers find themselves constantly re-explaining the same context, conventions, and patterns, leading to cognitive fatigue and repetitive developer-agent instruction loops.

Origin solves this by storing that project context as structured, typed, and versioned artifacts in a `.origin/` directory. Rather than relying on chat logs or complex vector indexes, Origin mirrors this knowledge in SQLite and human-readable Markdown files that AI agents and developers can read directly. Synced and versioned directly by Git, Origin becomes a single source of truth that feeds context directly into agent system prompts via standard files (e.g. `CLAUDE.md`, `.cursor/rules`) or a Model Context Protocol (MCP) server.

## Quickstart

### 1. Install Origin
Install the CLI and MCP server in your environment:
```bash
pip install -e .
```

### 2. Initialize a Workspace
Initialize Origin in the root of your project:
```bash
origin init --name MyAwesomeApp
```

### 3. Record a Decision
```bash
origin decision add --title "Use Postgres" --rationale "Need SQL ACID properties" --confidence 0.95
```

### 4. Export Context for Agents
```bash
origin export --target claude-code
```

## Architecture

```
                      +-------------------+
                      |   Developer CLI   |
                      +---------+---------+
                                |
  +------------+      +---------v---------+      +------------+
  |  AI Agent  | <---->  MCP Server StdIO |      |  AI Agent  |
  +------------+      +---------+---------+      +------------+
                                |
                      +---------v---------+
                      | Application Layer |
                      +---------+---------+
                                |
        +-----------------------+-----------------------+
        |                                               |
+-------v-------+                               +-------v-------+
|  SQLite DB    |                               |  Flat Files   |
| (workspace.db)|                               | (CLAUDE.md    |
+---------------+                               |  ORIGIN.md    |
                                                |  cursor rules)|
                                                +---------------+
```

## Scope: What v1 is & isn't

### What it IS:
* **Structured conclusions:** Only saves structured facts and ADRs.
* **Single artifact store:** SQLite single-table database backed by Markdown mirrors.
* **Local-first & Git-friendly:** Versioned by git, keeping context synced with project branches.
* **Universal adapters:** Writes cleanly inside blocks in `CLAUDE.md` and `.cursor/rules`.
* **Standard MCP:** Exposes tool endpoints via standard stdio transport.

### What it IS NOT (V1 Non-Goals):
* **No Task Engine:** No execution loops or task dispatchers.
* **No Snapshot/Branching Engine:** Sync is handled via Git itself.
* **No Consensus Engine:** Single-developer or trusted-team workflows only.
* **No Vector DB:** Search is keyword + SQL-filtered, avoiding heavy semantic dependencies.
* **No Web Dashboard:** Admin is CLI and editor-only.
* **No Multi-Language SDKs:** Python only for V1.
* **No Multi-Tenancy:** Single developer focus.
