<p align="center">
  <img src="web/logo.svg" alt="LightWorker task graph converging into an execution core" width="112">
</p>

<h1 align="center">LightWorker</h1>

<p align="center">English | <a href="README_CN.md">中文</a></p>

<p align="center"><strong>Local-first multi-agent delegation and approval control for Codex and ZCode.</strong></p>

<p align="center">
  <a href="https://openai.com/codex/"><img alt="ZCode & Codex Support" src="https://img.shields.io/badge/Dual_Harness-ZCode_%26_Codex-007ACC?logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0iI2ZmZiIgZD0iTTEyIDJMMiA3bDEwIDUgMTAtNS0xMC01ek0yIDE3bDEwIDUgMTAtNS0xMC01LXRvLTUtMTB6bTAgLTRsMTAgNSAxMC01LTEwLTUtMTB6Ii8+PC9zdmc+&logoColor=white"></a>
  <a href="https://chatglm.cn/"><img alt="GLM-5.3-Flash Agent used @0.7.1" src="https://img.shields.io/badge/GLM--5.3--Flash-Agent_used%400.7.1-2563EB"></a>
  <a href="https://github.com/ncepuee/LightWorker"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ncepuee/LightWorker?logo=github&cacheSeconds=86400"></a>
</p>

<p align="center">
  <a href="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/ncepuee/LightWorker/releases/latest"><img alt="Release v0.7.1" src="https://img.shields.io/badge/Release-v0.7.1-31D0AA"></a>
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

LightWorker is a lightweight, local-first multi-agent task runner with no third-party Python runtime dependencies. It provides dual worker harness execution for both OpenAI Codex and ZCode / GLM CLI, persists the task DAG in SQLite, and uses an isolated Git worktree for write tasks.

> **Current release:** `v0.7.1` hardens the native **Dual Worker Harness** architecture with reliable ZCode routing, whole-document result parsing, gateway-independent execution, provider status reporting, and cache-cohort isolation. It retains the v0.7.0 support for both `CodexWorker` (`codex exec`) and `ZCodeWorker` (`node zcode.cjs`) plus the Codex-native subagent bridge introduced in v0.6.0. By default, LightWorker listens only on the local loopback address and does not automatically commit, merge, push, or publish; write tasks require approval and run in an isolated Git worktree. See [CODEX_NATIVE_BRIDGE.md](docs/CODEX_NATIVE_BRIDGE.md) and [README_CN.md](README_CN.md).

## Core Capabilities

| Capability | What it does |
|---|---|
| Dual Worker Harness | Native execution for both OpenAI Codex (`CodexWorker`) and ZCode / GLM CLI (`ZCodeWorker`) with dynamic routing |
| ZCode Auto-Detection | Zero-config discovery for standard ZCode installation paths: `%ProgramFiles%` / `%LOCALAPPDATA%` on Windows, `/Applications/ZCode.app` or `~/Applications/ZCode.app` on macOS |
| Persistent task DAG | SQLite WAL stores tasks, dependencies, events, PIDs, results, and worktree information |
| Codex-native bridge | Durable native dispatch tickets, lease protection, native thread IDs, and host callbacks for `spawn_agent` / wait results |
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
- Codex CLI or ZCode CLI (Auto-detected on Windows)
- A working Codex / ZCode login or a configured model gateway
- CLIProxyAPI/OpenCodex Proxy on the current machine (when using non-OpenAI models)

The local development verification environment is Python 3.13, Git 2.51, Codex CLI, ZCode CLI, and SQLite 3.51.

## Installation

Install the CI-verified universal wheel directly from the v0.7.1 GitHub release:

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.7.1/lightworker-0.7.1-py3-none-any.whl
lightworker init
lightworker doctor
```

SHA-256 checksums for release assets are listed in [`SHA256SUMS-v0.7.1.txt`](SHA256SUMS-v0.7.1.txt). When developing or auditing the source, you can install from a pinned tag:

```bash
git clone --branch v0.7.1 --depth 1 https://github.com/ncepuee/LightWorker.git
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
export LIGHTWORKER_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/lightworker"
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
  --workspace "/path/to/project" `
  --kind explore `
  --model "deepseek/deepseek-v4-flash" `
  --run `
  "Analyze the project structure and list the three modules that most need tests."
```

Let Lead Codex decompose the task automatically:

```powershell
lightworker orchestrate `
  --workspace "/path/to/project" `
  --mode auto_readonly `
  --run `
  "Find the cause of intermittent HTTP 500 errors in the login endpoint and provide an evidence-backed remediation plan."
```

Example default routing in v0.7.1:

| Task type | Default model |
|---|---|
| Planner / design / review / debugging / complex coding | `gpt-5.6-sol` |
| Mechanical execution, formatting, and simple retrieval at `low` reasoning effort | `deepseek/deepseek-v4-flash` |
| Executor | `gpt-5.6-sol` |

When a single task does not specify a model explicitly, routing is automatic based on reasoning effort: `low` uses `deepseek/deepseek-v4-flash`; `medium/high/xhigh` use `gpt-5.6-sol`. In other words, mechanical execution, formatting, and simple retrieval go to Flash, while design, planning, review, debugging, and complex coding go to OpenAI agents.

Model names and the allowlist can be configured in `%LOCALAPPDATA%\LightWorker\config.toml`.

## Web Console

Run this in the project directory:

```bash
lightworker web
```

This starts the local dashboard at `http://127.0.0.1:8765/`.
