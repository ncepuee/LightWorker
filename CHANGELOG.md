# Changelog

## 0.5.1 - 2026-08-28

### Added

- System 视图新增「目录 / 白名单 / 显式路由」三层计数芯片，并解释只有白名单内且已声明路由的模型可委派，避免把路由表误读为上游目录全集。
- 网关表新增「目录」列：上游目录模型数（含 live 合并标记）、workbuddy 计数与 revision 提示。
- 概览网关健康卡片在元信息行追加目录模型数。

## 0.5.0 - 2026-08-28

### Added

- 全新 Web Console（Mission Control 设计语言，零依赖、CSP 自闭合，无外部字体/CDN）：
  - 哈希路由四视图：概览（KPI 卡片、网关健康、审批收件箱、最近任务）、任务（看板/列表双视图 + 状态筛选芯片 + 搜索）、Cache Lab（目标命中率进度条与 Cohort 明细）、系统（运行时、预算与缓存配置、网关、模型路由、Worker Profile 全量配置）。
  - `Ctrl+K` 命令面板：搜索并跳转任务、直达常用命令（新建任务、刷新、清空历史、视图切换）。
  - 任务详情抽屉改为四标签布局（概览 / 结果 / 治理 / 时间线），JSON 输出带语法高亮，事件时间线按结果类型着色。
  - 相对时间显示、运行中状态脉冲动画、调度器实时状态卡、任务侧栏计数徽章、中/英双语全覆盖。

### Changed

- `styles.css` / `app.js` 全量重写为设计令牌驱动的设计系统；静态文件名与 CSP 策略保持不变，服务端无需改动。
- 修正 0.3.0 / 0.4.0 条目中过时的「尚未同步」标注。

## 0.4.0 - 2026-08-08

### Added

- 管理页新增「清空历史」按钮：一键删除已结束（完成/失败/阻塞/孤立/取消）的任务及其事件与用量记录，活跃与待审批任务不受影响。
- 新增 `POST /api/tasks/purge` 接口与 `store.purge_terminal_tasks`，删除后自动清理孤立的 root budget 记录。
- 新增 `image` 任务类型与 `image_worker` profile（骨架），预留 WorkBuddy Bridge 0.9.0 生图模型路由（`workbuddy-image/hunyuan-image-v3.0-art`），为下一版生图委派做准备。

### Fixed

- worker profile 校验的合法任务类型改为引用 `KNOWN_KINDS`，新增任务类型时不再因硬编码列表导致启动失败。

## 0.3.0 - 2026-08-05

### Added

- 能力感知网关路由和兼容性回退过滤。
- `lightworker_worker` / `native_subagent` 执行通道。
- WorkBuddy 提供方与计费类别审计。
- 模型级 `required_capabilities`；Chat-only WorkBuddy Bridge 默认要求 `chat_to_responses`。
- OpenCodex 模型目录 revision、模型数和 WorkBuddy 模型数快照。
- 绑定权限范围的审批 ID 与 SHA-256 digest。
- Worker 环境变量显式 allowlist。

### Changed

- Prompt 协议升级到 `lightworker.prompt.v5`，缓存 cohort 纳入执行通道、能力和目录 revision。
- 本地管理页显示提供方、执行通道、网关能力和审批范围。
- 本地管理页侧栏与健康接口显示由服务端注入的当前版本号。
- 经真实生成验证后，为 OpenCodex 网关声明 `chat_to_responses`，开放 `workbuddy/hy3` 的 LightWorker 路由。
- 对齐 WorkBuddy Bridge 0.5.0，自适应开放 11 个显式 WorkBuddy 模型入口，并在目录缺失时失败关闭。
- 全局 Worker 与单根任务并发上限从 2 提升为 3。
- Worktree 创建前检查本地与远程 tracking ref，创建后验证 HEAD 和目录。

### Safety

- 需要 `web_search` 的任务不会回退到不兼容的 translated 网关。
- 目录中可见但协议不兼容的 WorkBuddy 模型会在提交时失败关闭。
- 模型目录更新后，旧的未执行任务失败关闭并要求按新 revision 重建。
- 审批后任务范围发生变化时拒绝执行。
- 新增 `[runner] codex_sandbox_network_access` 配置（默认关闭）：开启后 Worker 沙箱在保留 workspace-write 文件限制的同时放行出站网络，使 gh / git push 类发布任务成为可能。开启该开关时 Worker 不再使用 `--ephemeral`（ephemeral 会话会丢弃 `-c` 沙箱覆盖，导致网络仍被拦截），隔离性由 `CODEX_HOME` 继续保证。
