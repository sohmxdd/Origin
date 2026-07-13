# Contributing to Origin

Thank you for contributing to Origin! This document outlines code standards, setup steps, and how to extend the prototype.

## Developer Setup

1. **Clone the repo**
2. **Install dependencies in development mode:**
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

To run the unit and integration tests safely (directing pytest's temp directory away from restricted paths on Windows/Unix):
```bash
PYTHONPATH=src pytest --basetemp=tmp
```

## Adding a New Artifact Type

To add a new type of persistent knowledge artifact:
1. Define the Pydantic schema in `src/origin/domain/models.py`, inheriting from `ArtifactBase`.
2. Add your literal type identifier to `type` in `ArtifactBase` and update the DB row mapper in `src/origin/infrastructure/database.py`.
3. Promote any searchable fields to columns in `src/origin/infrastructure/database.py`'s `_init_db` table creation schema.
4. Update the SQL write query mappings inside `ArtifactRepository.save()`.
5. Add unit tests for validation in `tests/test_domain.py` and database persistence in `tests/test_database.py`.

## Proposing/Adding a New Flat-File Adapter

Exporters are the main way Origin connects to new tools. To add a new adapter (e.g. for `copilot` or other agents):
1. In `src/origin/adapters/flat_file.py`, add a new branch in `export_flat_file` representing your target.
2. Formulate the destination filepath (e.g. at repo root or inside tool subdirectories).
3. Reuse `update_file_with_block` to write the standard `<!-- ORIGIN:START -->...<!-- ORIGIN:END -->` block format to the destination.
4. Add verification tests inside `tests/test_flat_file_snapshots.py`.
