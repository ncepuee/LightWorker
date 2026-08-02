<p align="center">
  <img src="https://raw.githubusercontent.com/ncepuee/LightWorker/v0.2.0/lightworker/web/lightworker-app-icon.png" alt="LightWorker" width="128">
</p>

<h1 align="center">LightWorker v0.2.0</h1>

<p align="center"><strong>Profile-based delegation · Dual gateways · Measurable DeepSeek Cache Lab</strong></p>

[English](#english) · [中文](#中文)

## English

LightWorker v0.2.0 turns the original local task runner into a more auditable multi-agent delegation layer. Lead Codex can decompose work, route bounded Worker profiles through OpenCodex or CLIProxyAPI, and measure DeepSeek prefix-cache behavior without combining unrelated cache pools.

### Highlights

- **Worker Profiles:** named Planner, fast, deep, and reviewer contracts bind task kinds, models, reasoning effort, and gateways.
- **Dual-gateway routing:** explicit OpenCodex and CLIProxyAPI routes, native/translated protocol labels, route audits, bounded fallback, and manual escalation.
- **Cache Cohort v2:** cache identities include gateway, response mode, upstream model, reasoning effort, profile, schema, sandbox, Context Pack, configuration scope, and tool contract.
- **Verified Cache Lab:** cold, warm, and indeterminate samples are materialized in SQLite and exposed through the Web Console, CLI, HTTP API, and MCP.
- **Honest 90% target:** certification requires at least 20 route-verified warm samples from one strict cohort. Different gateways or Context Packs are never merged to claim success.
- **Explicit Context Packs:** up to 32 KiB of caller-supplied reference text, canonically encoded, credential-screened, and treated as untrusted data.
- **Fair cache affinity:** the scheduler may select only one additional same-cohort task before returning to root-fair ordering.

### Fixes and hardening

- Deduplicates repeated terminal usage events without collapsing identical requests from different tasks.
- Marks legacy, incomplete, or mismatched-route telemetry as indeterminate.
- Completes historical usage migration in bounded transactional batches and bounds cache windows to prevent timestamp overflow.
- Keeps Context Pack content out of public task responses and telemetry.
- Preserves the secure public default that Workers do not inherit user MCP servers.
- Keeps wheel/sdist Web assets, schemas, favicon, and application icon installable from any working directory.

### Install

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.2.0/lightworker-0.2.0-py3-none-any.whl
lightworker init
lightworker doctor
```

## 中文

LightWorker v0.2.0 将原来的本地任务 Runner 升级为更可审计的多 Agent 委派层。Lead Codex 可以自动拆解任务，通过 OpenCodex 或 CLIProxyAPI 调度受约束的 Worker Profile，并在不混合不同缓存池的前提下度量 DeepSeek 前缀缓存效果。

### 核心更新

- **Worker Profile：** Planner、快速执行、深度执行和 Reviewer 使用明确的任务类型、模型、推理强度与网关契约。
- **双网关路由：** 显式支持 OpenCodex 与 CLIProxyAPI，展示 Native/Translated 协议、路由审计、预算受控的备用重试与人工升级。
- **Cache Cohort v2：** 按网关、响应模式、上游模型、推理强度、Profile、Schema、沙箱、Context Pack、配置作用域和工具契约严格隔离。
- **可核验 Cache Lab：** SQLite 物化冷启动、暖缓存和不确定样本，并通过管理页、CLI、HTTP API 与 MCP 展示。
- **可信的 90% 目标：** 必须在同一严格 Cohort 中取得至少 20 个路由已核验的暖样本；不同网关或 Context Pack 不会合并报“已达标”。
- **显式 Context Pack：** 最多 32 KiB，由调用方主动提供，经过规范编码和疑似凭据检查，并始终作为不可信参考数据。
- **公平缓存亲和：** Scheduler 最多连续增加一次同 Cohort 调度，随后恢复 Root 公平顺序。

### 修复与加固

- 去重 Provider 重复上报的终止 usage，同时不会吞掉不同任务的相同请求。
- 旧版、字段不完整或路由不匹配的缓存遥测统一归为 `indeterminate`。
- 历史 usage 采用有界事务批次完整迁移，并限制缓存时间窗口，避免时间戳溢出。
- Context Pack 正文不会出现在公共任务响应或缓存遥测中。
- 正式包继续默认隔离用户 MCP，兼容模式需要显式开启。
- wheel/sdist 安装后可从任意工作目录加载管理页、Schema、favicon 和应用图标。

### 安装

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.2.0/lightworker-0.2.0-py3-none-any.whl
lightworker init
lightworker doctor
```

## Verification / 验证

- 77 local pytest tests, including a 1,001-event multi-batch migration regression.
- Python 3.11, 3.12, and 3.13 across Windows, Ubuntu, and macOS in GitHub Actions.
- Wheel and sdist build, metadata validation, clean-environment installation, CLI smoke tests, and packaged-resource checks.
- Final tracked-file, history, and distribution privacy scans before publication.

See [CHANGELOG.md](https://github.com/ncepuee/LightWorker/blob/v0.2.0/CHANGELOG.md) for the complete change history.
