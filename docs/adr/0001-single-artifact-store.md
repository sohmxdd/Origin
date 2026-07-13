# Architecture Decision Record (ADR) 0001: Single Artifact Store

* **Decision ID:** `dec_01KXBTA5ADR000000000000000`
* **Type:** `decision`
* **Created At:** 2026-07-12 18:00:00 UTC
* **Updated At:** 2026-07-12 18:00:00 UTC
* **Originating Agent:** human
* **Status:** active
* **Confidence:** 1.00

## Title: Single SQLite Database for All Artifact Types

### Rationale
To prevent storage divergence, redundant code paths, and schema overhead in the v1 prototype, we collapse the "Context", "Timeline", and "Search" engines into query views over a single underlying SQLite database table named `artifacts`.

Each artifact represents a row in a unified schema where common base fields (id, type, timestamp, status, agent) are shared, and specific attributes (e.g. decision title/rationale, memory key/value, event summaries) are mapped to columns. Complex collection fields (`alternatives_considered` and `affected_files`) are serialized as JSON-encoded text at the repository boundary. This structure enforces a single, lightweight source of truth while still allowing efficient SQL-based keyword indexing and chronological logging.

### Alternatives Considered
* **Multiple SQL Tables:** Separate tables for decisions, memories, and events. Rejected due to the increased join complexity and schema overhead for a v1 prototype.
* **Loose JSON/YAML Files Only:** Keeping files as the primary store. Rejected because it lacks ACID guarantees, concurrent lock safety, and makes complex structured search inefficient.
* **Vector Database:** Rejected for v1 to avoid heavy external dependencies and maintain a lightweight, local-first footprint.

### Affected Files
* `src/origin/infrastructure/database.py`
* `src/origin/domain/models.py`
* `src/origin/application/use_cases.py`
