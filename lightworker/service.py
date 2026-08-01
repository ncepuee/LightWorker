from __future__ import annotations

import json
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Config, resolve_executable
from .models import TaskSpec, public_task
from .policy import PolicyError, topological_order, validate_plan, validate_task
from .scheduler import Scheduler
from .store import TaskStore


class LightWorkerService:
    def __init__(self, cfg: Config, store: TaskStore, scheduler: Scheduler):
        self.cfg = cfg
        self.store = store
        self.scheduler = scheduler

    def orchestrate(
        self,
        objective: str,
        workspace: str,
        mode: str = "auto_readonly",
        model: str | None = None,
        max_tasks: int | None = None,
    ) -> dict[str, Any]:
        limit = min(max_tasks or self.cfg.max_tasks_per_plan, self.cfg.max_tasks_per_plan)
        routing = {
            "planner": self.cfg.model_defaults["planner"],
            "low_reasoning": self.cfg.model_defaults["fast"],
            "reasoning": self.cfg.model_defaults["reasoning"],
            "rule": "Use low_reasoning only for mechanical, low-judgment work; use reasoning for design, planning, review, debugging, and complex coding.",
            "allowed_models": list(self.cfg.allowed_models),
        }
        spec = TaskSpec(
            kind="plan",
            objective=objective,
            workspace=workspace,
            model=model or self.cfg.model_defaults["planner"],
            reasoning_effort="high",
            sandbox="read-only",
            mode=mode,
            timeout_seconds=self.cfg.default_timeout_seconds,
            success_criteria=[
                "Produce a bounded acyclic task graph",
                "Give every task independently verifiable success criteria",
                "Parallelize only independent read-only work",
            ],
            prohibited_actions=["Do not modify files", "Do not spawn nested workers"],
            metadata={"max_tasks": limit, "routing_policy": routing},
        )
        validate_task(spec, self.cfg)
        task_id = self.store.create_task(spec)
        return {"root_task_id": task_id, "status": "queued", "mode": mode}

    def delegate_task(self, data: dict[str, Any]) -> dict[str, Any]:
        kind = str(data.get("kind", "explore"))
        mode = str(data.get("mode", "auto_readonly"))
        reasoning_effort = str(data.get("reasoning_effort", "medium"))
        model = self.cfg.route_model(reasoning_effort, data.get("model"))
        spec = TaskSpec(
            kind=kind,
            objective=str(data["objective"]),
            workspace=str(data["workspace"]),
            model=model,
            reasoning_effort=reasoning_effort,
            sandbox="workspace-write" if kind == "execute" else "read-only",
            mode=mode,
            timeout_seconds=int(data.get("timeout_seconds", self.cfg.default_timeout_seconds)),
            allowed_paths=[str(value) for value in data.get("allowed_paths", [])],
            prohibited_actions=[str(value) for value in data.get("prohibited_actions", [])],
            success_criteria=[str(value) for value in data.get("success_criteria", [])],
            dependencies=[str(value) for value in data.get("dependencies", [])],
            parent_id=data.get("parent_id"),
            root_id=data.get("root_id"),
            name=data.get("name"),
        )
        validate_task(spec, self.cfg)
        status = "queued"
        if mode == "plan_only" or (mode == "auto_readonly" and kind == "execute"):
            status = "awaiting_approval"
        task_id = self.store.create_task(spec, status=status)
        return {"task_id": task_id, "status": status}

    def delegate_batch(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        if not tasks:
            raise PolicyError("tasks cannot be empty")
        if len(tasks) > self.cfg.max_tasks_per_plan:
            raise PolicyError(f"Batch exceeds limit of {self.cfg.max_tasks_per_plan}")
        normalized: list[dict[str, Any]] = []
        for index, task in enumerate(tasks):
            item = dict(task)
            item.setdefault("id", item.get("name") or f"task-{index + 1}")
            item.setdefault("kind", "explore")
            item.setdefault("dependencies", [])
            normalized.append(item)
        validate_plan({"tasks": normalized}, self.cfg)
        ordered = topological_order(normalized)
        generated = {str(item["id"]): f"task-{uuid.uuid4().hex[:12]}" for item in ordered}
        root_id = str(ordered[0].get("root_id") or generated[str(ordered[0]["id"])])
        results: list[dict[str, Any]] = []
        for item in ordered:
            name = str(item["id"])
            payload = dict(item)
            payload["name"] = name
            payload["root_id"] = str(item.get("root_id") or root_id)
            payload["dependencies"] = [generated[str(dep)] for dep in item.get("dependencies", [])]
            reasoning_effort = str(payload.get("reasoning_effort", "medium"))
            spec = TaskSpec(
                task_id=generated[name],
                root_id=payload["root_id"],
                parent_id=payload.get("parent_id"),
                name=name,
                kind=str(payload.get("kind", "explore")),
                objective=str(payload["objective"]),
                workspace=str(payload["workspace"]),
                model=self.cfg.route_model(reasoning_effort, payload.get("model")),
                reasoning_effort=reasoning_effort,
                sandbox="workspace-write" if payload.get("kind") == "execute" else "read-only",
                mode=str(payload.get("mode", "auto_readonly")),
                timeout_seconds=int(payload.get("timeout_seconds", self.cfg.default_timeout_seconds)),
                allowed_paths=[str(value) for value in payload.get("allowed_paths", [])],
                prohibited_actions=[str(value) for value in payload.get("prohibited_actions", [])],
                success_criteria=[str(value) for value in payload.get("success_criteria", [])],
                dependencies=payload["dependencies"],
            )
            validate_task(spec, self.cfg)
            status = "queued"
            if spec.mode == "plan_only" or (spec.mode == "auto_readonly" and spec.kind == "execute"):
                status = "awaiting_approval"
            task_id = self.store.create_task(spec, status=status)
            results.append({"task_id": task_id, "name": name, "status": status})
        return {"root_id": root_id, "tasks": results}

    def task(self, task_id: str) -> dict[str, Any]:
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError(task_id)
        result = public_task(row)
        result["dependencies"] = self.store.dependencies(task_id)
        if row.get("result_json"):
            result["result"] = json.loads(row["result_json"])
        return result

    def task_tree(self, root_id: str) -> dict[str, Any]:
        return {"root_id": root_id, "tasks": [public_task(row) for row in self.store.list_tasks(root_id=root_id)]}

    def list_tasks(self, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        return {"tasks": [public_task(row) for row in self.store.list_tasks(status=status, limit=limit)]}

    def wait_tasks(self, task_ids: list[str], timeout_seconds: float = 30) -> dict[str, Any]:
        deadline = time.monotonic() + max(0, min(timeout_seconds, 55))
        while True:
            tasks = [self.task(task_id) for task_id in task_ids]
            if all(task["status"] in {"completed", "failed", "cancelled", "blocked", "awaiting_approval", "orphaned"} for task in tasks):
                return {"tasks": tasks, "timed_out": False}
            if time.monotonic() >= deadline:
                return {"tasks": tasks, "timed_out": True}
            time.sleep(0.25)

    def events(self, task_id: str, after_id: int = 0, limit: int = 200) -> dict[str, Any]:
        if not self.store.get_task(task_id):
            raise KeyError(task_id)
        return {"task_id": task_id, "events": self.store.events(task_id, after_id, limit)}

    def approve(self, task_id: str) -> dict[str, Any]:
        if not self.store.approve(task_id):
            raise PolicyError("Task is not awaiting approval")
        return {"task_id": task_id, "status": "queued"}

    def cancel(self, task_id: str) -> dict[str, Any]:
        if not self.scheduler.cancel(task_id):
            raise PolicyError("Task is already terminal or does not exist")
        return {"task_id": task_id, "status": "cancelled"}

    def doctor(self) -> dict[str, Any]:
        codex_path = resolve_executable(self.cfg.codex_command)
        version = None
        if codex_path:
            prefix = [codex_path]
            path = Path(codex_path)
            if path.suffix.lower() == ".cmd":
                script = path.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
                node = path.parent / "node.exe"
                node_command = str(node) if node.exists() else resolve_executable("node")
                if script.exists() and node_command:
                    prefix = [node_command, str(script)]
            result = subprocess.run(
                [*prefix, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            version = (result.stdout or result.stderr).strip().splitlines()[0]

        def port_open(port: int) -> bool:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    return True
            except OSError:
                return False

        return {
            "home": str(self.cfg.home),
            "database": str(self.cfg.db_path),
            "codex_path": codex_path,
            "codex_version": version,
            "cliproxyapi_8317": port_open(8317),
            "opencodex_proxy_10100": port_open(10100),
            "allowed_models": list(self.cfg.allowed_models),
            "max_concurrency": self.cfg.max_concurrency,
            "codex_ignore_user_config": self.cfg.codex_ignore_user_config,
            "codex_base_url": self.cfg.codex_base_url,
            "codex_model_catalog": self.cfg.codex_model_catalog,
            "scheduler_role": "active" if self.scheduler.owns_instance_lock else "standby",
            "scheduler_background_alive": self.scheduler.is_background_alive,
        }
