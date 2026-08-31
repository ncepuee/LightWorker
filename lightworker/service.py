from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .approval import stamp_approval, verify_approval
from .cache import configure_task_cache
from .config import Config, resolve_executable
from .models import KNOWN_HARNESSES, TaskSpec, public_task
from .policy import PolicyError, topological_order, validate_plan, validate_task
from .scheduler import Scheduler
from .store import TaskStore
from .worker import ZCodeWorker


class LightWorkerService:
    def __init__(self, cfg: Config, store: TaskStore, scheduler: Scheduler):
        self.cfg = cfg
        self.store = store
        self.scheduler = scheduler

    @staticmethod
    def _zcode_provider_status() -> dict[str, Any] | None:
        """Provider/plan connection facts from the ZCode CLI config.

        Reports names, endpoints, and model selections only. Key material is
        never read into the result — a boolean says whether one is configured.
        """
        config_path = os.environ.get("ZCODE_CONFIG_PATH")
        path = Path(config_path).expanduser() if config_path else Path.home() / ".zcode" / "cli" / "config.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        model = data.get("model") if isinstance(data.get("model"), dict) else {}
        providers = data.get("provider") if isinstance(data.get("provider"), dict) else {}
        provider_id = str(model.get("main", "")).split("/", 1)[0] if model.get("main") else None
        entry = providers.get(provider_id) if provider_id and isinstance(providers.get(provider_id), dict) else None
        status: dict[str, Any] = {
            "config_path": str(path),
            "main_model": model.get("main"),
            "lite_model": model.get("lite"),
        }
        if entry is not None:
            options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
            status["provider"] = {
                "id": provider_id,
                "name": entry.get("name"),
                "kind": entry.get("kind"),
                "base_url": options.get("baseURL"),
                "api_key_configured": bool(options.get("apiKey")),
                "models": sorted(entry.get("models", {}) or {}),
            }
        else:
            status["provider"] = None
        return status


    def _root_budget_limits(self, requested: dict[str, Any] | None = None) -> dict[str, int]:
        if requested is not None and not isinstance(requested, dict):
            raise PolicyError("budget must be an object")
        requested = requested or {}
        try:
            limits = {
                "max_concurrency": min(int(requested.get("max_concurrency", self.cfg.root_max_concurrency)), self.cfg.root_max_concurrency, self.cfg.max_concurrency),
                "max_attempts": min(int(requested.get("max_attempts", self.cfg.root_max_attempts)), self.cfg.root_max_attempts),
                "max_retries": min(int(requested.get("max_retries", self.cfg.root_max_retries)), self.cfg.root_max_retries),
                "max_escalations": min(int(requested.get("max_escalations", self.cfg.root_max_escalations)), self.cfg.root_max_escalations),
            }
        except (TypeError, ValueError) as exc:
            raise PolicyError("budget values must be integers") from exc
        if any(value < 0 for value in limits.values()) or limits["max_concurrency"] < 1 or limits["max_attempts"] < 1:
            raise PolicyError("budget limits must be non-negative and concurrency/attempts must be at least 1")
        return limits

    def _record_route(self, task_id: str, spec: TaskSpec) -> None:
        self.store.add_event(task_id, "worker.route_requested", {
            "profile": spec.profile,
            "model": spec.requested_model,
            "gateway": spec.requested_gateway,
            "reasoning_effort": spec.requested_reasoning_effort,
            "execution_channel": spec.execution_channel,
            "required_capabilities": spec.required_capabilities,
        })

    def _record_acceptance(self, task_id: str, spec: TaskSpec, status: str) -> None:
        if status == "awaiting_approval":
            self.store.add_event(task_id, "approval.requested", {
                "approval_id": spec.approval_id,
                "scope_digest": spec.approval_scope_digest,
                "scope_version": spec.approval_scope.get("version"),
            })
            return
        self.store.add_event(task_id, "worker.dispatch.accepted", {
            "status": status,
            "execution_channel": spec.execution_channel,
            "gateway": spec.gateway,
        })
        self.store.add_event(task_id, "worker.route_resolved", {
            "profile": spec.profile,
            "model": spec.model,
            "gateway": spec.gateway,
            "upstream_model": spec.upstream_model,
            "reasoning_effort": spec.reasoning_effort,
            "response_mode": spec.response_mode,
            "provider": spec.provider,
            "billing_class": spec.billing_class,
            "execution_channel": spec.execution_channel,
            "required_capabilities": spec.required_capabilities,
            "route_capabilities": spec.route_capabilities,
            "catalog_revision": spec.catalog_revision,
            "verification": "configured",
            "cache_cohort": spec.cache_cohort,
            "context_pack_hash": spec.context_pack_hash,
        })

    def _configure_task_cache(self, spec: TaskSpec, context_pack: object = ...) -> None:
        try:
            configure_task_cache(self.cfg, spec, context_pack)
        except ValueError as exc:
            raise PolicyError(str(exc)) from exc

    def _validated_parent_root(self, parent_id: str | None, requested_root: str | None) -> str | None:
        if not parent_id:
            return requested_root
        parent = self.store.get_task(parent_id)
        if not parent:
            raise PolicyError(f"Parent task does not exist: {parent_id}")
        depth = 1
        cursor = parent
        seen = {parent_id}
        while cursor.get("parent_id"):
            ancestor_id = str(cursor["parent_id"])
            if ancestor_id in seen:
                raise PolicyError("Parent task chain contains a cycle")
            seen.add(ancestor_id)
            cursor = self.store.get_task(ancestor_id)
            if not cursor:
                raise PolicyError(f"Parent task chain is incomplete at: {ancestor_id}")
            depth += 1
        if depth > self.cfg.max_delegation_depth:
            raise PolicyError(f"Delegation depth exceeds limit of {self.cfg.max_delegation_depth}")
        parent_root = str(parent["root_id"] or parent_id)
        if requested_root and str(requested_root) != parent_root:
            raise PolicyError("Child root_id must match its parent root")
        return parent_root

    def orchestrate(
        self,
        objective: str,
        workspace: str,
        mode: str = "auto_readonly",
        model: str | None = None,
        max_tasks: int | None = None,
        gateway: str | None = None,
        profile: str | None = None,
        budget: dict[str, Any] | None = None,
        context_pack: object = None,
    ) -> dict[str, Any]:
        limit = min(max_tasks or self.cfg.max_tasks_per_plan, self.cfg.max_tasks_per_plan)
        routing = {
            "planner": self.cfg.model_defaults["planner"],
            "low_reasoning": self.cfg.model_defaults["fast"],
            "reasoning": self.cfg.model_defaults["reasoning"],
            "rule": "Use low_reasoning only for mechanical, low-judgment work; use reasoning for design, planning, review, debugging, and complex coding.",
            "allowed_models": list(self.cfg.allowed_models),
            "worker_profiles": {
                name: {
                    "description": value.description,
                    "model": value.model,
                    "reasoning_effort": value.reasoning_effort,
                    "allowed_kinds": list(value.allowed_kinds),
                }
                for name, value in self.cfg.worker_profiles.items()
                if name != "planner"
            },
        }
        requested_model = model
        selected = self.cfg.resolve_profile(
            profile,
            kind="plan",
            model=model or (None if profile else self.cfg.model_defaults["planner"]),
            gateway=gateway,
            reasoning_effort=None if profile else "high",
        )
        route = self.cfg.resolve_route(selected.reasoning_effort, selected.model, selected.gateway)
        spec = TaskSpec(
            kind="plan",
            objective=objective,
            workspace=workspace,
            model=route.model,
            profile=selected.profile,
            requested_model=requested_model,
            requested_gateway=gateway,
            requested_reasoning_effort=None,
            gateway=route.gateway,
            upstream_model=route.upstream_model,
            response_mode=route.response_mode,
            fallback_gateway=route.fallback_gateway,
            provider=route.provider,
            billing_class=route.billing_class,
            route_capabilities=list(route.capabilities),
            catalog_revision=route.catalog_revision,
            cache_cohort=route.cache_cohort,
            reasoning_effort=selected.reasoning_effort,
            sandbox="read-only",
            mode=mode,
            timeout_seconds=self.cfg.default_timeout_seconds,
            success_criteria=[
                "Produce a bounded acyclic task graph",
                "Give every task independently verifiable success criteria",
                "Parallelize only independent read-only work",
            ],
            prohibited_actions=["Do not modify files", "Do not spawn nested workers"],
            metadata={"max_tasks": limit, "routing_policy": routing, "profile_description": self.cfg.worker_profiles[selected.profile].description if selected.profile else ""},
        )
        self._configure_task_cache(spec, context_pack)
        validate_task(spec, self.cfg)
        task_id = self.store.create_task(spec, root_budget=self._root_budget_limits(budget))
        self._record_route(task_id, spec)
        self._record_acceptance(task_id, spec, "queued")
        return {"root_task_id": task_id, "status": "queued", "mode": mode, "profile": spec.profile}

    def delegate_task(self, data: dict[str, Any]) -> dict[str, Any]:
        kind = str(data.get("kind", "explore"))
        if kind == "plan":
            raise PolicyError("Plan tasks must be created through orchestrate")
        mode = str(data.get("mode", "auto_readonly"))
        harness = str(data.get("harness") or self.cfg.worker_harness or "codex")
        if harness not in KNOWN_HARNESSES:
            raise PolicyError(f"Unknown harness: {harness}")
        profile = str(data["profile"]) if data.get("profile") else None
        requested_effort = str(data["reasoning_effort"]) if data.get("reasoning_effort") else None
        execution_channel = str(data.get("execution_channel", "lightworker_worker"))
        if harness == "zcode" and execution_channel == "native_subagent":
            raise PolicyError("native_subagent channel requires the codex harness")
        requested_gateway = str(data["gateway"]) if data.get("gateway") else None
        if harness == "zcode" and requested_gateway:
            raise PolicyError("ZCode tasks manage their own provider; gateway routing does not apply")
        raw_capabilities = data.get("required_capabilities", [])
        if not isinstance(raw_capabilities, list):
            raise PolicyError("required_capabilities must be an array")
        required_capabilities = [str(value) for value in raw_capabilities]
        if execution_channel == "native_subagent" and "native_subagents" not in required_capabilities:
            required_capabilities.append("native_subagents")
        selected = self.cfg.resolve_profile(
            profile,
            kind=kind,
            model=str(data["model"]) if data.get("model") else None,
            gateway=requested_gateway,
            reasoning_effort=requested_effort,
        )
        reasoning_effort = selected.reasoning_effort
        try:
            if harness == "zcode":
                # ZCode signs in with its own provider and plan; never touch
                # gateway resolution or catalogs for it (they may be offline).
                route = self.cfg.resolve_zcode_route(required_capabilities=required_capabilities)
            else:
                route = self.cfg.resolve_route(
                    reasoning_effort,
                    selected.model,
                    selected.gateway,
                    required_capabilities=required_capabilities,
                )
        except ValueError as exc:
            raise PolicyError(str(exc)) from exc
        parent_id = str(data["parent_id"]) if data.get("parent_id") else None
        root_id = self._validated_parent_root(
            parent_id, str(data["root_id"]) if data.get("root_id") else None
        )
        dependencies = [str(value) for value in data.get("dependencies", [])]
        dependency_rows: list[dict[str, Any]] = []
        for dependency in dependencies:
            dependency_row = self.store.get_task(dependency)
            if not dependency_row:
                raise PolicyError(f"Dependency task does not exist: {dependency}")
            dependency_rows.append(dependency_row)
        if dependency_rows and not root_id:
            root_id = str(dependency_rows[0]["root_id"] or dependencies[0])
        if root_id and any(str(row["root_id"] or dependency) != root_id for row, dependency in zip(dependency_rows, dependencies, strict=True)):
            raise PolicyError("Dependencies must belong to the same root task")
        spec = TaskSpec(
            kind=kind,
            harness=harness,
            objective=str(data["objective"]),
            workspace=str(data["workspace"]),
            model=route.model,
            profile=selected.profile,
            requested_model=str(data["model"]) if data.get("model") else None,
            requested_gateway=requested_gateway,
            requested_reasoning_effort=requested_effort,
            gateway=route.gateway if harness != "zcode" else None,
            upstream_model=route.upstream_model,
            response_mode=route.response_mode,
            fallback_gateway=route.fallback_gateway,
            provider=route.provider,
            billing_class=route.billing_class,
            execution_channel=execution_channel,
            required_capabilities=list(route.required_capabilities),
            route_capabilities=list(route.capabilities),
            catalog_revision=route.catalog_revision,
            cache_cohort=route.cache_cohort,
            reasoning_effort=reasoning_effort,
            sandbox="workspace-write" if kind == "execute" else "read-only",
            mode=mode,
            timeout_seconds=int(data.get("timeout_seconds", self.cfg.default_timeout_seconds)),
            allowed_paths=[str(value) for value in data.get("allowed_paths", [])],
            prohibited_actions=[str(value) for value in data.get("prohibited_actions", [])],
            success_criteria=[str(value) for value in data.get("success_criteria", [])],
            dependencies=dependencies,
            parent_id=parent_id,
            root_id=root_id,
            name=data.get("name"),
            metadata={"profile_description": self.cfg.worker_profiles[selected.profile].description if selected.profile else ""},
        )
        self._configure_task_cache(spec, data.get("context_pack"))
        validate_task(spec, self.cfg)
        status = "queued"
        if mode == "plan_only" or (mode == "auto_readonly" and kind == "execute"):
            status = "awaiting_approval"
            stamp_approval(spec)
        task_id = self.store.create_task(
            spec, status=status, root_budget=self._root_budget_limits(data.get("budget"))
        )
        self._record_route(task_id, spec)
        self._record_acceptance(task_id, spec, status)
        return {
            "task_id": task_id,
            "status": status,
            "profile": spec.profile,
            "execution_channel": spec.execution_channel,
        }

    def delegate_batch(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        if not tasks:
            raise PolicyError("tasks cannot be empty")
        if len(tasks) > self.cfg.max_tasks_per_plan:
            raise PolicyError(f"Batch exceeds limit of {self.cfg.max_tasks_per_plan}")
        normalized: list[dict[str, Any]] = []
        for index, task in enumerate(tasks):
            item = dict(task)
            if item.get("parent_id"):
                raise PolicyError("Batch tasks cannot declare parent_id; use dependencies within one root")
            item.setdefault("id", item.get("name") or f"task-{index + 1}")
            item.setdefault("kind", "explore")
            item.setdefault("dependencies", [])
            normalized.append(item)
        validate_plan({"tasks": normalized}, self.cfg)
        ordered = topological_order(normalized)
        generated = {str(item["id"]): f"task-{uuid.uuid4().hex[:12]}" for item in ordered}
        root_id = str(ordered[0].get("root_id") or generated[str(ordered[0]["id"])])
        entries: list[tuple[TaskSpec, str, int]] = []
        for item in ordered:
            name = str(item["id"])
            payload = dict(item)
            payload["name"] = name
            payload["root_id"] = root_id
            payload["dependencies"] = [generated[str(dep)] for dep in item.get("dependencies", [])]
            try:
                profile = str(payload["profile"]) if payload.get("profile") else None
                requested_effort = str(payload["reasoning_effort"]) if payload.get("reasoning_effort") else None
                requested_gateway = str(payload["gateway"]) if payload.get("gateway") else None
                kind = str(payload.get("kind", "explore"))
                harness = str(payload.get("harness") or self.cfg.worker_harness or "codex")
                if harness not in KNOWN_HARNESSES:
                    raise PolicyError(f"Unknown harness: {harness}")
                execution_channel = str(payload.get("execution_channel", "lightworker_worker"))
                if harness == "zcode" and execution_channel == "native_subagent":
                    raise PolicyError("native_subagent channel requires the codex harness")
                if harness == "zcode" and requested_gateway:
                    raise PolicyError("ZCode tasks manage their own provider; gateway routing does not apply")
                selected = self.cfg.resolve_profile(
                    profile,
                    kind=kind,
                    model=str(payload["model"]) if payload.get("model") else None,
                    gateway=requested_gateway,
                    reasoning_effort=requested_effort,
                )
                reasoning_effort = selected.reasoning_effort
                raw_capabilities = payload.get("required_capabilities", [])
                if not isinstance(raw_capabilities, list):
                    raise PolicyError("required_capabilities must be an array")
                required_capabilities = [str(value) for value in raw_capabilities]
                if execution_channel == "native_subagent" and "native_subagents" not in required_capabilities:
                    required_capabilities.append("native_subagents")
                if harness == "zcode":
                    # ZCode signs in with its own provider and plan; never
                    # touch gateway resolution or catalogs for it.
                    route = self.cfg.resolve_zcode_route(required_capabilities=required_capabilities)
                else:
                    route = self.cfg.resolve_route(
                        reasoning_effort,
                        selected.model,
                        selected.gateway,
                        required_capabilities=required_capabilities,
                    )
                spec = TaskSpec(
                    task_id=generated[name], root_id=root_id, parent_id=None,
                    name=name, kind=kind, harness=harness,
                    objective=str(payload["objective"]), workspace=str(payload["workspace"]),
                    model=route.model, profile=selected.profile,
                    requested_model=str(payload["model"]) if payload.get("model") else None,
                    requested_gateway=requested_gateway, requested_reasoning_effort=requested_effort,
                    gateway=route.gateway if harness != "zcode" else None,
                    upstream_model=route.upstream_model,
                    response_mode=route.response_mode, fallback_gateway=route.fallback_gateway,
                    provider=route.provider, billing_class=route.billing_class,
                    execution_channel=execution_channel,
                    required_capabilities=list(route.required_capabilities),
                    route_capabilities=list(route.capabilities),
                    catalog_revision=route.catalog_revision,
                    cache_cohort=route.cache_cohort,
                    reasoning_effort=reasoning_effort,
                    sandbox="workspace-write" if kind == "execute" else "read-only",
                    mode=str(payload.get("mode", "auto_readonly")),
                    timeout_seconds=int(payload.get("timeout_seconds", self.cfg.default_timeout_seconds)),
                    allowed_paths=[str(value) for value in payload.get("allowed_paths", [])],
                    prohibited_actions=[str(value) for value in payload.get("prohibited_actions", [])],
                    success_criteria=[str(value) for value in payload.get("success_criteria", [])],
                    dependencies=payload["dependencies"],
                    metadata={"profile_description": self.cfg.worker_profiles[selected.profile].description if selected.profile else ""},
                )
                self._configure_task_cache(spec, payload.get("context_pack"))
                validate_task(spec, self.cfg)
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, PolicyError):
                    raise
                raise PolicyError(f"Invalid batch task {name!r}: {exc}") from exc
            status = "queued"
            if spec.mode == "plan_only" or (spec.mode == "auto_readonly" and spec.kind == "execute"):
                status = "awaiting_approval"
                stamp_approval(spec)
            entries.append((spec, status, 0))
        limits = self._root_budget_limits(ordered[0].get("budget"))
        task_ids = self.store.create_tasks(entries, root_budgets={root_id: limits})
        results: list[dict[str, Any]] = []
        for task_id, (spec, status, _) in zip(task_ids, entries, strict=True):
            self._record_route(task_id, spec)
            self._record_acceptance(task_id, spec, status)
            results.append({"task_id": task_id, "name": spec.name, "status": status, "profile": spec.profile})
        return {"root_id": root_id, "tasks": results}

    def task(self, task_id: str) -> dict[str, Any]:
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError(task_id)
        result = public_task(row)
        result["dependencies"] = self.store.dependencies(task_id)
        root_id = str(row["root_id"] or task_id)
        self.store.ensure_root_budget(root_id, **self._root_budget_limits())
        result["budget"] = self.store.root_budget(root_id)
        history = self.store.events(task_id, 0, 2000)
        observed = next(
            (event["payload"] for event in reversed(history) if event["event_type"] == "worker.route_observed"),
            None,
        )
        verification = "unverified"
        if observed:
            actual_model = observed.get("model")
            verification = "verified" if actual_model in {result.get("model"), result.get("upstream_model")} else "mismatch"
        result["route_audit"] = {
            "requested": {
                "profile": result.get("profile"),
                "model": result.get("requested_model"),
                "gateway": result.get("requested_gateway"),
                "reasoning_effort": result.get("requested_reasoning_effort"),
            },
            "resolved": {
                "model": result.get("model"),
                "upstream_model": result.get("upstream_model"),
                "gateway": result.get("gateway"),
                "reasoning_effort": result.get("reasoning_effort"),
                "response_mode": result.get("response_mode"),
                "provider": result.get("provider"),
                "billing_class": result.get("billing_class"),
                "execution_channel": result.get("execution_channel"),
                "required_capabilities": result.get("required_capabilities"),
                "route_capabilities": result.get("route_capabilities"),
                "catalog_revision": result.get("catalog_revision"),
            },
            "observed": observed,
            "verification": verification,
        }
        result["cache_audit"] = {
            "cohort": result.get("cache_cohort"),
            "context_pack": {
                "name": result.get("context_pack_name"),
                "version": result.get("context_pack_version"),
                "sha256": result.get("context_pack_hash"),
            },
            "latest_usage": self.store.cache_audit(task_id),
        }
        if row.get("result_json"):
            result["result"] = json.loads(row["result_json"])
            payload = result["result"]
            result["schema"] = {
                "status": payload.get("schema_status", "unknown"),
                "valid": payload.get("schema_valid"),
                "raw_result_path": payload.get("raw_result_path"),
            }
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

    def claim_native_dispatches(
        self, host_id: str, limit: int = 1, lease_seconds: int = 90
    ) -> dict[str, Any]:
        """Return durable tickets for this Codex session to spawn natively.

        This endpoint is intentionally a pull bridge: LightWorker cannot invoke
        the desktop session's spawn_agent tool itself.  The host owns the actual
        agent thread and immediately acknowledges it through native_started.
        """
        self.store.requeue_expired_native_dispatches()
        tickets = []
        for row in self.store.claim_native_dispatches(host_id, limit, lease_seconds):
            spec = self.store.get_spec(str(row["id"]))
            tickets.append({
                "task_id": str(row["id"]),
                "lease_id": str(row["native_lease_id"]),
                "lease_expires_at": row["native_lease_expires_at"],
                "task_name": spec.name or f"lightworker_{str(row['id'])[-8:]}",
                "objective": spec.objective,
                "workspace": spec.workspace,
                "kind": spec.kind,
                "model": spec.model,
                "reasoning_effort": spec.reasoning_effort,
                "sandbox": spec.sandbox,
                "allowed_paths": spec.allowed_paths,
                "prohibited_actions": spec.prohibited_actions,
                "success_criteria": spec.success_criteria,
                "result_contract": "Return a concise summary, files changed, verification performed, and blockers.",
            })
        return {"host_id": host_id, "tickets": tickets}

    def native_started(self, task_id: str, lease_id: str, thread_id: str) -> dict[str, Any]:
        if not self.store.native_started(task_id, lease_id, thread_id):
            raise PolicyError("Native dispatch lease is stale or task is not dispatching")
        return {"task_id": task_id, "status": "running", "thread_id": thread_id}

    def native_event(
        self, task_id: str, lease_id: str, event_type: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.store.native_event(task_id, lease_id, event_type, payload):
            raise PolicyError("Native dispatch lease is stale or task is not active")
        return {"task_id": task_id, "accepted": True}

    def native_completed(
        self, task_id: str, lease_id: str, status: str, result: dict[str, Any] | None = None, error: str | None = None
    ) -> dict[str, Any]:
        if not self.store.native_complete(task_id, lease_id, status, result=result, error=error):
            raise PolicyError("Native dispatch lease is stale or task is already terminal")
        return {"task_id": task_id, "status": status}

    def cache_metrics(
        self,
        model: str | None = "deepseek/deepseek-v4-flash",
        gateway: str | None = None,
        window_seconds: int | None = None,
    ) -> dict[str, Any]:
        metrics = self.store.cache_metrics(
            model=model,
            gateway=gateway,
            window_seconds=self.cfg.cache_warm_window_seconds if window_seconds is None else window_seconds,
        )
        # Certification is per strict upstream cache identity.  Aggregating
        # OpenCodex and CLIProxyAPI, or different profiles/context packs, would
        # make an attractive but false global "achieved" result.
        warm_cohorts = [item for item in metrics["cohorts"] if item["cohort_class"] == "warm"]
        assessed: list[dict[str, Any]] = []
        for item in warm_cohorts:
            candidate = dict(item)
            rate = candidate["verified_cache_hit_rate"]
            if candidate["samples"] < self.cfg.cache_min_warm_samples:
                candidate["target_status"] = "insufficient_samples"
            elif candidate["verified_samples"] < self.cfg.cache_min_warm_samples:
                candidate["target_status"] = "unverified_route"
            elif rate is not None and rate >= self.cfg.cache_target_hit_rate:
                candidate["target_status"] = "achieved"
            else:
                candidate["target_status"] = "below_target"
            candidate["remaining_samples"] = max(
                0, self.cfg.cache_min_warm_samples - candidate["verified_samples"]
            )
            assessed.append(candidate)
        achieved = [item for item in assessed if item["target_status"] == "achieved"]
        selected = max(
            achieved or assessed,
            key=lambda item: (item["verified_samples"], item["samples"], item["verified_cache_hit_rate"] or -1),
            default=None,
        )
        if selected is None:
            status = "insufficient_samples"
        else:
            status = selected["target_status"]
        metrics["target"] = {
            "hit_rate": self.cfg.cache_target_hit_rate,
            "min_warm_samples": self.cfg.cache_min_warm_samples,
            "status": status,
            "verified_warm_hit_rate": selected["verified_cache_hit_rate"] if selected else None,
            "remaining_samples": (
                selected["remaining_samples"] if selected else self.cfg.cache_min_warm_samples
            ),
            "cohort": ({key: selected[key] for key in (
                "cache_cohort", "cache_cohort_sha256", "gateway", "model",
            )} if selected else None),
            "cohorts": assessed,
        }
        return metrics

    def approve(
        self,
        task_id: str,
        approval_id: str | None = None,
        scope_digest: str | None = None,
    ) -> dict[str, Any]:
        row = self.store.get_task(task_id)
        if not row or row["status"] != "awaiting_approval":
            raise PolicyError("Task is not awaiting approval")
        spec = self.store.get_spec(task_id)
        try:
            verify_approval(spec, approval_id, scope_digest)
        except ValueError as exc:
            raise PolicyError(str(exc)) from exc
        if not self.store.approve(task_id):
            raise PolicyError("Task is not awaiting approval")
        self.store.add_event(task_id, "approval.granted", {
            "approval_id": spec.approval_id,
            "scope_digest": spec.approval_scope_digest,
            "actor": "local_user",
        })
        self.store.add_event(task_id, "worker.dispatch.accepted", {
            "status": "queued",
            "execution_channel": spec.execution_channel,
            "gateway": spec.gateway,
        })
        return {"task_id": task_id, "status": "queued", "approval_id": spec.approval_id}

    def cancel(self, task_id: str) -> dict[str, Any]:
        row = self.store.get_task(task_id)
        if not self.scheduler.cancel(task_id):
            raise PolicyError("Task is already terminal or does not exist")
        native_thread_id = row.get("native_thread_id") if row else None
        if native_thread_id:
            self.store.add_event(task_id, "native.interrupt_requested", {"thread_id": native_thread_id})
        return {
            "task_id": task_id,
            "status": "cancelled",
            "native_interrupt_required": bool(native_thread_id),
            "native_thread_id": native_thread_id,
        }

    def purge_history(self, include_cancelled: bool = True) -> dict[str, Any]:
        """Delete terminal tasks from the local database.

        Active work (queued/starting/running/awaiting_approval) is preserved.
        """
        statuses = {"completed", "failed", "blocked", "orphaned"}
        if include_cancelled:
            statuses.add("cancelled")
        deleted = self.store.purge_terminal_tasks(statuses)
        return {"deleted": deleted, "statuses": sorted(statuses)}

    def retry_fallback(self, task_id: str) -> dict[str, Any]:
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError(task_id)
        original = self.store.get_spec(task_id)
        if original.kind not in {"plan", "explore", "review"}:
            raise PolicyError("Fallback retry is limited to read-only tasks")
        if row["status"] not in {"failed", "blocked"}:
            raise PolicyError("Fallback retry requires a failed or blocked task")
        if not original.fallback_gateway:
            raise PolicyError("No configured fallback gateway is available")
        route = self.cfg.resolve_route(
            original.reasoning_effort,
            original.model,
            original.fallback_gateway,
            required_capabilities=original.required_capabilities,
        )
        root_id = original.root_id or task_id
        if not self.store.reserve_budget(root_id, "retry"):
            raise PolicyError("Root task retry budget exhausted")
        clone = TaskSpec(**original.to_dict())
        clone.task_id = None
        clone.root_id = root_id
        clone.parent_id = task_id
        clone.requested_gateway = original.fallback_gateway
        clone.gateway = route.gateway
        clone.upstream_model = route.upstream_model
        clone.response_mode = route.response_mode
        clone.fallback_gateway = route.fallback_gateway
        clone.provider = route.provider
        clone.billing_class = route.billing_class
        clone.route_capabilities = list(route.capabilities)
        clone.catalog_revision = route.catalog_revision
        clone.cache_cohort = route.cache_cohort
        clone.dependencies = []
        clone.metadata = {**clone.metadata, "retry_of": task_id}
        self._configure_task_cache(clone)
        validate_task(clone, self.cfg)
        new_id = self.store.create_task(clone)
        self._record_route(new_id, clone)
        self.store.add_event(task_id, "worker.gateway_fallback_requested", {"retry_task_id": new_id, "gateway": route.gateway})
        self.store.add_event(new_id, "worker.gateway_retried", {"retry_of": task_id, "gateway": route.gateway})
        return {"task_id": new_id, "status": "queued", "retry_of": task_id, "gateway": route.gateway}

    def escalate(self, task_id: str, profile: str | None = None) -> dict[str, Any]:
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError(task_id)
        original = self.store.get_spec(task_id)
        if original.kind not in {"explore", "review"}:
            raise PolicyError("Escalation is limited to read-only explore/review tasks")
        payload = json.loads(row["result_json"]) if row.get("result_json") else {}
        eligible = row["status"] in {"failed", "blocked"} or payload.get("schema_valid") is False
        if not eligible:
            raise PolicyError("Escalation requires a failed, blocked, or schema-invalid task")
        selected_profile = profile or "deep_worker"
        selected = self.cfg.resolve_profile(selected_profile, kind=original.kind)
        route = self.cfg.resolve_route(
            selected.reasoning_effort,
            selected.model,
            selected.gateway,
            required_capabilities=original.required_capabilities,
        )
        root_id = original.root_id or task_id
        if not self.store.reserve_budget(root_id, "escalation"):
            raise PolicyError("Root task escalation budget exhausted")
        clone = TaskSpec(**original.to_dict())
        clone.task_id = None
        clone.root_id = root_id
        clone.parent_id = task_id
        clone.profile = selected.profile
        clone.requested_model = None
        clone.requested_gateway = selected.gateway
        clone.requested_reasoning_effort = None
        clone.model = route.model
        clone.gateway = route.gateway
        clone.upstream_model = route.upstream_model
        clone.response_mode = route.response_mode
        clone.fallback_gateway = route.fallback_gateway
        clone.provider = route.provider
        clone.billing_class = route.billing_class
        clone.route_capabilities = list(route.capabilities)
        clone.catalog_revision = route.catalog_revision
        clone.cache_cohort = route.cache_cohort
        clone.reasoning_effort = selected.reasoning_effort
        clone.dependencies = []
        clone.metadata = {
            **clone.metadata,
            "escalation_of": task_id,
            "profile_description": self.cfg.worker_profiles[selected.profile].description if selected.profile else "",
        }
        self._configure_task_cache(clone)
        validate_task(clone, self.cfg)
        new_id = self.store.create_task(clone)
        self._record_route(new_id, clone)
        self.store.add_event(task_id, "worker.escalation_requested", {"task_id": new_id, "profile": selected.profile})
        self.store.add_event(new_id, "worker.escalation_created", {"from_task_id": task_id, "profile": selected.profile})
        return {"task_id": new_id, "status": "queued", "escalation_of": task_id, "profile": selected.profile}

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

        gateways = []
        configured = self.cfg.gateways or {
            "legacy": self.cfg.gateway_config("legacy")
        }
        for name, gateway in configured.items():
            tcp_reachable = False
            api_reachable = False
            if gateway.base_url:
                from urllib.parse import urlparse

                parsed = urlparse(gateway.base_url)
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                tcp_reachable = local and port_open(port)
                credential = os.environ.get(gateway.api_key_env) if gateway.api_key_env else None
                if tcp_reachable and (not gateway.api_key_env or credential):
                    headers = {"Accept": "application/json"}
                    if credential:
                        headers["Authorization"] = f"Bearer {credential}"
                    try:
                        opener = build_opener(ProxyHandler({}))
                        with opener.open(Request(f"{gateway.base_url.rstrip('/')}/models", headers=headers), timeout=0.8) as response:
                            api_reachable = 200 <= response.status < 300
                    except (HTTPError, URLError, OSError, ValueError):
                        api_reachable = False
            else:
                tcp_reachable = bool(codex_path)
                api_reachable = tcp_reachable
            gateways.append({
                "name": name,
                "enabled": gateway.enabled,
                "reachable": api_reachable,
                "tcp_reachable": tcp_reachable,
                "api_reachable": api_reachable,
                "response_mode": gateway.response_mode,
                "capabilities": list(self.cfg.gateway_capabilities(name)),
                "catalog": self.cfg.catalog_snapshot(name),
                "credential_configured": not gateway.api_key_env or bool(os.environ.get(gateway.api_key_env)),
                "default": name == self.cfg.default_gateway or (not self.cfg.gateways and name == "legacy"),
            })
        model_routes = []
        for model, route in sorted(self.cfg.model_routes.items()):
            candidates = (route.primary, *route.fallback)
            compatible = [
                name for name in candidates
                if name in configured
                and configured[name].enabled
                and set(route.required_capabilities).issubset(self.cfg.gateway_capabilities(name))
            ]
            model_routes.append({
                "model": model,
                "primary": route.primary,
                "fallback": list(route.fallback),
                "provider": route.provider or (model.split("/", 1)[0] if "/" in model else route.primary),
                "billing_class": route.billing_class,
                "upstream_models": dict(route.upstream_models),
                "required_capabilities": list(route.required_capabilities),
                "compatible_gateways": compatible,
                "routable": bool(compatible),
            })
        return {
            "home": str(self.cfg.home),
            "database": str(self.cfg.db_path),
            "codex_path": codex_path,
            "codex_version": version,
            "worker_harness": self.cfg.worker_harness,
            "zcode_path": resolve_executable(self.cfg.zcode_command) if not self.cfg.zcode_cli_path else str(Path(self.cfg.zcode_cli_path).expanduser()),
            "zcode_available": ZCodeWorker(self.cfg).available(),
            "zcode_provider": self._zcode_provider_status(),
            "cliproxyapi_8317": port_open(8317),
            "opencodex_proxy_10100": port_open(10100),
            "gateways": gateways,
            "default_gateway": self.cfg.default_gateway if self.cfg.gateways else "legacy",
            "allowed_models": list(self.cfg.allowed_models),
            "worker_profiles": [
                {
                    "name": profile.name,
                    "description": profile.description,
                    "model": profile.model,
                    "reasoning_effort": profile.reasoning_effort,
                    "gateway": profile.gateway,
                    "allowed_kinds": list(profile.allowed_kinds),
                }
                for profile in self.cfg.worker_profiles.values()
            ],
            "model_routes": model_routes,
            "max_concurrency": self.cfg.max_concurrency,
            "root_budget_defaults": {
                "max_concurrency": self.cfg.root_max_concurrency,
                "max_attempts": self.cfg.root_max_attempts,
                "max_retries": self.cfg.root_max_retries,
                "max_escalations": self.cfg.root_max_escalations,
            },
            "cache_lab": {
                "affinity_enabled": self.cfg.cache_affinity_enabled,
                "affinity_window_seconds": self.cfg.cache_affinity_window_seconds,
                "warm_window_seconds": self.cfg.cache_warm_window_seconds,
                "target_hit_rate": self.cfg.cache_target_hit_rate,
                "min_warm_samples": self.cfg.cache_min_warm_samples,
                "cohort_version": "cache_cohort.v2",
            },
            "codex_ignore_user_config": self.cfg.codex_ignore_user_config,
            "codex_base_url": self.cfg.codex_base_url,
            "codex_model_catalog": self.cfg.codex_model_catalog,
            "scheduler_role": "active" if self.scheduler.owns_instance_lock else "standby",
            "scheduler_background_alive": self.scheduler.is_background_alive,
        }
