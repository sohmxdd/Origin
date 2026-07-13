# 🤝 Contributing to Origin

Thank you for your interest in contributing to **Origin**! This document provides all the information you need to set up your local development environment, run tests, understand the architecture, and contribute new features.

---

## 📖 Table of Contents
1. [🛠️ Developer Setup](#️-developer-setup)
2. [📂 Repository Directory Structure](#-repository-directory-structure)
3. [🧪 Running Tests](#-running-tests)
4. [📐 Architecture Guidelines](#-architecture-guidelines)
5. [✨ How-To Guides](#-how-to-guides)
   - [Adding a New Artifact Type](#adding-a-new-artifact-type)
   - [Adding a New Flat-File Exporter Target](#adding-a-new-flat-file-exporter-target)
   - [Exposing New MCP Tools](#exposing-new-mcp-tools)
6. [📝 Code Style & Conventional Commits](#-code-style--conventional-commits)
7. [🚀 Pull Request Workflow](#-pull-request-workflow)

---

## 🛠️ Developer Setup

Origin requires **Python 3.11+**. Follow these steps to get started:

### 1. Clone the Repository
```bash
git clone https://github.com/sohmxdd/Origin.git
cd Origin
```

### 2. Create a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies in Editable Mode
Install the package along with development and test dependencies:
```bash
pip install -e ".[dev]"
```

---

## 📂 Repository Directory Structure

Origin is structured using clean architectural patterns (Domain, Application, Infrastructure, and Presentation layers):

```
├── .origin/                  # Auto-generated workspace configuration & cached indexes
├── src/
│   └── origin/
│       ├── application/      # Use cases (business logic orchestration)
│       ├── domain/           # Models, ULIDs, and base schemas
│       ├── infrastructure/   # Filesystem storage, SQLite caching, Git, and Mirror logic
│       └── presentation/     # Interfaces: cli.py, mcp_server.py, and tui.py
├── tests/                    # Comprehensive unit, integration, and Textual Pilot tests
├── demo_tui.py               # Seeded terminal dashboard launcher
├── pyproject.toml            # Dependencies and script definitions
└── README.md                 # Main documentation page
```

---

## 🧪 Running Tests

Origin uses `pytest` for testing. 

> [!IMPORTANT]
> **Windows/Restricted Sandbox Environments:** Always use the `--basetemp=tmp` flag when running tests to ensure pytest creates temporary workspace folders within the local directory rather than restricted system `AppData` folders.

### Run All Tests
```bash
# Windows PowerShell
$env:PYTHONPATH="src"
python -m pytest --basetemp=tmp -v

# macOS / Linux
PYTHONPATH=src python -m pytest --basetemp=tmp -v
```

### Run specific test files
* **CLI Tests:** `python -m pytest tests/test_cli.py --basetemp=tmp`
* **TUI Dashboard Tests:** `python -m pytest tests/test_tui.py --basetemp=tmp`
* **MCP Server Tests:** `python -m pytest tests/test_mcp_server.py --basetemp=tmp`

---

## 📐 Architecture Guidelines

Before writing code, keep these core architectural choices in mind:
1. **YAML files are the Source of Truth:** SQLite (`workspace.db`) is strictly a read/query cache index. Any state change must write atomically to YAML files in `.origin/` first, then sync to the SQLite index.
2. **Presentation Adapters are Thin:** The CLI (`cli.py`), MCP Server (`mcp_server.py`), and TUI (`tui.py`) must contain **zero business logic**. All write or read operations must delegate to the use cases defined in [use_cases.py](file:///c:/Users/SOHAM/ProjectRepos/Origin/src/origin/application/use_cases.py).
3. **Robustness & No Stdio Pollution:** Since the MCP server communicates over standard input/output (`stdio`), any code path called by the MCP server **must never write to stdout** via `print()` or `Console().print()`. Log tracebacks and warnings to `sys.stderr` instead.
4. **Isolate Primary vs. Secondary Writes:** Database writes must occur first. Secondary post-write actions (like timeline logs, mirrors, or git commit checks) must be protected by local exception catch-blocks so that a primary database write does not crash or report false errors if a secondary hook experiences file contention.

---

## ✨ How-To Guides

### Adding a New Artifact Type
To create a new type of versioned project knowledge (like a ticket link, task list, or configuration flag):
1. **Define Schema:** Add your new class inheriting from `ArtifactBase` in [models.py](file:///c:/Users/SOHAM/ProjectRepos/Origin/src/origin/domain/models.py). Add its string identifier literal to the `type` field.
2. **Configure Database Schema:** In `database.py`, update `_init_db` to include any columns you want to index for search, and map your new model to a row in `_row_to_artifact()`.
3. **YAML Serialization:** Implement the YAML read/write methods in `database.py`'s `ArtifactRepository.save()`.
4. **Add Tests:** Write persistence and schema validation checks inside `tests/test_domain.py` and `tests/test_database.py`.

### Adding a New Flat-File Exporter Target
Exporters map Origin context to different coding editor systems.
1. Add a new target branch inside `export_flat_file` in [flat_file.py](file:///c:/Users/SOHAM/ProjectRepos/Origin/src/origin/adapters/flat_file.py).
2. Formulate the destination filename (e.g. `.cursorrules`, `CLAUDE.md`, or a new format like `COPILOT.md`).
3. Use the helper `update_file_with_block` to write context inside the marked comment tags (`<!-- ORIGIN:START -->` ... `<!-- ORIGIN:END -->`).
4. Write verification tests in `tests/test_flat_file_snapshots.py`.

### Exposing New MCP Tools
1. Define the tool function in [mcp_server.py](file:///c:/Users/SOHAM/ProjectRepos/Origin/src/origin/presentation/mcp_server.py) using the `@mcp.tool()` decorator.
2. Ensure you wrap the body in a `try...except Exception as e:` block.
3. If an exception occurs, print the traceback to `sys.stderr` and return a clean error string to prevent stream corruption.
4. Update the test suite in `tests/test_mcp_server.py` to cover the new tool.

---

## 📝 Code Style & Conventional Commits

We follow standard Python PEP 8 conventions. Commit messages should conform to the **Conventional Commits** specification:

* `feat: ...` for new user-facing features (like a new CLI command).
* `fix: ...` for bug fixes.
* `docs: ...` for documentation updates.
* `test: ...` for adding or modifying tests.
* `refactor: ...` for internal structural code changes.

Example:
```bash
git commit -m "feat: add copy-to-clipboard shortcut to decisions TUI modal"
```

---

## 🚀 Pull Request Workflow

1. **Create a Branch:** `git checkout -b feature/my-new-feature`
2. **Write Code & Tests:** Add unit/integration tests to verify your implementation.
3. **Format & Run Linting:** Ensure your code is clean and error-free.
4. **Run Full Test Suite:** Ensure all 46+ tests pass successfully.
5. **Open a Pull Request:** Describe your changes, specify the issue they resolve, and link to the relevant ADRs or design docs.
