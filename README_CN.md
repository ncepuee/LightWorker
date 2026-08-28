<p align="center">
  <img src="lightworker/web/logo.svg" alt="LightWorker task graph converging into an execution core" width="112">
</p>

<h1 align="center">LightWorker</h1>

<p align="center"><a href="README.md">English</a> | 中文</p>

<p align="center"><strong>Local-first multi-agent delegation and approval control for Codex.</strong></p>

<p align="center">
  <a href="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ncepuee/LightWorker/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/ncepuee/LightWorker/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/ncepuee/LightWorker?display_name=tag&sort=semver"></a>
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

LightWorker 是一个本地优先、零运行时依赖的轻量多 Agent Worker Runner。它让 Codex 通过 MCP 提交任务，用 SQLite 保存任务 DAG，通过 `codex exec --json` 执行 Worker，并对写任务使用独立 git worktree。

本机版 `0.5.0` 将 LightWorker 定位为 OpenCodex、CLIProxyAPI 和本地模型桥接器之上的策略调度层：

- Lead Codex 自动生成依赖任务图。
- Explorer、Executor、Reviewer 采用明确角色和结构化结果。
- `auto_readonly` 默认自动运行只读任务，将写任务停在审批状态。
- Codex、DeepSeek V4、Claude、Gemini 等模型通过现有 Codex/CLIProxyAPI 模型目录选择。
- SQLite WAL 保存任务、依赖、事件、PID、结果和 worktree。
- MCP Server 与 CLI 使用同一套调度器和状态库。
- Worker 取消会终止完整进程树。
- 本地管理页可创建、筛选、审批、取消任务，并查看结果与事件流。
- 任务创建时固定网关、上游模型、模型目录 revision 和协议模式；目录改变后旧任务会失败关闭，避免运行中漂移。
- 网关显式声明 `responses`、`translated_responses`、`chat_to_responses`、`web_search`、`codex_tools` 和 `native_subagents` 等能力。
- 任务按所需能力选择网关；需要原生 `web_search` 时不会错误回退到 translated 网关。
- `lightworker_worker` 与 `native_subagent` 是两个独立执行通道，原生子代理不得递归调用 LightWorker。
- WorkBuddy 11 个模型从 OpenCodex 目录发现，LightWorker 不保存登录信息或 Bridge 密钥；Bridge 0.5.0 按显式 `workbuddy/<model>` 请求自适应直达，Chat-only Bridge 必须先经过 `chat_to_responses` 兼容层。
- 审批绑定 `approval_id + scope_digest`，覆盖文件范围、网关、能力、沙箱、worktree 和目录 revision。
- OpenCodex 默认走 Native Responses；CLIProxyAPI 作为显式手动备用，标记为 Responses → Chat 转译。
- 稳定 Prompt v5 Profile/执行通道前缀与 cache cohort 分组，记录缓存输入 token 和命中率。
- `planner`、`fast_worker`、`deep_worker`、`reviewer` 四个可配置 Worker Profile。
- 区分请求路由、解析路由与上游观测；没有上游证据时明确显示 `unverified`。
- 根任务限制并发、尝试、备用重试和升级次数，避免嵌套委派失控。
- Worker 结果经过确定性 Schema 规范化；完整原始响应默认不落盘，只保存哈希和字节数。
- 失败、阻塞或 Schema 无效的只读任务可手工升级到深度 Worker；原任务不被覆盖。
- 显式 Context Pack 作为稳定 Prompt 前缀，不会自动读取仓库、日志、环境文件或任意路径。
- `cache_cohort.v2` 严格隔离网关、端点、模型、推理强度、Profile、Schema、沙箱、Context Pack 和工具契约。
- Root 公平优先、同 Cohort 最多一次额外亲和调度，避免为了缓存长期饿死其他任务。
- SQLite 物化冷/暖缓存样本，Dashboard 分开展示总体、冷启动、暖缓存与路由核验状态。
- 不允许 `danger-full-access`，不自动提交、推送或合并。
- 注册网关的 Worker 只继承最小系统环境和显式 `worker_env_allowlist`；旧式 legacy 模式保持兼容。
- Worktree 创建前检查本地与 `origin` 完整 ref 命名空间，创建后核验实际分支和目录归属。

