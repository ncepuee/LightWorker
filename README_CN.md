<p align="center">
  <img src="web/logo.svg" alt="LightWorker task graph converging into an execution core" width="112">
</p>

<h1 align="center">LightWorker</h1>

<p align="center"><a href="README.md">English</a> | 中文</p>

<p align="center"><strong>面向 Codex 与 ZCode 的本地优先多 Agent 委派与审批控制调度器。</strong></p>

<p align="center">
  <a href="https://openai.com/codex/"><img alt="ZCode & Codex 支持" src="https://img.shields.io/badge/Dual_Harness-ZCode_%26_Codex-007ACC?logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0iI2ZmZiIgZD0iTTEyIDJMMiA3bDEwIDUgMTAtNS0xMC01ek0yIDE3bDEwIDUgMTAtNS0xMC01LXRvLTUtMTB6bTAgLTRsMTAgNSAxMC01LTEwLTUtMTB6Ii8+PC9zdmc+&logoColor=white"></a>
  <a href="https://chatglm.cn/"><img alt="GLM-5.3-Flash Agent used @0.7.0" src="https://img.shields.io/badge/GLM--5.3--Flash-Agent_used%400.7.0-2563EB"></a>
  <a href="https://github.com/ncepuee/LightWorker"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ncepuee/LightWorker?logo=github&cacheSeconds=86400"></a>
</p>

<p align="center">
  <a href="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/ncepuee/LightWorker/releases/latest"><img alt="Release v0.7.0" src="https://img.shields.io/badge/Release-v0.7.0-31D0AA"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-31D0AA.svg"></a>
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#本地管理页">Web Console</a> ·
  <a href="#接入-codex-mcp">Codex MCP</a> ·
  <a href="SECURITY.md">安全策略</a> ·
  <a href="https://github.com/ncepuee/LightWorker/releases">Releases</a> ·
  <a href="CONTRIBUTING.md">贡献</a>
</p>

LightWorker 是一个本地优先、零运行时依赖的轻量多 Agent Worker Runner。它支持 OpenAI Codex 与 ZCode / GLM CLI 原生双 Worker Harness，用 SQLite 保存任务 DAG，并通过隔离 Git worktree 执行写任务。

正式版 `0.7.0` 引入原生 **Dual Worker Harness** 架构，并继承 `0.6.0` 的原生 Subagent Bridge 能力：

- **Dual Worker Harness (`ZCodeWorker` + `CodexWorker`)**：根据任务的 `harness` 字段动态路由原生执行 `node zcode.cjs` 或 `codex exec`。
- **Windows ZCode 零配置自动探测**：自动识别标准路径（如 `D:\ZCode\resources\glm\zcode.cjs`、`Program Files` 及 `AppData`）。
- **安全模式对齐**：写任务严格映射至 `--mode edit`，只读任务映射至 `--mode plan`，严格拒绝破坏性 `yolo` 模式。
- Lead Codex 自动生成依赖任务图。
- Explorer、Executor、Reviewer 采用明确角色和结构化结果。
- `auto_readonly` 默认自动运行只读任务，将写任务停在审批状态。
- Codex、ZCode、DeepSeek V4、Claude、Gemini 等模型通过模型目录选择。
- SQLite WAL 保存任务、依赖、事件、PID、结果和 worktree。
- MCP Server 与 CLI 使用同一套调度器和状态库。
- Worker 取消会终止完整进程树。
- 本地管理页可创建、筛选、审批、取消任务，并查看结果与事件流。
- 任务创建时固定网关、上游模型、模型目录 revision 和协议模式；目录改变后旧任务会失败关闭，避免运行中漂移。
- 网关显式声明 `responses`、`translated_responses`、`chat_to_responses`、`web_search`、`codex_tools` 和 `native_subagents` 等能力。
- 审批绑定 `approval_id + scope_digest`，覆盖文件范围、网关、能力、沙箱、worktree 和目录 revision。
- 稳定 Prompt v5 Profile/执行通道前缀与 cache cohort 分组，记录缓存输入 token 和命中率。
- `planner`、`fast_worker`、`deep_worker`、`reviewer` 四个可配置 Worker Profile。
- SQLite 物化冷/暖缓存样本，Dashboard 分开展示总体、冷启动、暖缓存与路由核验状态。
- 不允许 `danger-full-access`，不自动提交、推送或合并。
- Worktree 创建前检查本地与 `origin` 完整 ref 命名空间，创建后核验实际分支和目录归属。

### 0.7.0 本地升级重点

- **原生双执行引擎**：完整实现 `ZCodeWorker` 与 `CodexWorker` 双抽象。
- **Windows ZCode 路径自动发现**：开箱即用支持 Windows ZCode 环境。
- **System Overview & Doctor 支持**：UI 与诊断命令实时展示双 Harness 环境状态。

### 0.6.0 升级回顾

- **真实 Codex 原生 Subagent Bridge**：支持原生 `spawn_agent` 与等待线程回写。
- **动态能力路由**：网关显式声明能力，按需分发。

### 快速安装

从 v0.7.0 Release 直接安装已验证的通用 Wheel 包：

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.7.0/lightworker-0.7.0-py3-none-any.whl
lightworker init
lightworker doctor
```
