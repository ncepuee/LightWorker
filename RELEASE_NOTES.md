# LightWorker v0.1.0 — Initial Public Release

LightWorker 是一个本地优先、零第三方 Python 运行时依赖的轻量多 Agent Worker Runner，为 Codex 提供可审计的任务拆分、委派和执行控制面。

## Highlights

- 使用 SQLite WAL 保存依赖任务图、事件、进程与结构化结果。
- 提供 CLI、MCP Server 和无需前端构建链的本地管理页。
- 默认把低推理强度的机械任务路由到 DeepSeek V4 Flash，把规划、复杂编码和审查路由到 OpenAI 智能体。
- 只读任务可自动执行；写任务支持审批和独立 git worktree。
- 本地 Web 管理页使用随机会话令牌、严格回环 Host 校验和安全响应头。
- Wheel 和源码包包含全部 Web 与 JSON Schema 资源。

## Requirements

- Python 3.11+
- Git
- 已认证的 Codex CLI
- 可选：CLIProxyAPI 或其他 Codex 兼容模型网关

## Known limitations

- 第一版不包含远程 Worker、Redis、Docker 隔离或自动合并。
- `auto_execute` 不会自动提交、推送、发布或执行外部写操作。
- 嵌套 Codex 会话若由宿主强制为只读沙箱，Executor 需要在具备 workspace-write 权限的环境中运行。
- 非 OpenAI 模型的工具调用稳定性取决于模型与网关兼容性。
