# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-02

### Added

- Named `planner`, `fast_worker`, `deep_worker`, and `reviewer` profiles with explicit gateway, model, reasoning, and task-kind contracts.
- Dual-gateway routing for OpenCodex and CLIProxyAPI, including native/translated response-mode audits, bounded fallback, and manual deep escalation.
- Prompt Protocol v4 and Cache Cohort v2, isolating cache identity by gateway, response mode, upstream model, reasoning effort, profile, schema, sandbox, Context Pack, configuration scope, and tool contract.
- Explicit, bounded Context Packs treated as untrusted reference data, with credential screening and content-free public audit fields.
- Materialized cold/warm/indeterminate cache samples, token-weighted verified metrics, per-cohort 90% target certification, and historical event migration receipts.
- Cache-aware but root-fair scheduling, allowing at most one extra same-cohort affinity selection.
- Cache metrics in the Web Console, CLI, HTTP API, and MCP; task detail now includes route, schema, budget, and cache audits.

### Changed

- DeepSeek cache certification now requires at least 20 route-verified warm samples from one strict cohort; gateways and Context Packs are never combined to claim success.
- Worker results use deterministic schema normalization, bounded raw-result retention, and content-free prompt metadata.
- Public package keeps user Codex/MCP configuration isolated by default; compatibility mode remains an explicit opt-in.

### Fixed

- Prevented duplicate terminal usage events from inflating cache metrics, including providers that omit event IDs.
- Reclassified legacy or mismatched-route telemetry as indeterminate so older samples cannot satisfy the new target.
- Bounded cache windows and completed historical usage backfill in transactional batches.
- Preserved gateway authentication while filtering unselected provider credentials from Worker environments.
- Restored favicon and packaged Web/Schema resources for wheel and sdist installations.

### Security

- Context Pack content is JSON encoded under an explicit untrusted-data boundary and is never returned by public task APIs.
- Common token, password, API-key, certificate, local database, runtime, and authentication-file patterns are excluded from public source packaging.
- No API keys, local model catalogs, databases, logs, task results, or machine-specific paths are included in the release.

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
