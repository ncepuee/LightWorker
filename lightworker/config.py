from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_MODELS = {
    "planner": "gpt-5.6-sol",
    "explore": "deepseek/deepseek-v4-flash",
    "execute": "gpt-5.6-sol",
    "review": "gpt-5.6-sol",
    "fast": "deepseek/deepseek-v4-flash",
    "reasoning": "gpt-5.6-sol",
}

DEFAULT_ALLOWED_MODELS = (
    "gpt-5.5",
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
    "google-antigravity/gemini-3.6-flash",
    "google-antigravity/claude-sonnet-4-6",
    "google-antigravity/claude-opus-4-6-thinking",
    "cursor/kimi-k2.7-code",
    "cursor/grok-4.5",
)


def validate_config(cfg: "Config") -> None:
    bounds = {
        "max_concurrency": (1, 32),
        "max_tasks_per_plan": (1, 12),
        "max_delegation_depth": (0, 8),
        "max_replans": (0, 20),
        "default_timeout_seconds": (10, 86_400),
    }
    for name, (minimum, maximum) in bounds.items():
        value = getattr(cfg, name)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    if isinstance(cfg.poll_interval_seconds, bool) or not isinstance(
        cfg.poll_interval_seconds, (int, float)
    ):
        raise ValueError("poll_interval_seconds must be a number")
    if not 0.01 <= float(cfg.poll_interval_seconds) <= 60:
        raise ValueError("poll_interval_seconds must be between 0.01 and 60")
    if not isinstance(cfg.codex_command, str) or not cfg.codex_command.strip():
        raise ValueError("codex_command cannot be empty")


def default_home() -> Path:
    override = os.environ.get("LIGHTWORKER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "LightWorker"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lightworker"


def resolve_executable(command: str) -> str | None:
    """Resolve Windows npm .cmd shims before extensionless app aliases."""
    if sys.platform == "win32" and not Path(command).suffix:
        cmd = shutil.which(f"{command}.cmd")
        if cmd:
            return cmd
    return shutil.which(command)


@dataclass(slots=True)
class Config:
    home: Path = field(default_factory=default_home)
    max_concurrency: int = 2
    max_tasks_per_plan: int = 6
    max_delegation_depth: int = 1
    max_replans: int = 2
    default_timeout_seconds: int = 1800
    poll_interval_seconds: float = 0.25
    allow_dirty_worktree_source: bool = False
    codex_command: str = "codex"
    # Safe by default: unattended workers must not inherit user MCP servers.
    codex_ignore_user_config: bool = True
    codex_base_url: str | None = None
    codex_model_catalog: str | None = None
    model_defaults: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    allowed_models: tuple[str, ...] = DEFAULT_ALLOWED_MODELS

    @property
    def db_path(self) -> Path:
        return self.home / "lightworker.db"

    @property
    def results_dir(self) -> Path:
        return self.home / "results"

    @property
    def worktrees_dir(self) -> Path:
        return self.home / "worktrees"

    @property
    def scheduler_lock_path(self) -> Path:
        return self.home / "scheduler.lock"

    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    @property
    def package_root(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def schemas_dir(self) -> Path:
        return self.package_root / "schemas"

    @property
    def web_dir(self) -> Path:
        return self.package_root / "web"

    def route_model(self, reasoning_effort: str, requested: str | None = None) -> str:
        """Route mechanical work to Flash and judgment-heavy work to OpenAI."""
        if requested:
            return str(requested)
        return self.model_defaults["fast" if reasoning_effort == "low" else "reasoning"]

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)


def load_config(home: str | Path | None = None, config_path: str | Path | None = None) -> Config:
    cfg = Config(home=Path(home).expanduser().resolve() if home else default_home())
    path = Path(config_path).expanduser().resolve() if config_path else cfg.config_path
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        runner = data.get("runner", {})
        for key in (
            "max_concurrency",
            "max_tasks_per_plan",
            "max_delegation_depth",
            "max_replans",
            "default_timeout_seconds",
            "poll_interval_seconds",
            "allow_dirty_worktree_source",
            "codex_command",
            "codex_ignore_user_config",
            "codex_base_url",
            "codex_model_catalog",
        ):
            if key in runner:
                setattr(cfg, key, runner[key])
        if "models" in data:
            cfg.model_defaults.update({str(k): str(v) for k, v in data["models"].items()})
        if "policy" in data and "allowed_models" in data["policy"]:
            cfg.allowed_models = tuple(str(v) for v in data["policy"]["allowed_models"])
    validate_config(cfg)
    cfg.ensure_dirs()
    return cfg


def write_default_config(cfg: Config, overwrite: bool = False) -> Path:
    if cfg.config_path.exists() and not overwrite:
        return cfg.config_path
    allowed = ",\n  ".join(f'"{model}"' for model in cfg.allowed_models)
    isolated = "true" if cfg.codex_ignore_user_config else "false"
    gateway_lines = ""
    if cfg.codex_base_url:
        gateway_lines += f'codex_base_url = "{cfg.codex_base_url}"\n'
    else:
        gateway_lines += '# codex_base_url = "http://127.0.0.1:10100/v1"\n'
    if cfg.codex_model_catalog:
        catalog = str(Path(cfg.codex_model_catalog).expanduser().resolve()).replace("\\", "\\\\")
        gateway_lines += f'codex_model_catalog = "{catalog}"\n'
    else:
        gateway_lines += '# codex_model_catalog = "C:\\\\Users\\\\you\\\\.codex\\\\opencodex-catalog.json"\n'
    text = f'''# LightWorker local configuration
[runner]
max_concurrency = {cfg.max_concurrency}
max_tasks_per_plan = {cfg.max_tasks_per_plan}
max_delegation_depth = {cfg.max_delegation_depth}
max_replans = {cfg.max_replans}
default_timeout_seconds = {cfg.default_timeout_seconds}
poll_interval_seconds = {cfg.poll_interval_seconds}
allow_dirty_worktree_source = false
codex_command = "codex"
codex_ignore_user_config = {isolated}
{gateway_lines.rstrip()}

[models]
planner = "{cfg.model_defaults['planner']}"
explore = "{cfg.model_defaults['explore']}"
execute = "{cfg.model_defaults['execute']}"
review = "{cfg.model_defaults['review']}"
fast = "{cfg.model_defaults['fast']}"
reasoning = "{cfg.model_defaults['reasoning']}"

[policy]
allowed_models = [
  {allowed}
]
'''
    cfg.config_path.write_text(text, encoding="utf-8")
    return cfg.config_path
