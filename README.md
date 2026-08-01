# LightWorker

LightWorker 是一个本地优先、零第三方 Python 运行时依赖的轻量多 Agent Worker Runner。它让 Codex 通过 MCP 提交任务，用 SQLite 保存任务 DAG，通过 `codex exec --json` 执行 Worker，并对写任务使用独立 git worktree。

第一版重点是可靠的协作原语，并提供一个无需前端构建链的本地管理页：

- Lead Codex 自动生成依赖任务图。
- Explorer、Executor、Reviewer 采用明确角色和结构化结果。
- `auto_readonly` 默认自动运行只读任务，将写任务停在审批状态。
- Codex、DeepSeek V4、Claude、Gemini 等模型通过现有 Codex/CLIProxyAPI 模型目录选择。
- SQLite WAL 保存任务、依赖、事件、PID、结果和 worktree。
- MCP Server 与 CLI 使用同一套调度器和状态库。
- Worker 取消会终止完整进程树。
- 本地管理页可创建、筛选、审批、取消任务，并查看结果与事件流。
- 不允许 `danger-full-access`，不自动提交、推送或合并。

## 设计来源

LightWorker 吸收了这些项目最实用的机制：

- OpenHands：后端、工作区、自动化控制面。
- AionUi：Lead/Teammate、任务板、异步协作。
- Delegate：git worktree、Reviewer、Merge Worker 思路。
- Cindy：明确区分创建、排队、派发和完成。
- OpenWorker：新鲜上下文、短生命周期、只读探索。

它不依赖这些项目，也不要求安装其中任何一个。

## 要求

- Python 3.11+
- Git
- Codex CLI
- 已登录或已配置可用模型网关
- 当前机器上的 CLIProxyAPI/OpenCodex Proxy（使用非 OpenAI 模型时）

本机开发验证环境为 Python 3.13、Git 2.51、Codex CLI 0.146.0 和 SQLite 3.51。

## 安装

从 GitHub 克隆后安装：

```bash
git clone https://github.com/ncepuee/LightWorker.git
cd LightWorker
python -m pip install .
```

也可以从 GitHub Release 下载 wheel 后安装：

```bash
python -m pip install lightworker-0.1.0-py3-none-any.whl
```

## 快速开始

在项目目录中直接运行，不必安装依赖：

```powershell
Set-Location C:\path\to\lightworker
$env:LIGHTWORKER_HOME = "$env:LOCALAPPDATA\LightWorker"
python -m lightworker init
python -m lightworker doctor
```

macOS / Linux：

```bash
cd /path/to/lightworker
export LIGHTWORKER_HOME="${XDG_STATE_HOME:-$HOME/.local/state}/lightworker"
python -m lightworker init
python -m lightworker doctor
```

本机 CLIProxyAPI/OpenCodex 配置建议使用隔离初始化：

```powershell
python -m lightworker init --force --isolated-codex `
  --codex-base-url "http://127.0.0.1:10100/v1" `
  --model-catalog "$env:USERPROFILE\.codex\opencodex-catalog.json"
```

提交一个 DeepSeek V4 Flash 只读调查：

```powershell
python -m lightworker submit `
  --workspace "C:\path\to\project" `
  --kind explore `
  --model "deepseek/deepseek-v4-flash" `
  --run `
  "分析项目结构并列出三个最需要测试的模块"
```

让 Lead Codex 自动拆任务：

```powershell
python -m lightworker orchestrate `
  --workspace "C:\path\to\project" `
  --mode auto_readonly `
  --run `
  "定位登录接口偶发500的原因，并给出经过证据支持的修复计划"
```

模型路由：

| 任务类型 | 默认模型 |
|---|---|
| Planner / 设计 / 审查 / 调试 / 复杂编码 | `gpt-5.6-sol` |
| `low` 推理强度的机械执行、格式整理、简单检索 | `deepseek/deepseek-v4-flash` |
| Executor | `gpt-5.6-sol` |

单任务未显式指定模型时按推理强度自动路由：`low` 使用 `deepseek/deepseek-v4-flash`；`medium/high/xhigh` 使用 `gpt-5.6-sol`。也就是把机械执行、格式整理和简单检索交给 Flash，把设计、规划、审查、调试和复杂编码交给 OpenAI 智能体。

模型名称和白名单可以在 `%LOCALAPPDATA%\LightWorker\config.toml` 修改。

## 本地管理页

在项目目录中运行：

```powershell
.\Start-LightWorker-Web.ps1
```

也可以直接执行：

```powershell
python -m lightworker web
python -m lightworker web --no-open --port 8766
```

默认地址是 `http://127.0.0.1:8766/`。页面提供：

- 任务总览、状态筛选和三秒自动刷新。
- 自动规划任务与单 Worker 任务表单。
- 审批 `awaiting_approval` 写任务、取消非终态任务。
- 任务结构化结果、错误信息和事件流查看。
- Codex、CLIProxyAPI、OpenCodex Proxy 与模型白名单状态。

Web 服务只允许绑定字面回环地址 `127.0.0.1` 或 `::1`。每次启动会生成随机会话令牌，写接口必须携带该令牌；页面会自动注入令牌，不需要手工填写。该令牌用于防止浏览器跨站写请求，不用于隔离同一用户下的其他本机进程；本机同用户进程属于受信任边界，并且只读 API 可能返回任务与诊断信息。Web 与 Codex MCP 共享 SQLite 状态库，并通过进程锁保证同一时刻只有一个 Scheduler 执行任务。未持锁的进程处于 standby 状态，仍可提交和查询任务，并会在当前 Scheduler 退出后自动接管。

