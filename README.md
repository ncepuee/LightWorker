<p align="center">
  <img src="lightworker/web/logo.svg" alt="LightWorker task graph converging into an execution core" width="112">
</p>

<h1 align="center">LightWorker</h1>

<p align="center">English | <a href="README_CN.md">中文</a></p>

<p align="center"><strong>Local-first multi-agent delegation and approval control for Codex.</strong></p>

<p align="center">
  <a href="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/ncepuee/LightWorker/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/ncepuee/LightWorker?display_name=tag&sort=semver"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-31D0AA.svg"></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#web-console">Web Console</a> ·
  <a href="#codex-mcp">Codex MCP</a> ·
  <a href="SECURITY.md">Security</a> ·
  <a href="https://github.com/ncepuee/LightWorker/releases">Releases</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

LightWorker is a lightweight, local-first multi-agent task runner with no third-party Python runtime dependencies. It lets Codex submit tasks through MCP, persists the task DAG in SQLite, executes Workers with `codex exec --json`, and uses an isolated Git worktree for write tasks.

> **Project status:** `v0.5.0` is the current release. It ships a fully redesigned Mission Control Web Console — hash-routed Overview / Tasks / Cache Lab / System views, a `Ctrl+K` command palette, a tabbed task drawer with JSON highlighting, and an approval inbox — while keeping the zero-dependency, CSP-safe delivery. Since v0.2.0 the runtime also adds capability-aware gateway routing, `lightworker_worker` / `native_subagent` execution channels, approvals bound to immutable task scopes, an explicit worker environment allowlist, and Prompt Protocol v5 cache cohorts. By default, LightWorker listens only on the local loopback address and does not automatically commit, merge, push, or publish; write tasks require approval and run in an isolated Git worktree. See [README_CN.md](README_CN.md) for the full Chinese documentation.

## Core Capabilities

| Capability | What it does |
|---|---|
| Persistent task DAG | SQLite WAL stores tasks, dependencies, events, PIDs, results, and worktree information |
| Automatic decomposition and parallelism | Lead Codex generates a directed acyclic task graph; independent read-only Workers can run in parallel |
| Reasoning-aware routing | Mechanical tasks go to DeepSeek V4 Flash by default; complex tasks use `gpt-5.6-sol` |
| Approval and isolation | `auto_readonly` runs read-only tasks automatically; write tasks wait for approval and enter an isolated Git worktree |
| Three control surfaces | CLI, Codex MCP, and the local Web Console share the same scheduler and state store |
| Measurable cache optimization | Prompt Protocol v5, strict Cache Cohort v2 isolation, explicit Context Packs, cache-affinity scheduling, and verified warm-cache metrics |
| Dual-gateway profiles | Named Planner, fast, deep, and review profiles can route through OpenCodex or CLIProxyAPI with explicit fallback and route audits |
| Capability-aware routing | Tasks declare required capabilities (e.g. `web_search`); gateways that lack them are excluded up front and fail closed instead of silently degrading |
| Scope-bound approvals | Each approval binds `approval_id` plus a SHA-256 scope digest; a task spec that changes after approval is refused |
| History management | The Web Console can purge terminated tasks with their events and usage records in one click |
| Local-first security | `danger-full-access` is prohibited; user MCP servers are isolated by default; no automatic commit, merge, push, or publish |

## Secure Defaults

| Boundary | Default behavior |
|---|---|
| Web Console | Only the literal loopback addresses `127.0.0.1` / `::1` are allowed |
| Read-only tasks | Can run automatically under `auto_readonly` |
| Write tasks | Manual approval, using an isolated Git worktree |
| User Codex configuration | Ignored by Workers by default, avoiding inheritance of MCP servers with external write access |
| Git and external systems | Never automatically commits, merges, pushes, publishes, or grants `danger-full-access` |

See [SECURITY.md](SECURITY.md) for the full threat model and how to report vulnerabilities.

