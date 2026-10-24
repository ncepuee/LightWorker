# LightWorker v0.8.0

LightWorker 0.8.0 makes task state trustworthy: every task now persists its real backend session identifier, restart reconciliation probes process liveness, and a reaper clears tasks whose worker died without reporting — eliminating stuck "running" rows.

## What's new vs v0.7.1

### Added

- **Backend session identifiers (`backend_session_id`)**: tasks persist the real backend session id — Codex `thread.started`/`thread_id` events, ZCode `--json` document `sessionId` — captured live from the event stream and again at task completion; exposed through the task API and the detail drawer.
- **Liveness-probe restart reconciliation**: after a scheduler restart, tasks whose worker process is still alive keep their `running` status and record a `task.reconciled` event (state matches the backend); only dead-pid tasks are orphaned.
- **Unowned dead-task reaper**: the scheduler loop periodically clears `running`/`starting` tasks it does not own whose pid has exited without a result, so no task stays "running" forever after a crash.

### Fixed

- **ZCode 0.17+ compatibility**: the worker environment now passes `ZCODE_*` runtime hints through (paths and build metadata only, never credentials); ZCode 0.17.0 locates its built-in provider config through them and exits with an error without them.

### Fixed

- **Packaging fix**: `schemas/` and `web/` now ship inside the wheel (moved into the `lightworker` package with declared package-data). Previously the wheel lacked the output schemas and the web console, so a wheel-installed CLI could not create tasks; source checkouts were unaffected.

### Changed

- `RunResult` carries `session_id`; both worker harnesses report their backend session identifier.
- The wheel now includes the full web console (Mission Control) and both output schemas.

## Verified end-to-end

- 150 unit and integration tests passing (17 new regression tests for session capture, migration, reconciliation, reaper, and env passthrough).
- Real ZCode E2E on Windows: task `queued → running → completed`, backend `sessionId` persisted and exposed via the API; cancel path verified with no leftover processes.
- ZCode CLI 0.17.0 verified end to end after the auto-update broke the previous release's environment filter.
- Full CI matrix green across `windows-latest`, `ubuntu-latest`, `macos-latest`.
- Zero third-party runtime dependencies maintained.

## Install

Wheel (CLI + MCP server + Web console):

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.8.0/lightworker-0.8.0-py3-none-any.whl
lightworker init
lightworker doctor
```

Source checkout (full features, including Mission Control):

```bash
git clone --branch v0.8.0 https://github.com/ncepuee/LightWorker.git
cd LightWorker
python -m pip install -e .
```

## Verification assets

- `SHA256SUMS-v0.8.0.txt` covers the attached wheel and source distribution.
