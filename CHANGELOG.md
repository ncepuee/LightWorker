# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-08-02

### Added

- Cache-friendly Prompt Protocol v2 with deterministic list and routing-policy serialization.
- Content-free prompt, stable-prefix, schema, gateway, and cache-cohort SHA-256 fingerprints in `worker.prompt` events.
- Normalized `worker.usage` events for OpenAI-compatible and DeepSeek cache token fields, including cache hit rate when available.
- Regression coverage for prompt stability, worktree-aware execution context, content-free fingerprint telemetry, and usage parsing.
- Tag CI checks, Python 3.12 coverage, and clean sdist installation verification.

### Fixed

- Moved stable safety, output, and role instructions ahead of task-specific content so compatible providers can reuse the common prompt prefix.
- Worker prompts now report the resolved execution worktree instead of the original repository when write or review tasks run in isolation.
- Added and refreshed README language navigation, repository branding, and browser favicon support delivered since v0.1.0.

### Security

- Cache telemetry records hashes and token counts only; prompt text, objectives, workspace paths, gateway URLs, catalogs, and credentials are not copied into the new events.
- Workers remain short-lived and `--ephemeral`; v0.1.1 does not share provider sessions, response IDs, tool state, or task results across agents.

## [0.1.0] - 2026-08-01

### Added

- Local-first task DAG runner for Codex-compatible workers with zero third-party Python runtime dependencies.
- SQLite task state, structured results, events, approvals, cancellation and scheduler standby takeover.
- Planner, Explorer, Executor and Reviewer workflows with reasoning-aware model routing.
- Isolated Git worktrees for write tasks; no automatic commit, merge, push or release.
- Loopback-only local management console with per-session mutation tokens.
- MCP server and command-line interface backed by the same scheduler and state store.
- MIT license and cross-platform GitHub Actions checks.
