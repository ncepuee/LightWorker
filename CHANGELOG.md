# Changelog

## 0.4.0 - 2026-08-08

本地开发版，尚未同步到 `lightworker-release` 或 GitHub。

### Added

- 管理页新增「清空历史」按钮：一键删除已结束（完成/失败/阻塞/孤立/取消）的任务及其事件与用量记录，活跃与待审批任务不受影响。
- 新增 `POST /api/tasks/purge` 接口与 `store.purge_terminal_tasks`，删除后自动清理孤立的 root budget 记录。
- 新增 `image` 任务类型与 `image_worker` profile（骨架），预留 WorkBuddy Bridge 0.9.0 生图模型路由（`workbuddy-image/hunyuan-image-v3.0-art`），为下一版生图委派做准备。

### Fixed

- worker profile 校验的合法任务类型改为引用 `KNOWN_KINDS`，新增任务类型时不再因硬编码列表导致启动失败。

## 0.3.0 - 2026-08-05

本地开发版升级，尚未同步到 `lightworker-release` 或 GitHub。

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
