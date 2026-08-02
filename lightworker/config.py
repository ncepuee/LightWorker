
from __future__ import annotations

import os
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .cache import CACHE_WINDOW_MAX_SECONDS


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
        "root_max_concurrency": (1, 32),
        "root_max_attempts": (1, 100),
        "root_max_retries": (0, 20),
        "root_max_escalations": (0, 20),
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
    for name in (
        "allow_dirty_worktree_source", "retain_redacted_raw_results", "codex_ignore_user_config",
    ):
        if not isinstance(getattr(cfg, name), bool):
            raise ValueError(f"{name} must be a boolean")
    if not isinstance(cfg.codex_command, str) or not cfg.codex_command.strip():
        raise ValueError("codex_command cannot be empty")

RESPONSE_MODES = {"native", "translated"}
REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
_PROFILE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    name: str
    base_url: str | None
    response_mode: str = "native"
    model_catalog: str | None = None
    api_key_env: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ModelRoute:
    primary: str
    fallback: tuple[str, ...] = ()
    upstream_models: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkerProfile:
    """A named, reusable worker role independent of a gateway implementation."""

    name: str
    description: str
    model: str
    reasoning_effort: str
    gateway: str | None = None
    allowed_kinds: tuple[str, ...] = ("explore",)


DEFAULT_WORKER_PROFILES = {
    "planner": WorkerProfile(
        name="planner",
        description="Break down ambiguous goals and make bounded routing decisions.",
        model="gpt-5.6-sol",
        reasoning_effort="high",
        allowed_kinds=("plan",),
    ),
    "fast_worker": WorkerProfile(
        name="fast_worker",
        description="Perform narrow, repeatable, low-judgment exploration or mechanical work.",
        model="deepseek/deepseek-v4-flash",
        reasoning_effort="low",
        allowed_kinds=("explore", "execute"),
    ),
    "deep_worker": WorkerProfile(
        name="deep_worker",
        description="Handle bounded implementation or investigation that benefits from deeper reasoning.",
        model="gpt-5.6-luna",
        reasoning_effort="max",
        allowed_kinds=("explore", "execute", "review"),
    ),
    "reviewer": WorkerProfile(
        name="reviewer",
        description="Independently inspect evidence, tests, and implementation risks.",
        model="gpt-5.6-terra",
        reasoning_effort="high",
        allowed_kinds=("review",),
    ),
}


@dataclass(frozen=True, slots=True)
class RouteSelection:
    model: str
    gateway: str
    upstream_model: str
    response_mode: str
    fallback_gateway: str | None
    cache_cohort: str


