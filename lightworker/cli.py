from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_OPENCODEX_CAPABILITIES,
    Config,
    GatewayConfig,
    load_config,
    write_default_config,
)
from .mcp_server import run_mcp
from .scheduler import Scheduler
from .service import LightWorkerService
from .store import TaskStore


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lightworker",
        description="Local-first task DAG runner for Codex and CLIProxyAPI models.",
    )
    parser.add_argument("--home", help="State directory (or set LIGHTWORKER_HOME)")
    parser.add_argument("--config", help="Explicit config.toml path")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create state directories and a default config")
    init.add_argument("--force", action="store_true", help="Overwrite an existing config")
    init.add_argument("--isolated-codex", action="store_true", help="Do not load user MCP/config in workers")
    init.add_argument("--codex-base-url", help="Gateway URL used with --isolated-codex")
    init.add_argument("--model-catalog", help="Codex model_catalog_json used with --isolated-codex")

    orchestrate = sub.add_parser("orchestrate", help="Queue a Lead Codex planning task")
    orchestrate.add_argument("objective")
    orchestrate.add_argument("--workspace", required=True)
    orchestrate.add_argument(
        "--mode", choices=["plan_only", "auto_readonly", "auto_execute"], default="auto_readonly"
    )
    orchestrate.add_argument("--model")
    orchestrate.add_argument("--profile", help="Configured worker profile")
    orchestrate.add_argument("--gateway", help="Configured gateway name")
    orchestrate.add_argument("--max-tasks", type=int)
    orchestrate.add_argument("--context-pack-file", help="UTF-8 file containing reviewed shared context (max 32KiB)")
    orchestrate.add_argument("--run", action="store_true", help="Run until no queued/active work remains")

    submit = sub.add_parser("submit", help="Queue a single worker task")
    submit.add_argument("objective")
    submit.add_argument("--workspace", required=True)
    submit.add_argument("--kind", choices=["explore", "execute", "review"], default="explore")
    submit.add_argument("--model")
    submit.add_argument("--profile", help="Configured worker profile")
    submit.add_argument("--gateway", help="Configured gateway name")
    submit.add_argument(
        "--harness",
        choices=["codex", "zcode"],
        help="Worker harness (defaults to [runner] worker_harness, currently codex)",
    )
    submit.add_argument(
        "--execution-channel",
        choices=["lightworker_worker", "native_subagent"],
        default="lightworker_worker",
    )
    submit.add_argument(
        "--require-capability",
        action="append",
        default=[],
        help="Repeatable gateway capability such as web_search",
    )
    submit.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    submit.add_argument(
        "--mode", choices=["plan_only", "auto_readonly", "auto_execute"], default="auto_readonly"
    )
    submit.add_argument("--timeout", type=int)
    submit.add_argument("--allowed-paths", help="Comma-separated paths relative to workspace")
    submit.add_argument("--success", action="append", default=[], help="Repeatable success criterion")
    submit.add_argument("--context-pack-file", help="UTF-8 file containing reviewed shared context (max 32KiB)")
    submit.add_argument("--run", action="store_true")

    run = sub.add_parser("run", help="Run queued tasks")
    run.add_argument("--timeout", type=float, help="Overall scheduler timeout")

    tasks = sub.add_parser("tasks", help="List recent tasks")
    tasks.add_argument("--status")
    tasks.add_argument("--limit", type=int, default=100)

    status = sub.add_parser("status", help="Show one task")
    status.add_argument("task_id")

    tree = sub.add_parser("tree", help="Show an orchestration task tree")
    tree.add_argument("root_id")

    events = sub.add_parser("events", help="Show task events")
    events.add_argument("task_id")
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--limit", type=int, default=200)

    cache_metrics = sub.add_parser("cache-metrics", help="Show cold/warm cache telemetry")
    cache_metrics.add_argument("--model", default="deepseek/deepseek-v4-flash")
    cache_metrics.add_argument("--gateway")
    cache_metrics.add_argument("--window-seconds", type=int)

    approve = sub.add_parser("approve", help="Release an awaiting-approval task")
    approve.add_argument("task_id")

    cancel = sub.add_parser("cancel", help="Cancel a task")
    cancel.add_argument("task_id")

    retry = sub.add_parser("retry-fallback", help="Clone a failed read-only task onto its fallback gateway")
    retry.add_argument("task_id")
    escalate = sub.add_parser("escalate", help="Clone an eligible read-only task onto a deeper worker profile")
    escalate.add_argument("task_id")
    escalate.add_argument("--profile")

    sub.add_parser("doctor", help="Check Codex, proxy ports, state and model policy")
    web = sub.add_parser("web", help="Run the loopback-only local management console")
    web.add_argument("--host", default="127.0.0.1", help="Loopback host (default: 127.0.0.1)")
    web.add_argument("--port", type=int, default=8766, help="Listening port (default: 8766)")
    web.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    sub.add_parser("mcp", help="Run the stdio MCP server and background scheduler")
    sub.add_parser("mcp-config", help="Print Codex config.toml snippet for this MCP server")
    release = sub.add_parser("release", help="Run the deterministic release SOP for this repository")
    release.add_argument("version", help="Version to release, e.g. 0.5.1 (v prefix optional)")
    release.add_argument("--pr", type=int, help="Squash-merge this PR first (must be OPEN and mergeable)")
    release.add_argument("--notes-file", help="Markdown file used as the GitHub Release body")
    release.add_argument("--workspace", default=".", help="Repository path (defaults to current directory)")
    return parser