### 0.3.0 本地升级重点

- DeepSeek 原生联网搜索任务：提交 `required_capabilities = ["web_search"]`，只会选择声明该能力的 Native Responses 网关。
- OpenCodex 原生子代理：提交 `execution_channel = "native_subagent"`；LightWorker 负责外层预算、状态和审计。
- WorkBuddy：经实测可走 `LightWorker → OpenCodex openai-chat 适配 → WorkBuddy Bridge`；`auto`、Hy3、DeepSeek、GLM、Kimi 和 MiniMax 共 11 个入口分别保留独立路由、计费与缓存审计。
- 本地调度并发和单根任务并发均为 3；旧根任务预算不会追溯修改，新建任务才采用新上限。
- 模型目录热更新：新任务取得新 revision；已排队任务发现 revision 改变时会阻塞并要求重新创建。
- 审批页面会显示完整权限摘要，审批后的任务规范若发生变化会被拒绝。

### 0.4.0 本地升级重点

- 管理页新增「清空历史」：一键删除已结束（完成/失败/阻塞/孤立/取消）任务及其事件与用量记录，活跃与待审批任务不受影响（`POST /api/tasks/purge`）。
- 新增 `image` 任务类型与 `image_worker` profile（骨架），为 WorkBuddy Bridge 0.9.0 生图模型路由（`workbuddy-image/hunyuan-image-v3.0-art`）做准备。
- Worker profile 校验改为引用 `KNOWN_KINDS`，新增任务类型不再受硬编码列表限制。

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

## 快速开始

在项目目录中直接运行，不必安装依赖：

```powershell
Set-Location C:\path\to\lightworker
$env:LIGHTWORKER_HOME = "$env:LOCALAPPDATA\LightWorker"
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
  --profile fast_worker `
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

| Profile | 默认模型 | 默认强度 | 用途 |
|---|---|---|---|
| `planner` | `gpt-5.6-sol` | `high` | 分解与路由决策 |
| `fast_worker` | `deepseek/deepseek-v4-flash` | `low` | 机械执行、整理、简单检索 |
| `executor` | `gpt-5.6-luna` | `max` | 最高频的编码执行角色，在隔离 worktree 中按既定步骤写改代码 |
| `deep_worker` | `gpt-5.6-luna` | `max` | 有边界的深度调查或实现 |
| `reviewer` | `gpt-5.6-terra` | `high` | 独立审核与证据验收 |

单任务未显式指定模型时按推理强度自动路由：`low` 使用 `deepseek/deepseek-v4-flash`；`medium/high/xhigh` 使用 `gpt-5.6-sol`。例外是未指定 profile 的 `execute` 任务：它走 `[models]` 的 `execute` 默认值 `gpt-5.6-luna`，因为 Executor 是最高频角色，用性价比编码模型可以显著节省 Sol 额度。也就是把机械执行、格式整理和简单检索交给 Flash，把编码实现交给 Luna，把设计、规划、审查、调试和复杂决策交给 OpenAI 智能体。

模型名称和白名单可以在 `%LOCALAPPDATA%\LightWorker\config.toml` 修改。

提交一个使用 DeepSeek 原生联网搜索能力的 Explorer：

```powershell
python -m lightworker submit `
  --workspace "C:\path\to\project" `
  --profile fast_worker `
  --require-capability web_search `
  "调研依赖的最新官方兼容性变化"
```

让 OpenCodex 在一个受 LightWorker 审计的任务内使用其原生子代理：

```powershell
python -m lightworker submit `
  --workspace "C:\path\to\project" `
  --kind execute `
  --profile executor `
  --execution-channel native_subagent `
  "按既定方案完成实现并汇总子代理结果"
```

### DeepSeek Cache Lab

重复任务可以提供同一份经过人工审阅的 Context Pack：

```powershell
python -m lightworker submit `
  --workspace "C:\path\to\project" `
  --profile fast_worker `
  --context-pack-file ".\context-pack.md" `
  "检查模块 A 的测试缺口"
