# LightWorker v0.7.1

LightWorker v0.7.1 is a patch release that hardens the dual Codex/ZCode worker architecture and makes native ZCode delegation reliable in real local deployments.

## What's new vs v0.7.0

### Added

- Per-task `harness` validation is preserved through batch delegation and planner-generated child tasks.
- The Web Console System view reports ZCode CLI availability, configured provider plan facts, selected models, and key presence without exposing key material.
- Regression coverage for gateway-free ZCode routing, planner propagation, cache isolation, provider reporting, and real subprocess result parsing.

### Fixed

- ZCode tasks no longer require OpenCodex or CLIProxyAPI gateway resolution and cannot be silently migrated onto a default gateway.
- ZCode's pretty-printed `--json` document output is parsed reliably, including its terminal `response` field.
- ZCode cache cohorts no longer look up a legacy gateway when no gateway applies.
- The batch API and planner now reject invalid ZCode/native-subagent and ZCode/explicit-gateway combinations.
- Windows TOML examples use valid literal-string path syntax.

### Changed

- ZCode tasks use the auditable `zcode-managed` model marker and keep `gateway`/`upstream_model` unset because provider selection is owned by the ZCode CLI.
- The task dialog enables Codex and ZCode independently according to their actual local availability.

## Install

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.7.1/lightworker-0.7.1-py3-none-any.whl
lightworker init
lightworker doctor
```

## Verification

- 128 local tests passed on the release candidate, including the new ZCode routing and whole-document parser regressions.
- Real ZCode end-to-end verification passed: `queued → running → completed`, structured result write-back, three concurrent tasks, and cancellation with no residual process.
- GitHub Actions runs the cross-platform Python 3.11/3.12/3.13 test matrix and package verification.
- `SHA256SUMS-v0.7.1.txt` records hashes for the release distributions.
