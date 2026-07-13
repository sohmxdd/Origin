# Origin Decisions Mirror

This file is an auto-generated mirror of the active decisions in this workspace. Do not edit directly.

## Active Decisions Index

| Decision ID | Title | Confidence | Originating Agent | Updated At |
| :--- | :--- | :---: | :--- | :--- |
| `dec_01HXYZ00000000000000000000` | Use PostgreSQL | 0.95 | human | 2026-07-13 00:00:00 UTC |

---

## Active Decisions Details

### Use PostgreSQL (`dec_01HXYZ00000000000000000000`)
- **Confidence:** 0.95
- **Originating Agent:** human
- **Updated At:** 2026-07-13 00:00:00 UTC

#### Rationale
We need ACID compliance and support for JSON columns.

#### Alternatives Considered
- MongoDB
- MySQL

#### Affected Files
- `src/db.py`
- `src/models.py`

---
