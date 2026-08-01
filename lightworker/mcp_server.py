from __future__ import annotations

import json
import sys
from typing import Any, Callable

from . import __version__
from .config import Config, load_config
from .policy import PolicyError
from .scheduler import Scheduler
from .service import LightWorkerService
from .store import TaskStore


TOOLS: list[dict[str, Any]] = [
    {
        "name": "orchestrate",
        "description": "Queue a bounded Lead Codex planning run. It creates a dependency-aware task graph and automatically dispatches allowed child tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "workspace": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["plan_only", "auto_readonly", "auto_execute"],
                    "default": "auto_readonly",
                },
                "model": {"type": "string"},
                "max_tasks": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "required": ["objective", "workspace"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "delegate_task",
        "description": "Queue one bounded worker task. Explore/review are read-only; execute uses an isolated git worktree and may require approval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "workspace": {"type": "string"},
                "kind": {"type": "string", "enum": ["explore", "execute", "review"]},
                "model": {"type": "string"},
                "reasoning_effort": {"type": "string", "enum": ["low", "medium", "high", "xhigh"]},
                "mode": {"type": "string", "enum": ["plan_only", "auto_readonly", "auto_execute"]},
                "timeout_seconds": {"type": "integer", "minimum": 10, "maximum": 86400},
                "allowed_paths": {"type": "array", "items": {"type": "string"}},
                "prohibited_actions": {"type": "array", "items": {"type": "string"}},
                "success_criteria": {"type": "array", "items": {"type": "string"}},
                "dependencies": {"type": "array", "items": {"type": "string"}},
                "name": {"type": "string"},
                "parent_id": {"type": "string"},
                "root_id": {"type": "string"},
            },
            "required": ["objective", "workspace"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "delegate_batch",
        "description": "Queue up to the configured limit of already-decomposed worker tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {"tasks": {"type": "array", "items": {"type": "object"}, "minItems": 1}},
            "required": ["tasks"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_task",
        "description": "Get one task, its dependencies, and structured result when available.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_task_tree",
        "description": "List every task belonging to an orchestration root.",
        "inputSchema": {
            "type": "object",
            "properties": {"root_id": {"type": "string"}},
            "required": ["root_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "list_tasks",
        "description": "List recent tasks, optionally filtered by status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "wait_tasks",
        "description": "Wait up to 55 seconds for tasks to reach a terminal or approval state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 55},
            },
            "required": ["task_ids"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_events",
        "description": "Read append-only task events after an event cursor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "after_id": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "approve_task",
        "description": "Release one task that is awaiting approval into the execution queue.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "cancel_task",
        "description": "Cancel a queued or active task and terminate its worker process tree.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    },
    {
        "name": "doctor",
        "description": "Check local Codex, proxy ports, state paths, model allowlist, and concurrency.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
]


class MCPServer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.store = TaskStore(cfg.db_path)
        self.scheduler = Scheduler(cfg, self.store)
        self.service = LightWorkerService(cfg, self.store, self.scheduler)
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "orchestrate": lambda a: self.service.orchestrate(**a),
            "delegate_task": self.service.delegate_task,
            "delegate_batch": lambda a: self.service.delegate_batch(a["tasks"]),
            "get_task": lambda a: self.service.task(a["task_id"]),
            "get_task_tree": lambda a: self.service.task_tree(a["root_id"]),
            "list_tasks": lambda a: self.service.list_tasks(a.get("status"), int(a.get("limit", 100))),
            "wait_tasks": lambda a: self.service.wait_tasks(a["task_ids"], float(a.get("timeout_seconds", 30))),
            "get_events": lambda a: self.service.events(a["task_id"], int(a.get("after_id", 0)), int(a.get("limit", 200))),
            "approve_task": lambda a: self.service.approve(a["task_id"]),
            "cancel_task": lambda a: self.service.cancel(a["task_id"]),
            "doctor": lambda a: self.service.doctor(),
        }

    @staticmethod
    def _write(message: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def _result(self, request_id: Any, result: Any) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _error(self, request_id: Any, code: int, message: str) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def run(self) -> None:
        # If the Web console already owns the scheduler lock, MCP stays passive:
        # tool calls still enqueue/read/cancel through the shared SQLite database.
        self.scheduler.start_background(reconcile=True, allow_passive=True)
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                    self._handle(request)
                except json.JSONDecodeError as exc:
                    self._error(None, -32700, f"Parse error: {exc}")
        finally:
            # Keep the global scheduler lock until active workers have exited;
            # releasing it early would let another process reconcile live tasks.
            self.scheduler.stop(wait=True)

    def _handle(self, request: dict[str, Any]) -> None:
        request_id = request.get("id")
        method = request.get("method")
        if method == "initialize":
            params = request.get("params") or {}
            self._result(
                request_id,
                {
                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "lightworker", "version": __version__},
                    "instructions": (
                        "Use orchestrate for a complete goal and delegate_batch for an existing plan. "
                        "Default to auto_readonly. Do not approve execute tasks or expand workspace scope "
                        "without the user's authorization. Max concurrency and model routing are enforced locally."
                    ),
                },
            )
            return
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return
        if method == "ping":
            self._result(request_id, {})
            return
        if method == "tools/list":
            self._result(request_id, {"tools": TOOLS})
            return
        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            handler = self.handlers.get(str(name))
            if not handler:
                self._error(request_id, -32601, f"Unknown tool: {name}")
                return
            try:
                data = handler(arguments)
                self._result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                        "structuredContent": data,
                        "isError": False,
                    },
                )
            except (KeyError, TypeError, ValueError, PolicyError) as exc:
                data = {"error": str(exc)}
                self._result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                        "structuredContent": data,
                        "isError": True,
                    },
                )
            return
        if request_id is not None:
            self._error(request_id, -32601, f"Method not found: {method}")


def run_mcp(home: str | None = None, config_path: str | None = None) -> None:
    MCPServer(load_config(home, config_path)).run()
