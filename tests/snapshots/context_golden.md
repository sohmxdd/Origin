# Origin Project Context

This is the active project memory and decision history. Use this context to align with architecture and decisions.

## Workspace Information
- **Workspace Name:** TestWorkspace
- **Schema Version:** 1.0

## Active Decisions

### Use PostgreSQL (`dec_01HXYZ00000000000000000000`)
- **Confidence:** 0.95 | **Agent:** human | **Updated:** 2026-07-13 00:00:00 UTC
- **Rationale:** We need ACID compliance and support for JSON columns.
- **Alternatives Considered:** MongoDB, MySQL
- **Affected Files:** `src/db.py`, `src/models.py`

## Active Project Memory

### Tech Stack
- **database**: postgresql