@dataclass(frozen=True, slots=True)
class ProfileSelection:
    """The role defaults after applying explicit caller overrides."""

    profile: str | None
    model: str
    reasoning_effort: str
    gateway: str | None
    allowed_kinds: tuple[str, ...] = ()


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
    root_max_concurrency: int = 2
    root_max_attempts: int = 8
    root_max_retries: int = 1
    root_max_escalations: int = 1
    default_timeout_seconds: int = 1800
    poll_interval_seconds: float = 0.25
    cache_affinity_enabled: bool = True
    cache_affinity_window_seconds: int = 300
    cache_warm_window_seconds: int = 3600
    cache_target_hit_rate: float = 0.90
    cache_min_warm_samples: int = 20
    cache_config_scope: str = "lightworker.cache.default.v1"
    cache_tool_contract: str = "codex.exec.v1"
    allow_dirty_worktree_source: bool = False
    retain_redacted_raw_results: bool = False
    codex_command: str = "codex"
    # Secure public default: unattended workers must not inherit user MCP servers.
    codex_ignore_user_config: bool = True
    codex_base_url: str | None = None
    codex_model_catalog: str | None = None
    default_gateway: str = "legacy"
    gateways: dict[str, GatewayConfig] = field(default_factory=dict)
    model_routes: dict[str, ModelRoute] = field(default_factory=dict)
    model_defaults: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    worker_profiles: dict[str, WorkerProfile] = field(
        default_factory=lambda: dict(DEFAULT_WORKER_PROFILES)
    )
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

    def resolve_profile(
        self,
        profile: str | None,
        *,
        kind: str | None = None,
        model: str | None = None,
        gateway: str | None = None,
        reasoning_effort: str | None = None,
    ) -> ProfileSelection:
        """Resolve a named role while retaining legacy no-profile routing behavior.

        Explicit fields take precedence over a profile.  A caller that omits a
        profile receives the same model routing defaults as before this feature.
        """
        if profile is None:
            effort = reasoning_effort or "medium"
            return ProfileSelection(
                profile=None,
                model=self.route_model(effort, model),
                reasoning_effort=effort,
                gateway=gateway,
            )
        selected = self.worker_profiles.get(profile)
        if not selected:
            raise ValueError(f"Unknown worker profile: {profile}")
        if kind and kind not in selected.allowed_kinds:
            raise ValueError(f"Worker profile {profile!r} does not allow task kind {kind!r}")
        return ProfileSelection(
            profile=profile,
            model=model or selected.model,
            reasoning_effort=reasoning_effort or selected.reasoning_effort,
            gateway=gateway if gateway is not None else selected.gateway,
            allowed_kinds=selected.allowed_kinds,
        )

    def gateway_config(self, name: str) -> GatewayConfig:
        if not self.gateways:
            if name != "legacy":
                raise ValueError(f"Unknown gateway: {name}")
            return GatewayConfig(
                name="legacy",
                base_url=self.codex_base_url,
                model_catalog=self.codex_model_catalog,
                response_mode="native",
            )
        gateway = self.gateways.get(name)
        if not gateway or not gateway.enabled:
            raise ValueError(f"Unknown or disabled gateway: {name}")
        return gateway

    def resolve_route(
        self,
        reasoning_effort: str,
        requested_model: str | None = None,
        requested_gateway: str | None = None,
    ) -> RouteSelection:
        model = self.route_model(reasoning_effort, requested_model)
        route = self.model_routes.get(model)
        default_gateway = self.default_gateway if self.gateways else "legacy"
        primary = route.primary if route else default_gateway
        gateway_name = requested_gateway or primary
        allowed = {primary, *(route.fallback if route else ())}
        if requested_gateway and requested_gateway not in allowed:
            raise ValueError(f"Gateway {requested_gateway!r} is not configured for model {model!r}")
        gateway = self.gateway_config(gateway_name)
        upstream_model = route.upstream_models.get(gateway_name, model) if route else model
        fallback = next(
            (
                name
                for name in (route.fallback if route else ())
                if name != gateway_name and name in self.gateways and self.gateways[name].enabled
            ),
            None,
        )
        return RouteSelection(
            model=model,
            gateway=gateway_name,
            upstream_model=upstream_model,
            response_mode=gateway.response_mode,
            fallback_gateway=fallback,
            cache_cohort=f"{gateway_name}:{gateway.response_mode}:{upstream_model}",
        )

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
            "root_max_concurrency",
            "root_max_attempts",
            "root_max_retries",
            "root_max_escalations",
            "default_timeout_seconds",
            "poll_interval_seconds",
            "cache_affinity_enabled",
            "cache_affinity_window_seconds",
            "cache_warm_window_seconds",
            "cache_target_hit_rate",
            "cache_min_warm_samples",
            "cache_config_scope",
            "cache_tool_contract",
            "allow_dirty_worktree_source",
            "retain_redacted_raw_results",
            "codex_command",
            "codex_ignore_user_config",
            "codex_base_url",
            "codex_model_catalog",
            "default_gateway",
        ):
            if key in runner:
                setattr(cfg, key, runner[key])
        if "models" in data:
            cfg.model_defaults.update({str(k): str(v) for k, v in data["models"].items()})
        if "policy" in data and "allowed_models" in data["policy"]:
            cfg.allowed_models = tuple(str(v) for v in data["policy"]["allowed_models"])
        for name, value in data.get("gateways", {}).items():
            cfg.gateways[str(name)] = GatewayConfig(
                name=str(name),
                base_url=str(value["base_url"]).rstrip("/") if value.get("base_url") else None,
                response_mode=str(value.get("response_mode", "native")),
                model_catalog=str(value["model_catalog"]) if value.get("model_catalog") else None,
                api_key_env=str(value["api_key_env"]) if value.get("api_key_env") else None,
                enabled=bool(value.get("enabled", True)),
            )
        for model, value in data.get("model_routes", {}).items():
            cfg.model_routes[str(model)] = ModelRoute(
                primary=str(value.get("primary", cfg.default_gateway)),
                fallback=tuple(str(item) for item in value.get("fallback", [])),
                upstream_models={str(k): str(v) for k, v in value.get("upstream_models", {}).items()},
            )
        for name, value in data.get("worker_profiles", {}).items():
            profile_name = str(name)
            base_profile = cfg.worker_profiles.get(profile_name)
            cfg.worker_profiles[profile_name] = WorkerProfile(
                name=profile_name,
                description=str(value.get("description", base_profile.description if base_profile else "")),
                model=str(value.get("model", base_profile.model if base_profile else "")),
                reasoning_effort=str(value.get("reasoning_effort", base_profile.reasoning_effort if base_profile else "medium")),
                gateway=(
                    str(value["gateway"])
                    if value.get("gateway")
                    else (base_profile.gateway if base_profile else None)
                ),
                allowed_kinds=tuple(
                    str(item)
                    for item in value.get(
                        "allowed_kinds", base_profile.allowed_kinds if base_profile else ["explore"]
                    )
                ),
            )
    validate_config(cfg)
    _validate_gateways(cfg)
    _validate_worker_profiles(cfg)
    _validate_cache_lab(cfg)
    cfg.ensure_dirs()
    return cfg