```

管理页和 MCP `delegate_task` 支持 `context_pack` 字符串或 `{name, version, content}` 对象。内容最大 32KiB，保存在任务规范中但不会通过公共任务 API 回显；不要写入密钥、动态日志或无关填充文本。

查看指标：

```powershell
python -m lightworker cache-metrics `
  --model deepseek/deepseek-v4-flash `
  --gateway opencodex `
  --window-seconds 3600
```

90% 目标只针对同一严格 Cohort、路由已核验的暖缓存加权命中率。默认至少需要 20 个已核验暖样本；样本不足、路由未核验和跨网关调用会分别显示，不能合并成“已达标”。

### 双网关路由

推荐配置见 `config.example.toml`。核心规则是：

- `opencodex` 是默认网关，`response_mode = "native"`。
- `cliproxyapi` 只作为手动备用，`response_mode = "translated"`。
- 备用网关必须具备任务要求的全部能力，否则不生成备用线路。
- `workbuddy/hy3` 声明 `chat_to_responses` 为必需能力；仅在 OpenCodex 的 `openai-chat` Provider 已完成真实 Responses 生成测试后声明该能力。缺失时显示“当前不可路由”，不会等到上游 502 才失败。
- WorkBuddy 不直连 LightWorker：Bridge 只提供 Chat Completions，由 OpenCodex 负责 Responses 协议适配和模型路由。
- Bridge 0.5.0 的 Dashboard 模型仅作为缺省/无效请求的回退；LightWorker 对目录中不存在的显式模型失败关闭，防止静默跑到错误模型。
- CLIProxyAPI 客户端密钥仅通过 `CLIPROXYAPI_CLIENT_KEY` 环境变量注入；不要写入 TOML、任务参数或仓库。
- 第一版绝不自动 fallback。失败的只读任务可在管理页点击备用重试，或执行 `lightworker retry-fallback <task-id>`；原任务保持不变。
- Executor 不允许备用重试，以免重复产生写操作。
- 每个根任务默认最多一次备用重试和一次深度升级；可在配置中收紧，但不能突破全局上限。

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
- 显式选择网关，并展示规范模型、上游模型、Native/Translated 协议和备用线路。
- 选择 Worker Profile，并查看请求路由、解析路由、上游核验状态和根任务预算。
- 查看 Schema 的 `valid`、`normalized`、`invalid` 状态；若显式开启原始结果留存，页面会显示尽力脱敏后的路径。
- 对失败、阻塞或 Schema 无效的只读任务创建一次预算受控的深度升级尝试。
- 查看审批范围和 digest，审批 `awaiting_approval` 写任务、取消非终态任务。
- 任务结构化结果、错误信息和事件流查看。
- Codex、CLIProxyAPI、OpenCodex Proxy 与模型白名单状态。

Web 服务只允许绑定本机回环地址。每次启动会生成随机会话令牌，写接口必须携带该令牌；页面会自动注入令牌，不需要手工填写。Web 与 Codex MCP 共享 SQLite 状态库，并通过进程锁保证同一时刻只有一个 Scheduler 执行任务。未持锁的进程处于 standby 状态，仍可提交和查询任务，并会在当前 Scheduler 退出后自动接管。

品牌资产：

- `web/logo.svg`：LightWorker Worker 设计的「汇流执行核」矢量标志，用于侧边栏和空状态。
- `web/favicon.svg`：16/32 px 光学校正的暗底 favicon。
- `web/lightworker-app-icon.png`：GPT Image 生成的高分辨率应用图标，用作 `apple-touch-icon` 和品牌展示资产。

如果用户 Codex 配置里启用了很多 MCP Server，建议让 Worker 使用隔离配置，避免每个子任务重复加载无关工具：

```toml
[runner]
codex_ignore_user_config = true
codex_base_url = "http://127.0.0.1:10100/v1"
codex_model_catalog = "C:\\Users\\you\\.codex\\opencodex-catalog.json"
```

隔离模式会为每个 LightWorker 状态目录创建干净的 `codex-home`，避免 Worker 重复加载用户级 skills、plugins 和 MCP；模型目录、网关和 sandbox 都由 LightWorker 显式传入。凭据只在选中网关需要时从指定环境变量注入，其他 Worker 环境变量必须通过 `worker_env_allowlist` 显式声明。

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
- `retry_fallback`
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
lightworker retry-fallback
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