品牌资产：

- `lightworker/web/logo.svg`：LightWorker Worker 设计的「汇流执行核」矢量标志，用于侧边栏和空状态。
- `lightworker/web/favicon.svg`：16/32 px 光学校正的暗底 favicon。
- `lightworker/web/lightworker-app-icon.png`：GPT Image 生成的高分辨率应用图标，用作 `apple-touch-icon` 和品牌展示资产。

如果用户 Codex 配置里启用了很多 MCP Server，建议让 Worker 使用隔离配置，避免每个子任务重复加载无关工具：

```toml
[runner]
codex_ignore_user_config = true
codex_base_url = "http://127.0.0.1:10100/v1"
codex_model_catalog = "C:\\Users\\you\\.codex\\opencodex-catalog.json"
```

`--ignore-user-config` 仍复用 Codex 的认证目录，但不会加载用户级 MCP 和沙箱默认值；LightWorker 会显式传入只读或 workspace-write sandbox。

隔离是默认安全边界，而不只是性能选项：无人值守 Worker 不应继承可能执行 GitHub、Slack 等外部写操作的用户 MCP。只有明确理解风险并希望兼容用户级配置时，才可把 `codex_ignore_user_config` 改为 `false`；此时 `auto_readonly` 只能约束 Codex 本地沙箱，不能保证第三方 MCP 没有外部副作用。

## 模型网关

LightWorker 不直接保存模型服务的 API Key。它调用本机 Codex CLI，并可通过 Codex 的模型目录连接 OpenAI 或兼容网关。使用 CLIProxyAPI 等本地网关时，建议只监听回环地址，并将认证文件保留在用户配置目录，不要放入项目仓库。

默认路由只是起点：`low` 推理任务交给 DeepSeek V4 Flash，复杂规划、编码与审查交给 `gpt-5.6-sol`。所有可用模型仍受 `config.toml` 中的白名单控制。

## 隐私与本地状态

任务内容、事件、结果和进程信息保存在 `LIGHTWORKER_HOME` 下的 SQLite 数据库中。默认状态目录位于源码树之外，仓库 `.gitignore` 也排除了常见的运行状态、数据库、日志、环境文件、用户配置与 worktree 路径；不要把自定义 `LIGHTWORKER_HOME` 指向源码树内未忽略的位置。公开源码不包含本机凭据或个人路径。

LightWorker 本身不包含遥测模块。它只会在执行任务时通过本机 Codex CLI 访问所配置的模型网关；任务中涉及的源码和提示是否发送到远程服务，取决于你选择的模型及其服务条款。

## 审批写任务

`auto_readonly` 下，计划中的 Executor 会进入 `awaiting_approval`：

```powershell
python -m lightworker tasks --status awaiting_approval
python -m lightworker approve <task-id>
python -m lightworker run
```

Executor 要求源仓库没有未提交改动，然后创建：

```text
%LOCALAPPDATA%\LightWorker\worktrees\<task-id>
```

任务完成后只保留 worktree、分支、diff 和测试结果，不自动合并。

## 接入 Codex MCP

生成配置片段：

```powershell
python -m lightworker mcp-config
```

将输出加入 `~/.codex/config.toml`，然后重启 Codex。也可以使用 CLI 注册：

```powershell
codex mcp add lightworker `
  --env LIGHTWORKER_HOME="$env:LOCALAPPDATA\LightWorker" `
  -- python -m lightworker mcp
```

如果不是从 LightWorker 源码目录启动，请先执行 `pip install -e .`，或者在 MCP 配置中设置 `cwd` 为本项目目录。

MCP 工具包括：

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

Codex 使用建议：

```text
默认使用 auto_readonly。只有用户明确授权修改时才能批准 execute 任务。
多个 Explorer 可以并行；同一个仓库的写任务必须在独立 worktree 执行。
Worker 的结论必须通过 get_task 返回结构化证据，不以自然语言“完成了”作为完成依据。
```

## CLI 命令

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

在未安装 console script 时，将 `lightworker` 替换为 `python -m lightworker`。

## 状态机

```text
queued → starting → running → completed
                           ├→ failed
                           ├→ cancelled
                           └→ blocked

awaiting_approval → queued
```

Runner 重启时，遗留的 `starting/running` 任务会标记为 `orphaned`，避免悄悄重复执行写任务。

## 当前边界

- 第一版没有 Redis、远程 Worker 或 Docker 管理。
- 进程锁保证只有一个 Scheduler；管理页运行时，其余 MCP 实例会作为共享状态库的被动客户端。
- DeepSeek 等模型是否能稳定执行 Codex 工具调用取决于对应网关和模型兼容性。
- 普通 Worker 若忽略 JSON Schema 但返回了文本，任务会以 `schema_valid=false` 保存可用结果；Planner 不允许这种降级，因为非 JSON 结果无法安全生成任务 DAG。
- `auto_execute` 仍不会自动 merge、push、发布或进行外部写操作。
- 路径限制目前由工作区、Codex sandbox 和提示共同约束；强敌对隔离应增加 Docker 后端。

## 测试

```powershell
python -m pytest
```

## 许可证

[MIT](LICENSE)