def _service(cfg: Config) -> tuple[LightWorkerService, Scheduler]:
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    return LightWorkerService(cfg, store, scheduler), scheduler


def _context_pack_file(path: str | None) -> str | None:
    return Path(path).expanduser().read_text(encoding="utf-8") if path else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        run_mcp(args.home, args.config)
        return 0
    cfg = load_config(args.home, args.config)
    if args.command == "web":
        from .web_server import run_web

        run_web(cfg, host=args.host, port=args.port, open_browser=not args.no_open)
        return 0
    if args.command == "init":
        if args.isolated_codex:
            cfg.codex_ignore_user_config = True
            cfg.codex_base_url = args.codex_base_url
            cfg.codex_model_catalog = args.model_catalog
            if not cfg.codex_base_url or not cfg.codex_model_catalog:
                _json({"error": "--isolated-codex requires --codex-base-url and --model-catalog"})
                return 2
            cfg.default_gateway = "opencodex"
            cfg.gateways["opencodex"] = GatewayConfig(
                "opencodex",
                cfg.codex_base_url,
                "native",
                model_catalog=cfg.codex_model_catalog,
                capabilities=DEFAULT_OPENCODEX_CAPABILITIES,
            )
        path = write_default_config(cfg, overwrite=args.force)
        _json({"home": str(cfg.home), "config": str(path), "database": str(cfg.db_path)})
        return 0
    if args.command == "release":
        from .release import run_release

        return run_release(
            args.version,
            args.pr,
            Path(args.notes_file).expanduser() if args.notes_file else None,
            Path(args.workspace).expanduser().resolve(),
        )
    if args.command == "mcp-config":
        package_root = Path(__file__).resolve().parent.parent
        snippet = (
            "[mcp_servers.lightworker]\n"
            f'command = "{sys.executable.replace(chr(92), chr(92) * 2)}"\n'
            f'args = ["-m", "lightworker", "--home", "{str(cfg.home).replace(chr(92), chr(92) * 2)}", "mcp"]\n'
            f'cwd = "{str(package_root).replace(chr(92), chr(92) * 2)}"\n'
            "startup_timeout_sec = 15\n"
            "tool_timeout_sec = 60\n"
            'default_tools_approval_mode = "writes"\n'
        )
        print(snippet)
        return 0

    service, scheduler = _service(cfg)
    try:
        if args.command == "orchestrate":
            result = service.orchestrate(
                args.objective,
                args.workspace,
                mode=args.mode,
                model=args.model,
                max_tasks=args.max_tasks,
                gateway=args.gateway,
                profile=args.profile,
                context_pack=_context_pack_file(args.context_pack_file),
            )
            _json(result)
            if args.run:
                ok = scheduler.run_until_idle()
                _json(service.task_tree(result["root_task_id"]))
                return 0 if ok else 2
            return 0
        if args.command == "submit":
            result = service.delegate_task(
                {
                    "objective": args.objective,
                    "workspace": args.workspace,
                    "kind": args.kind,
                    "harness": args.harness,
                    "profile": args.profile,
                    "model": args.model,
                    "gateway": args.gateway,
                    "execution_channel": args.execution_channel,
                    "required_capabilities": args.require_capability,
                    "reasoning_effort": args.effort,
                    "mode": args.mode,
                    "timeout_seconds": args.timeout or cfg.default_timeout_seconds,
                    "allowed_paths": _csv(args.allowed_paths),
                    "success_criteria": args.success,
                    "context_pack": _context_pack_file(args.context_pack_file),
                }
            )
            _json(result)
            if args.run and result["status"] == "queued":
                ok = scheduler.run_until_idle()
                _json(service.task(result["task_id"]))
                return 0 if ok else 2
            return 0
        if args.command == "run":
            return 0 if scheduler.run_until_idle(timeout=args.timeout) else 2
        if args.command == "tasks":
            _json(service.list_tasks(args.status, args.limit))
            return 0
        if args.command == "status":
            _json(service.task(args.task_id))
            return 0
        if args.command == "tree":
            _json(service.task_tree(args.root_id))
            return 0
        if args.command == "events":
            _json(service.events(args.task_id, args.after, args.limit))
            return 0
        if args.command == "cache-metrics":
            _json(service.cache_metrics(args.model or None, args.gateway, args.window_seconds))
            return 0
        if args.command == "approve":
            task = service.task(args.task_id)
            _json(service.approve(
                args.task_id,
                task.get("approval_id"),
                task.get("approval_scope_digest"),
            ))
            return 0
        if args.command == "cancel":
            _json(service.cancel(args.task_id))
            return 0
        if args.command == "escalate":
            _json(service.escalate(args.task_id, args.profile))
            return 0
        if args.command == "retry-fallback":
            _json(service.retry_fallback(args.task_id))
            return 0
        if args.command == "doctor":
            _json(service.doctor())
            return 0
    except (KeyError, ValueError) as exc:
        _json({"error": str(exc)})
        return 2
    return 1