## Requirements

- Python 3.11+
- Git
- Codex CLI
- A working Codex login or a configured model gateway
- CLIProxyAPI/OpenCodex Proxy on the current machine (when using non-OpenAI models)

The local development verification environment is Python 3.13, Git 2.51, Codex CLI 0.146.0, and SQLite 3.51.

## Installation

Install the CI-verified universal wheel directly from the v0.2.0 GitHub release:

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.2.0/lightworker-0.2.0-py3-none-any.whl
lightworker init
lightworker doctor
```

SHA-256 checksums for release assets are listed in [`SHA256SUMS.txt`](SHA256SUMS.txt). When developing or auditing the source, you can install from a pinned tag:

```bash
git clone --branch v0.2.0 --depth 1 https://github.com/ncepuee/LightWorker.git
cd LightWorker
python -m pip install -e .
```

## Quick Start

You can run it directly after installation:

```powershell
$env:LIGHTWORKER_HOME = "$env:LOCALAPPDATA\LightWorker"
lightworker init
lightworker doctor
```

macOS / Linux:

```bash
export LIGHTWORKER_HOME="${XDG_STATE_HOME:-$HOME/.local/state}/lightworker"
lightworker init
lightworker doctor
```

For a local CLIProxyAPI/OpenCodex setup, we recommend initializing LightWorker with an isolated Codex configuration:

```powershell
lightworker init --force --isolated-codex `
  --codex-base-url "http://127.0.0.1:10100/v1" `
  --model-catalog "$env:USERPROFILE\.codex\opencodex-catalog.json"
```

Submit a read-only DeepSeek V4 Flash investigation:

```powershell
lightworker submit `
  --workspace "C:\path\to\project" `
  --kind explore `
  --model "deepseek/deepseek-v4-flash" `
  --run `
  "Analyze the project structure and list the three modules that most need tests."
```

Let Lead Codex decompose the task automatically:

```powershell
lightworker orchestrate `
  --workspace "C:\path\to\project" `
  --mode auto_readonly `
  --run `
  "Find the cause of intermittent HTTP 500 errors in the login endpoint and provide an evidence-backed remediation plan."
```

Example default routing in v0.2.0:

| Task type | Default model |
|---|---|
| Planner / design / review / debugging / complex coding | `gpt-5.6-sol` |
| Mechanical execution, formatting, and simple retrieval at `low` reasoning effort | `deepseek/deepseek-v4-flash` |
| Executor | `gpt-5.6-sol` |

When a single task does not specify a model explicitly, routing is automatic based on reasoning effort: `low` uses `deepseek/deepseek-v4-flash`; `medium/high/xhigh` use `gpt-5.6-sol`. In other words, mechanical execution, formatting, and simple retrieval go to Flash, while design, planning, review, debugging, and complex coding go to OpenAI agents.

Model names and the allowlist can be configured in `%LOCALAPPDATA%\LightWorker\config.toml`.

## Web Console

Run this in the project directory:

```powershell
.\Start-LightWorker-Web.ps1
```

You can also run it directly:

```powershell
python -m lightworker web
python -m lightworker web --no-open --port 8766
```

The default address is `http://127.0.0.1:8766/`. The page offers:

- Task overview, status filtering, and automatic refresh every three seconds.
- Forms for auto-planned tasks and single-Worker tasks.
- Approval of `awaiting_approval` write tasks and cancellation of non-terminal tasks.
- Structured task results, error messages, and event stream inspection.
- Status of Codex, CLIProxyAPI, OpenCodex Proxy, and the model allowlist.
- A DeepSeek Cache Lab card with verified warm-cache hit rate, strict cohort audit, and target status.
- Explicit Context Packs for stable shared reference material without automatic repository or environment-file ingestion.

