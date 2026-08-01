<p align="center">
  <img src="https://raw.githubusercontent.com/ncepuee/LightWorker/v0.1.1/lightworker/web/lightworker-app-icon.png" alt="LightWorker" width="128">
</p>

<h1 align="center">LightWorker v0.1.1</h1>

<p align="center"><strong>Cache-friendly prompts · Observable cache usage · Worktree context fix</strong></p>

这是 LightWorker 的首个补丁版本，重点是提高 DeepSeek、火山方舟等兼容 Provider 的原生前缀缓存复用率，并让缓存效果可以在任务事件流中被审计。

## 安装

```bash
python -m pip install https://github.com/ncepuee/LightWorker/releases/download/v0.1.1/lightworker-0.1.1-py3-none-any.whl
lightworker init
lightworker doctor
```

## 新增功能

- **Prompt Protocol v2**：稳定的安全规则、JSON 输出契约和角色规则位于动态目标之前，列表去重排序，路由策略使用规范 JSON，使相同类型 Worker 更容易命中 Provider 的精确前缀缓存。
- **不含正文的 Prompt 指纹**：`worker.prompt` 事件记录协议版本以及完整提示、稳定前缀、Schema、网关、缓存 cohort 的 SHA-256，不记录正文；确定性指纹不作为匿名机制。
- **缓存用量观测**：兼容 Codex/OpenAI 与 DeepSeek 常见 usage 字段，规范为 `worker.usage` 事件，提供输入、命中、未命中、输出、总 Token 和命中率。
- **更完整 CI**：增加 Python 3.12；Tag 构建校验 Tag 与包版本一致；wheel 和 sdist 分别在干净虚拟环境安装验证。
- **双语与品牌体验**：整合 v0.1.0 后新增的中英文 README、语言切换、Logo、应用图标和 favicon 修复。

## 修复

- 修复动态 Objective 位于稳定协议前方、导致后续公共规则无法被前缀缓存复用的问题。
- 修复 Executor/Reviewer 在隔离 worktree 中运行时，Prompt 仍显示原仓库路径的问题；现在使用真实解析后的执行目录。
- 修复部分浏览器标签页 favicon 未及时刷新或未识别的问题。

## 安全与边界

- 新增事件只保存哈希和 Token 计数，不保存 Prompt、Objective、Workspace、网关 URL、模型目录或凭据明文。
- 仍使用短生命周期 `codex exec --ephemeral`；没有跨 Agent 共享 `previous_response_id`、方舟 session、工具状态或任务结果。
- 写任务仍需审批并进入独立 Git worktree；不会自动 commit、merge、push 或发布。

## 下载资产

| 资产 | 用途 |
|---|---|
| `lightworker-0.1.1-py3-none-any.whl` | 推荐；Python 3.11+ 通用安装包 |
| `lightworker-0.1.1.tar.gz` | 源码分发包 |
| `SHA256SUMS.txt` | 发布资产 SHA-256 |
| `lightworker-app-icon.png` | 高分辨率应用图标 |
| `logo.svg` / `favicon.svg` | 矢量品牌标志与浏览器图标 |

## 验证

- 30 项本地 pytest 回归测试
- Python 语法编译与 `git diff --check`
- wheel/sdist 构建与 `twine check`
- wheel/sdist 独立干净环境安装、CLI 和包内资源验证
- 发布前源码、Git 历史和构建资产隐私扫描
- GitHub Actions：Windows、Ubuntu、macOS × Python 3.11、3.12、3.13

完整变更见 [Changelog](https://github.com/ncepuee/LightWorker/blob/v0.1.1/CHANGELOG.md)，源码见 [v0.1.1 Tag](https://github.com/ncepuee/LightWorker/tree/v0.1.1)。
