# Security Policy

## Supported versions

Security fixes target the latest `0.2.x` release.

## Reporting a vulnerability

Please use the repository Security tab's **Report a vulnerability** action to open a private GitHub Security Advisory. Include the affected version, reproduction steps, expected impact and any suggested mitigation. Do not open a public issue for an active vulnerability.

Reports are handled on a best-effort basis. Public disclosure should wait until a fix or mitigation is available.

## Local-first threat model

- The management console binds only to literal loopback addresses. Mutating requests require a per-session token that protects against browser cross-site writes; it is not an authentication boundary against other processes running as the same local user.
- Read-only APIs may expose task content and local diagnostic paths. Processes running as the same local user are part of the trusted boundary.
- SQLite state, results, worktrees and user configuration use a default location outside the source tree. Common local-state paths are excluded from version control; custom state paths remain the operator's responsibility.
- Read-only workers are sandboxed; write tasks use isolated Git worktrees and approval policy.
- Workers ignore user-level Codex configuration by default so unattended tasks cannot inherit external-write MCP tools. Disabling `codex_ignore_user_config` is an explicit unsafe compatibility opt-in.
- Context Packs are explicit, size-bounded, credential-screened, JSON-encoded untrusted reference data. Their content is excluded from public task responses and cache telemetry.
- Cache target certification is limited to route-verified warm samples from one strict Cache Cohort v2 identity; gateways, profiles, schemas, and Context Packs are never merged to claim success.
- LightWorker does not automatically commit, merge, push, publish or grant `danger-full-access`.