def _validate_gateways(cfg: Config) -> None:
    if not cfg.gateways:
        return
    if cfg.default_gateway not in cfg.gateways:
        raise ValueError(f"default_gateway is not configured: {cfg.default_gateway}")
    for name, gateway in cfg.gateways.items():
        if gateway.response_mode not in RESPONSE_MODES:
            raise ValueError(f"Unsupported response_mode for {name}: {gateway.response_mode}")
        if gateway.base_url:
            parsed = urlparse(gateway.base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid base_url for gateway {name}")
        if gateway.api_key_env and not gateway.api_key_env.replace("_", "").isalnum():
            raise ValueError(f"Invalid api_key_env for gateway {name}")
    for model, route in cfg.model_routes.items():
        referenced = {route.primary, *route.fallback, *route.upstream_models}
        missing = sorted(referenced - set(cfg.gateways))
        if missing:
            raise ValueError(f"Model route {model} references unknown gateways: {missing}")


def _validate_worker_profiles(cfg: Config) -> None:
    valid_kinds = {"plan", "explore", "execute", "review"}
    for key, profile in cfg.worker_profiles.items():
        if key != profile.name or not _PROFILE_NAME.fullmatch(profile.name):
            raise ValueError(f"Invalid worker profile name: {profile.name!r}")
        if not profile.description.strip():
            raise ValueError(f"Worker profile {profile.name!r} requires a description")
        if profile.reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(f"Unsupported reasoning effort for worker profile {profile.name!r}")
        if not profile.allowed_kinds or set(profile.allowed_kinds) - valid_kinds:
            raise ValueError(f"Worker profile {profile.name!r} has unsupported allowed_kinds")
        if profile.gateway:
            cfg.gateway_config(profile.gateway)


def _validate_cache_lab(cfg: Config) -> None:
    if not isinstance(cfg.cache_affinity_enabled, bool):
        raise ValueError("cache_affinity_enabled must be a boolean")
    if not isinstance(cfg.cache_affinity_window_seconds, int) or cfg.cache_affinity_window_seconds < 0:
        raise ValueError("cache_affinity_window_seconds must be a non-negative integer")
    if (
        not isinstance(cfg.cache_warm_window_seconds, int)
        or cfg.cache_warm_window_seconds <= 0
        or cfg.cache_warm_window_seconds > CACHE_WINDOW_MAX_SECONDS
    ):
        raise ValueError(
            f"cache_warm_window_seconds must be between 1 and {CACHE_WINDOW_MAX_SECONDS}"
        )
    if isinstance(cfg.cache_target_hit_rate, bool) or not isinstance(cfg.cache_target_hit_rate, (int, float)):
        raise ValueError("cache_target_hit_rate must be a number between 0 and 1")
    if not 0 <= float(cfg.cache_target_hit_rate) <= 1:
        raise ValueError("cache_target_hit_rate must be between 0 and 1")
    if not isinstance(cfg.cache_min_warm_samples, int) or cfg.cache_min_warm_samples < 1:
        raise ValueError("cache_min_warm_samples must be a positive integer")
    for field in ("cache_config_scope", "cache_tool_contract"):
        value = getattr(cfg, field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")


def write_default_config(cfg: Config, overwrite: bool = False) -> Path:
    cfg.ensure_dirs()
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
    gateways = dict(cfg.gateways)
    if not gateways:
        gateways = {
            "opencodex": GatewayConfig(
                "opencodex",
                cfg.codex_base_url or "http://127.0.0.1:10100/v1",
                "native",
                model_catalog=cfg.codex_model_catalog,
            ),
            "cliproxyapi": GatewayConfig(
                "cliproxyapi",
                "http://127.0.0.1:8317/v1",
                "translated",
                api_key_env="CLIPROXYAPI_CLIENT_KEY",
            ),
        }
    default_gateway = cfg.default_gateway if cfg.default_gateway in gateways else "opencodex"

    def quote(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    gateway_blocks: list[str] = []
    for name, gateway in gateways.items():
        lines = [f'[gateways."{quote(name)}"]']
        if gateway.base_url:
            lines.append(f'base_url = "{quote(gateway.base_url)}"')
        lines.append(f'response_mode = "{gateway.response_mode}"')
        if gateway.model_catalog:
            lines.append(f'model_catalog = "{quote(str(Path(gateway.model_catalog).expanduser().resolve()))}"')
        if gateway.api_key_env:
            lines.append(f'api_key_env = "{quote(gateway.api_key_env)}"')
        lines.append(f'enabled = {"true" if gateway.enabled else "false"}')
        gateway_blocks.append("\n".join(lines))

    routes = dict(cfg.model_routes)
    if not routes and {"opencodex", "cliproxyapi"}.issubset(gateways):
        routes["deepseek/deepseek-v4-flash"] = ModelRoute(
            primary="opencodex",
            fallback=("cliproxyapi",),
            upstream_models={
                "opencodex": "deepseek/deepseek-v4-flash",
                "cliproxyapi": "deepseek-v4-flash",
            },
        )
    route_blocks: list[str] = []
    for model, route in routes.items():
        fallbacks = ", ".join(f'"{quote(item)}"' for item in route.fallback)
        lines = [
            f'[model_routes."{quote(model)}"]',
            f'primary = "{quote(route.primary)}"',
            f'fallback = [{fallbacks}]',
        ]
        if route.upstream_models:
            lines.append(f'\n[model_routes."{quote(model)}".upstream_models]')
            lines.extend(f'"{quote(name)}" = "{quote(value)}"' for name, value in route.upstream_models.items())
        route_blocks.append("\n".join(lines))
    profile_blocks: list[str] = []
    for name, profile in cfg.worker_profiles.items():
        lines = [f'[worker_profiles."{quote(name)}"]']
        lines.append(f'description = "{quote(profile.description)}"')
        lines.append(f'model = "{quote(profile.model)}"')
        lines.append(f'reasoning_effort = "{profile.reasoning_effort}"')
        if profile.gateway:
            lines.append(f'gateway = "{quote(profile.gateway)}"')
        kinds = ", ".join(f'"{quote(kind)}"' for kind in profile.allowed_kinds)
        lines.append(f"allowed_kinds = [{kinds}]")
        profile_blocks.append("\n".join(lines))
    text = f'''# LightWorker local configuration
[runner]
max_concurrency = {cfg.max_concurrency}
max_tasks_per_plan = {cfg.max_tasks_per_plan}
max_delegation_depth = {cfg.max_delegation_depth}
max_replans = {cfg.max_replans}
root_max_concurrency = {cfg.root_max_concurrency}
root_max_attempts = {cfg.root_max_attempts}
root_max_retries = {cfg.root_max_retries}
root_max_escalations = {cfg.root_max_escalations}
default_timeout_seconds = {cfg.default_timeout_seconds}
poll_interval_seconds = {cfg.poll_interval_seconds}
cache_affinity_enabled = {"true" if cfg.cache_affinity_enabled else "false"}
cache_affinity_window_seconds = {cfg.cache_affinity_window_seconds}
cache_warm_window_seconds = {cfg.cache_warm_window_seconds}
cache_target_hit_rate = {cfg.cache_target_hit_rate}
cache_min_warm_samples = {cfg.cache_min_warm_samples}
cache_config_scope = "{quote(cfg.cache_config_scope)}"
cache_tool_contract = "{quote(cfg.cache_tool_contract)}"
allow_dirty_worktree_source = false
retain_redacted_raw_results = {"true" if cfg.retain_redacted_raw_results else "false"}
codex_command = "codex"
codex_ignore_user_config = {isolated}
default_gateway = "{default_gateway}"
{gateway_lines.rstrip()}

{chr(10).join(gateway_blocks)}

{chr(10).join(route_blocks)}

[models]
planner = "{cfg.model_defaults['planner']}"
explore = "{cfg.model_defaults['explore']}"
execute = "{cfg.model_defaults['execute']}"
review = "{cfg.model_defaults['review']}"
fast = "{cfg.model_defaults['fast']}"
reasoning = "{cfg.model_defaults['reasoning']}"

{chr(10).join(profile_blocks)}

[policy]
allowed_models = [
  {allowed}
]
'''
    cfg.config_path.write_text(text, encoding="utf-8")
    return cfg.config_path
