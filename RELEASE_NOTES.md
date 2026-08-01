<p align="center">
  <img src="https://raw.githubusercontent.com/ncepuee/LightWorker/v0.1.0/lightworker/web/lightworker-app-icon.png" alt="LightWorker" width="128">
</p>

<h1 align="center">LightWorker v0.1.0</h1>

<p align="center"><strong>Initial public release · Local-first multi-agent delegation for Codex</strong></p>

LightWorker 为 Codex 提供可审计的任务拆分、委派、审批和执行控制面。它使用 SQLite 保存任务 DAG，通过短生命周期 Worker 执行任务，并把写操作隔离到独立 git worktree。

## 30 秒安装

大多数用户请选择通用 wheel：

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.1.0/lightworker-0.1.0-py3-none-any.whl
lightworker init
lightworker doctor
```

也可以克隆源码安装：

```bash
git clone https://github.com/ncepuee/LightWorker.git
cd LightWorker
python -m pip install .
```

## Highlights

- SQLite WAL 持久化依赖任务图、事件、进程与结构化结果。
- CLI、Codex MCP 和无需前端构建链的本地 Web Console 共用同一状态库。
- 低推理机械任务默认路由到 DeepSeek V4 Flash；规划、复杂编码与审查路由到 OpenAI 智能体。
- `auto_readonly` 自动运行只读任务；写任务支持人工审批和独立 git worktree。
- 默认忽略用户级 Codex 配置，避免无人值守 Worker 继承外部写入 MCP。
- Web Console 采用字面回环绑定、严格 Host 校验、随机写入令牌和安全响应头。

## 选择下载资产

| 资产 | 用途 |
|---|---|
| `lightworker-0.1.0-py3-none-any.whl` | 推荐；适用于 Python 3.11+ 的通用安装包 |
| `lightworker-0.1.0.tar.gz` | 源码分发包；适合打包者、审计者和离线构建 |
| `SHA256SUMS.txt` | 所有发布资产的 SHA-256 校验值 |
| `lightworker-app-icon.png` | 高分辨率应用图标 |
| `logo.svg` / `favicon.svg` | 矢量品牌标志与浏览器图标 |

## 校验下载

Windows PowerShell：

```powershell
Get-FileHash -Algorithm SHA256 .\lightworker-0.1.0-py3-none-any.whl
```

macOS / Linux：

```bash
sha256sum lightworker-0.1.0-py3-none-any.whl
```

将结果与 `SHA256SUMS.txt` 对照。Release 上传后已经执行过回下载校验，远端资产与本地审计包逐字节一致。

## 验证矩阵

- Windows、Ubuntu、macOS
- Python 3.11、Python 3.13
- 23 项本地 pytest 回归测试
- wheel 与 sdist 构建、`twine check`
- 全新虚拟环境安装、CLI 启动与 8 个包内 Web/Schema 资源检查
- 最终 CI：[GitHub Actions run 30703989136](https://github.com/ncepuee/LightWorker/actions/runs/30703989136)

## 安全与隐私

- 只读任务强制使用 read-only sandbox；写任务强制使用 workspace-write。
- 默认不继承用户 MCP；设置 `codex_ignore_user_config = false` 属于显式不安全兼容选项。
- 取消与完成使用条件状态更新，已取消任务不能被迟到结果“复活”。
- Scheduler 锁保持到活动 Worker 退出，防止双调度和状态覆盖。
- Git 历史、46 个公开文件、wheel、sdist 与 PNG C2PA 元数据已通过独立隐私审核。
- 未发布真实凭据、个人路径、数据库、日志、任务结果、runtime-state 或实际 worktree。

详见 [Security Policy](https://github.com/ncepuee/LightWorker/blob/main/SECURITY.md)。

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

## Source & project links

- [Source at v0.1.0](https://github.com/ncepuee/LightWorker/tree/v0.1.0)
- [Changelog](https://github.com/ncepuee/LightWorker/blob/main/CHANGELOG.md)
- [Issues](https://github.com/ncepuee/LightWorker/issues)
- [Contributing](https://github.com/ncepuee/LightWorker/blob/main/CONTRIBUTING.md)

Initial public release by the LightWorker contributors.
