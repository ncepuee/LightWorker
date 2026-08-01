# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-01

### Added

- Local-first task DAG runner for Codex-compatible workers with zero third-party Python runtime dependencies.
- SQLite task state, structured results, events, approvals, cancellation and scheduler standby takeover.
- Planner, Explorer, Executor and Reviewer workflows with reasoning-aware model routing.
- Isolated Git worktrees for write tasks; no automatic commit, merge, push or release.
- Loopback-only local management console with per-session mutation tokens.
- MCP server and command-line interface backed by the same scheduler and state store.
- MIT license and cross-platform GitHub Actions checks.
