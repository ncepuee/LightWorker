
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import Config
from .models import KNOWN_KINDS, READ_ONLY_KINDS, TaskSpec


class PolicyError(ValueError):
    pass


_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def validate_task(spec: TaskSpec, cfg: Config) -> TaskSpec:
    spec.objective = spec.objective.strip()
    if not spec.objective:
        raise PolicyError("Task objective cannot be empty")
    if spec.kind not in KNOWN_KINDS:
        raise PolicyError(f"Unsupported task kind: {spec.kind}")
    if spec.model not in cfg.allowed_models:
        raise PolicyError(f"Model is not in the allowlist: {spec.model}")
    if spec.gateway:
        try:
            gateway = cfg.gateway_config(spec.gateway)
        except ValueError as exc:
            raise PolicyError(str(exc)) from exc
        if spec.response_mode != gateway.response_mode:
            raise PolicyError("Task response_mode does not match the selected gateway")
        if not spec.upstream_model or not spec.cache_cohort:
            raise PolicyError("Task gateway route is incomplete")
    if spec.reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise PolicyError(f"Unsupported reasoning effort: {spec.reasoning_effort}")
    if spec.mode not in {"plan_only", "auto_readonly", "auto_execute"}:
        raise PolicyError(f"Unsupported execution mode: {spec.mode}")
    workspace = Path(spec.workspace).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise PolicyError(f"Workspace does not exist or is not a directory: {workspace}")
    spec.workspace = str(workspace)
    if spec.kind in READ_ONLY_KINDS:
        spec.sandbox = "read-only"
    elif spec.kind == "execute":
        spec.sandbox = "workspace-write"
    if spec.sandbox not in {"read-only", "workspace-write"}:
        raise PolicyError("LightWorker never permits danger-full-access")
    if not 10 <= int(spec.timeout_seconds) <= 86_400:
        raise PolicyError("timeout_seconds must be between 10 and 86400")
    if spec.name and not _SAFE_NAME.fullmatch(spec.name):
        raise PolicyError(f"Invalid task name: {spec.name!r}")
    for path in spec.allowed_paths:
        candidate = (workspace / path).resolve()
        if candidate != workspace and workspace not in candidate.parents:
            raise PolicyError(f"allowed_paths escapes workspace: {path}")
    return spec


def validate_plan(plan: dict[str, Any], cfg: Config) -> list[dict[str, Any]]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise PolicyError("Planner result must contain a non-empty tasks array")
    if len(tasks) > cfg.max_tasks_per_plan:
        raise PolicyError(
            f"Planner produced {len(tasks)} tasks; limit is {cfg.max_tasks_per_plan}"
        )
    names: set[str] = set()
    for item in tasks:
        if not isinstance(item, dict):
            raise PolicyError("Every planned task must be an object")
        name = str(item.get("id", ""))
        if not _SAFE_NAME.fullmatch(name):
            raise PolicyError(f"Invalid planned task id: {name!r}")
        if name in names:
            raise PolicyError(f"Duplicate planned task id: {name}")
        names.add(name)
    graph: dict[str, list[str]] = {}
    for item in tasks:
        name = str(item["id"])
        deps = [str(value) for value in item.get("dependencies", [])]
        missing = [dep for dep in deps if dep not in names]
        if missing:
            raise PolicyError(f"Task {name} has unknown dependencies: {missing}")
        if name in deps:
            raise PolicyError(f"Task {name} depends on itself")
        graph[name] = deps
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise PolicyError(f"Task plan contains a dependency cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for name in graph:
        visit(name)
    return tasks


def topological_order(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {str(item["id"]): item for item in tasks}
    emitted: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while len(ordered) < len(tasks):
        ready = [
            item
            for name, item in by_name.items()
            if name not in emitted
            and all(str(dep) in emitted for dep in item.get("dependencies", []))
        ]
        if not ready:
            raise PolicyError("No schedulable task remains; dependency cycle suspected")
        ready.sort(key=lambda item: str(item["id"]))
        for item in ready:
            emitted.add(str(item["id"]))
            ordered.append(item)
    return ordered