The Web service may only bind to the literal loopback addresses `127.0.0.1` or `::1`. A random session token is generated at every startup, and write endpoints must carry it; the page injects the token automatically, so no manual entry is required. The token protects against cross-site write requests from browsers; it does not isolate other local processes running under the same user. Same-user local processes are within the trusted boundary, and read-only APIs may return task and diagnostic information. Web and Codex MCP share the SQLite state store, and a process lock guarantees that only one Scheduler executes tasks at any given time. Processes without the lock stay in standby: they can still submit and query tasks and will take over automatically once the current Scheduler exits.

Brand assets:

- `lightworker/web/logo.svg`: LightWorker's "converging execution core" vector mark, used in the sidebar and empty states.
- `lightworker/web/favicon.svg`: an optically corrected 16/32 px dark favicon.
- `lightworker/web/lightworker-app-icon.png`: a high-resolution app icon generated with GPT Image, used as `apple-touch-icon` and as a brand asset.

If the user Codex configuration enables many MCP servers, we recommend letting Workers use an isolated configuration so that each subtask does not repeatedly load unrelated tools:

```toml
[runner]
codex_ignore_user_config = true
codex_base_url = "http://127.0.0.1:10100/v1"
codex_model_catalog = "C:\\Users\\you\\.codex\\opencodex-catalog.json"
```

`--ignore-user-config` still reuses Codex's authentication directory, but does not load user-level MCP servers or sandbox defaults; LightWorker explicitly passes a read-only or workspace-write sandbox.

Isolation is the default security boundary, not just a performance option: unattended Workers should not inherit user MCP servers that could perform external writes such as GitHub or Slack. Only set `codex_ignore_user_config` to `false` if you clearly understand the risk and want to be compatible with user-level configuration; in that case `auto_readonly` can only constrain Codex's local sandbox and cannot guarantee that third-party MCP servers have no external side effects.

## Model Gateways

LightWorker does not store API keys for model services directly. It invokes the local Codex CLI and can connect to OpenAI or a compatible gateway through Codex's model catalog. When using a local gateway such as CLIProxyAPI, we recommend listening only on the loopback address and keeping authentication files in the user configuration directory, not in the project repository.

The default routing is only a starting point: `low`-reasoning tasks go to DeepSeek V4 Flash, while complex planning, coding, and review go to `gpt-5.6-sol`. All available models remain controlled by the allowlist in `config.toml`.

## Provider Cache Lab

Prompt Protocol v4 keeps the stable safety, output, role, profile, and optional Context Pack contract ahead of task-specific content. Cache Cohort v2 prevents misleading aggregation across gateways, response modes, upstream models, reasoning effort, profiles, schemas, sandboxes, Context Packs, configuration scopes, and tool contracts. Root-fair scheduling permits at most one extra same-cohort affinity selection, so cache reuse cannot starve unrelated roots.

The 90% target is certified only for one strict cohort using at least 20 route-verified warm samples and a token-weighted verified hit rate. Unverified routes, legacy cohorts, cold starts, and different gateways remain visible but cannot be combined into an “achieved” result. Metrics are available in the Web Console, `lightworker cache-metrics`, the `GET /api/cache-metrics` endpoint, and the MCP `get_cache_metrics` tool.

Context Packs are explicit caller-supplied reference text, capped at 32 KiB, canonically encoded, screened for likely credentials, and treated as untrusted data. LightWorker never automatically reads repository files, logs, environment files, or arbitrary paths into a Context Pack. Prompt and cache events expose hashes and byte counts rather than Context Pack content.

## Privacy and Local State

Task content, events, results, and process information are stored in an SQLite database under `LIGHTWORKER_HOME`. The default state directory is outside the source tree, and the repository's `.gitignore` also excludes common runtime state, databases, logs, environment files, user configuration, and worktree paths; do not point a custom `LIGHTWORKER_HOME` at an unignored location inside the source tree. The public source contains no local credentials or personal paths.

LightWorker itself contains no telemetry module. It only accesses the configured model gateway through the local Codex CLI while executing tasks; whether the source code and prompts involved in a task are sent to a remote service depends on the model you choose and its terms of service.

