# LightWorker v0.7.0

LightWorker 0.7.0 introduces a native Dual Worker Harness architecture, adding full out-of-the-box support for the ZCode / GLM native agent CLI alongside OpenAI Codex.

## What's new vs v0.6.0

### Added

- **Dual Worker Harness (`ZCodeWorker` + `CodexWorker`)**: Unified worker abstraction executing tasks natively via either `codex exec` or `node zcode.cjs`.
- **Zero-Config Windows Path Auto-Detection**: Automatically detects standard ZCode installation paths (`D:\ZCode\resources\glm\zcode.cjs`, `C:\Program Files`, `AppData`).
- **Dynamic Task Routing**: `build_worker(cfg, spec)` dynamically instantiates the appropriate runner according to the task's declared `harness` parameter (`codex` or `zcode`).
- **Safety Mode Mapping**: Maps `workspace-write` + `execute` tasks safely to ZCode `--mode edit` and read-only tasks to `--mode plan` (strictly refusing destructive `yolo` mode).
- **Web UI & Doctor Diagnostic Support**: System view and `/api/doctor` endpoint detect and report ZCode binary availability and dual-harness execution readiness.
- **Unified Stream Parser & Process Tree Cleanup**: Robust JSON event parsing and recursive process tree termination on timeout or cancellation across both harnesses.

### Changed

- Task approval scope signature now binds `harness` parameter to ensure immutable execution context.
- System Overview UI displays available worker harnesses with live environment detection status.

## Verified end-to-end

- Dual harness unit and integration test suite: 105 tests passed across Python 3.11, 3.12, and 3.13.
- Windows auto-discovery verified against `D:\ZCode\resources\glm\zcode.cjs`.
- Full CI matrix green across `windows-latest`, `ubuntu-latest`, and `macos-latest`.
- Zero third-party runtime dependencies maintained.

## Install

Source checkout (full features, including Mission Control):

```bash
git clone --branch v0.7.0 https://github.com/ncepuee/LightWorker.git
cd LightWorker
python -m pip install -e .
```

Wheel/sdist (CLI + MCP server):

```bash
python -m pip install lightworker-0.7.0-py3-none-any.whl
```

## Verification assets

- `SHA256SUMS-v0.7.0.txt` covers the attached wheel and source distribution.
