# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-07-25

### Added
- **Incremental SQLite Index Sync:** Scalable $O(\Delta)$ filesystem diffing for `sync_index()`.
- **`origin blame <file>`:** CLI command and MCP tool (`origin_blame`) for file-level decision history tracing.
- **`origin build-site`:** Static HTML site builder with Jinja2 templates and Shields.io status `badge.json`.
- **`origin version` & `origin badge`:** CLI commands for package/schema version checking and README badge snippet generation.
- **`origin doctor --ci`:** Single-line concise status mode for CI pipelines.
- **Proactive PR Context Bot:** GitHub Action (`origin-context-bot.yml`) auto-commenting affected ADRs on pull requests.
- **Secrets Guard:** Automatic pre-commit scanning blocking high-entropy secrets, PEM keys, and AWS credentials.
- **Pre-commit & Dependabot Integration:** Automated linting, mypy type checks, and dependency vulnerability monitoring.
- **Hypothesis Property Tests & Coverage Gate:** Property-based serialization testing and 70% coverage floor enforcement.

### Changed
- **Filesystem-First v2 Architecture:** Decentralized flat-file YAML storage with local SQLite query caching.
- **Strict Safe Loading:** PyYAML safe deserialization enforced across all file reads (`yaml.safe_load`).

## [1.0.0] - 2026-07-13

### Added
- Initial release of Origin persistent memory layer for AI agents.
- Core CLI commands (`init`, `decision add`, `memory set`, `export`, `doctor`).
- FastMCP stdio server implementation (`origin-mcp`).
- Interactive terminal UI dashboard (`textual` TUI).