## Approving Write Tasks

Under `auto_readonly`, the Executor in the plan enters `awaiting_approval`:

```powershell
python -m lightworker tasks --status awaiting_approval
python -m lightworker approve <task-id>
python -m lightworker run
```

The Executor requires the source repository to have no uncommitted changes, then creates:

```text
%LOCALAPPDATA%\LightWorker\worktrees\<task-id>
```

After the task completes, only the Git worktree, branch, diff, and test results are kept; nothing is merged automatically.

## Codex MCP

Generate the configuration snippet:

```powershell
python -m lightworker mcp-config
```

Add the output to `~/.codex/config.toml`, then restart Codex. You can also register it via the CLI:

```powershell
codex mcp add lightworker `
  --env LIGHTWORKER_HOME="$env:LOCALAPPDATA\LightWorker" `
  -- python -m lightworker mcp
```

If you are not launching from the LightWorker source directory, run `pip install -e .` first, or set `cwd` to this project directory in the MCP configuration.

The MCP tools include:

- `orchestrate`
- `delegate_task`
- `delegate_batch`
- `get_task`
- `get_task_tree`
- `list_tasks`
- `wait_tasks`
- `get_events`
- `approve_task`
- `cancel_task`
- `doctor`

Suggested usage from Codex:

```text
Use auto_readonly by default. Only approve execute tasks when the user has explicitly authorized changes.
Multiple Explorers can run in parallel; write tasks on the same repository must run in an isolated worktree.
Workers must return their conclusions as structured evidence through get_task; a natural-language claim of "done" is not accepted as evidence of completion.
```

## CLI Commands

```text
lightworker init
lightworker doctor
lightworker web
lightworker orchestrate
lightworker submit
lightworker run
lightworker tasks
lightworker status
lightworker tree
lightworker events
lightworker approve
lightworker cancel
lightworker mcp
lightworker mcp-config
```

If the console script is not installed, replace `lightworker` with `python -m lightworker`.

## State Machine

```text
queued → starting → running → completed
                    └→ finishing → completed  (Planner)
                           ├→ failed
                           ├→ cancelled
                           └→ blocked

awaiting_approval → queued
```

When the Runner restarts, leftover `starting/running` tasks are marked `orphaned` to avoid silently re-executing write tasks.

## Acknowledgements and Design Influences

LightWorker incorporates the most practical mechanisms from these projects:

- OpenHands: backend, workspace, automated control surface.
- AionUi: Lead/Teammate, task board, asynchronous collaboration.
- Delegate: Git worktree, Reviewer, and Merge Worker concepts.
- Cindy: explicit separation of creation, queuing, dispatch, and completion.
- OpenWorker: fresh context, short lifecycle, read-only exploration.

It does not depend on these projects, and installing any of them is not required.

Project entry points: [Changelog](CHANGELOG.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Issues](https://github.com/ncepuee/LightWorker/issues) · [Releases](https://github.com/ncepuee/LightWorker/releases)

## Current Limitations

- The first release does not include Redis, remote Workers, or Docker management.
- A process lock guarantees only one Scheduler; while the Web Console is running, the remaining MCP instances act as passive clients of the shared state store.
- Whether models such as DeepSeek can reliably execute Codex tool calls depends on the corresponding gateway and model compatibility.
- If a non-Planner Worker ignores the JSON Schema and returns text, the task is saved with a usable result marked `schema_valid=false`; the Planner does not allow this degradation because non-JSON results cannot safely generate a task DAG.
- `auto_execute` still never automatically commits, merges, pushes, publishes, or performs external writes.
- Path restrictions are currently enforced jointly by the workspace, the Codex sandbox, and the prompt; robust isolation against adversarial workloads would require a Docker backend.

## Tests

```powershell
python -m pytest
```

## License

[MIT](LICENSE)
