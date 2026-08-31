from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .approval import stamp_approval
from .cache import configure_task_cache
from .config import Config
from .instance_lock import InstanceLock
from .models import RunResult, TaskSpec
from .policy import PolicyError, topological_order, validate_plan, validate_task
from .store import TaskStore
from .worker import CodexWorker, build_worker
from .worktree import WorktreeError, create_worktree


class Scheduler:
    def __init__(self, cfg: Config, store: TaskStore, worker: CodexWorker | None = None):
        self.cfg = cfg
        self.store = store
        # Injected worker (tests) takes precedence; otherwise each task picks
        # its harness at dispatch time via build_worker().
        self.worker = worker
        self._executor = ThreadPoolExecutor(
            max_workers=cfg.max_concurrency, thread_name_prefix="lightworker"
        )
        self._futures: dict[str, Future[None]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._instance_lock = InstanceLock(cfg.scheduler_lock_path)
        self._owns_instance_lock = False
        self._last_root_id: str | None = None
        self._last_cache_cohort: str | None = None
        self._last_cache_dispatch_at = 0.0
        self._cache_affinity_streak = 0

    def start_background(self, reconcile: bool = True, allow_passive: bool = False) -> bool:
        if self._thread and self._thread.is_alive():
            return self._owns_instance_lock
        if not self._instance_lock.acquire():
            if allow_passive:
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._wait_for_lock_then_run,
                    args=(reconcile,),
                    name="lightworker-scheduler-standby",
                    daemon=True,
                )
                self._thread.start()
                return False
            raise RuntimeError(
                "Another LightWorker scheduler is already active. Use the Web console or existing MCP process."
            )
        self._owns_instance_lock = True
        if reconcile:
            self.store.reconcile_after_restart()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="lightworker-scheduler", daemon=True)
        self._thread.start()
        return True

    @property
    def owns_instance_lock(self) -> bool:
        return self._owns_instance_lock

    @property
    def is_background_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _wait_for_lock_then_run(self, reconcile: bool) -> None:
        while not self._stop.is_set():
            if self._instance_lock.acquire():
                self._owns_instance_lock = True
                if reconcile:
                    self.store.reconcile_after_restart()
                self._loop()
                return
            self._stop.wait(max(0.25, self.cfg.poll_interval_seconds))

    def stop(self, wait: bool = True) -> None:
        self._stop.set()
        if wait and self._thread:
            self._thread.join(timeout=5)
        self._executor.shutdown(wait=wait, cancel_futures=False)
        if self._owns_instance_lock:
            self._instance_lock.release()
            self._owns_instance_lock = False

    def run_until_idle(self, timeout: float | None = None, reconcile: bool = True) -> bool:
        self.start_background(reconcile=reconcile)
        started = time.monotonic()
        while self.store.has_pending_work() or self._futures:
            if timeout is not None and time.monotonic() - started > timeout:
                return False
            time.sleep(0.1)
        self.stop(wait=True)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.store.block_failed_dependencies()
            self._collect_finished()
            with self._lock:
                available = self.cfg.max_concurrency - len(self._futures)
            if available > 0:
                # Inspect beyond the first root so a saturated orchestration cannot
                # starve unrelated work that still has root-level capacity.
                ready = self.store.ready_tasks(max(available * 4, 32))
                for row, affinity_selected in self._order_ready(ready):
                    with self._lock:
                        if len(self._futures) >= self.cfg.max_concurrency:
                            break
                    task_id = str(row["id"])
                    self.store.ensure_root_budget(
                        str(row["root_id"] or task_id),
                        max_concurrency=min(self.cfg.root_max_concurrency, self.cfg.max_concurrency),
                        max_attempts=self.cfg.root_max_attempts,
                        max_retries=self.cfg.root_max_retries,
                        max_escalations=self.cfg.root_max_escalations,
                    )
                    lease = self.store.claim_task(task_id)
                    if not lease:
                        continue
                    self._note_dispatch(row)
                    if affinity_selected:
                        self.store.add_event(task_id, "scheduler.cache_affinity_selected", {
                            "cache_cohort": self._row_cache_cohort(row),
                            "max_burst": 1,
                        })
                    future = self._executor.submit(self._run_task, task_id, lease)
                    with self._lock:
                        self._futures[task_id] = future
            self._stop.wait(self.cfg.poll_interval_seconds)
        self._collect_finished()

    @staticmethod
    def _row_cache_cohort(row: dict[str, Any]) -> str | None:
        try:
            value = json.loads(row.get("spec_json") or "{}").get("cache_cohort")
        except (TypeError, json.JSONDecodeError):
            return None
        return str(value) if value else None

    def _order_ready(self, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], bool]]:
        """Keep root rounds fair, then apply one bounded warm-cohort preference."""
        if not rows:
            return []
        rounds: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            rounds.setdefault(int(row.get("root_round") or 1), []).append(row)
        ordered: list[tuple[dict[str, Any], bool]] = []
        affinity_available = (
            self.cfg.cache_affinity_enabled
            and self._last_cache_cohort is not None
            and self._cache_affinity_streak < 1
            and time.monotonic() - self._last_cache_dispatch_at <= self.cfg.cache_affinity_window_seconds
        )
        for round_number in sorted(rounds):
            candidates = rounds[round_number]
            roots = [str(row["root_id"] or row["id"]) for row in candidates]
            if self._last_root_id in roots:
                pivot = roots.index(self._last_root_id) + 1
                candidates = candidates[pivot:] + candidates[:pivot]
            selected_id: str | None = None
            if affinity_available:
                match = next((row for row in candidates if self._row_cache_cohort(row) == self._last_cache_cohort), None)
                if match is not None and candidates[0] is not match:
                    candidates = [match, *[row for row in candidates if row is not match]]
                    selected_id = str(match["id"])
                    affinity_available = False
            ordered.extend((row, str(row["id"]) == selected_id) for row in candidates)
        return ordered

    def _note_dispatch(self, row: dict[str, Any]) -> None:
        root_id = str(row["root_id"] or row["id"])
        cohort = self._row_cache_cohort(row)
        self._last_root_id = root_id
        if cohort and cohort == self._last_cache_cohort:
            self._cache_affinity_streak += 1
        else:
            self._last_cache_cohort = cohort
            self._cache_affinity_streak = 0
        self._last_cache_dispatch_at = time.monotonic()

    def _collect_finished(self) -> None:
        with self._lock:
            finished = [task_id for task_id, future in self._futures.items() if future.done()]
            futures = [(task_id, self._futures.pop(task_id)) for task_id in finished]
        for task_id, future in futures:
            try:
                future.result()
            except Exception as exc:  # pragma: no cover - final defensive boundary
                row = self.store.get_task(task_id)
                if row and row["status"] not in {"completed", "failed", "cancelled", "blocked"}:
                    self.store.update_status(task_id, "failed", error=f"Scheduler error: {exc}")

    def _review_workspace(self, task_id: str, default: str) -> str:
        for dependency in self.store.dependencies(task_id):
            row = self.store.get_task(dependency)
            if row and row.get("kind") == "execute" and row.get("worktree_path"):
                return str(row["worktree_path"])
        return default

    def _run_task(self, task_id: str, lease_id: str) -> None:
        del lease_id  # The claim is persisted for observability; a single scheduler owns execution.
        row = self.store.get_task(task_id)
        if not row or row["status"] == "cancelled":
            return
        try:
            spec = self.store.get_spec(task_id)
            # A native task is deliberately handed back to the interactive Codex
            # host.  The host later claims the durable ticket and calls
            # spawn_agent; running codex exec here would be a misleading fallback.
            if spec.execution_channel == "native_subagent":
                self.store.stage_native_dispatch(task_id)
                return
            if not spec.gateway:
                route = self.cfg.resolve_route(
                    spec.reasoning_effort,
                    spec.model,
                    required_capabilities=spec.required_capabilities,
                )
                spec.gateway = route.gateway
                spec.upstream_model = route.upstream_model
                spec.response_mode = route.response_mode
                spec.fallback_gateway = route.fallback_gateway
                spec.provider = route.provider
                spec.billing_class = route.billing_class
                spec.route_capabilities = list(route.capabilities)
                spec.catalog_revision = route.catalog_revision
                spec.cache_cohort = route.cache_cohort
                configure_task_cache(self.cfg, spec)
                self.store.update_spec(task_id, spec)
                self.store.add_event(task_id, "task.route_migrated", {"gateway": route.gateway, "response_mode": route.response_mode})
            spec = validate_task(spec, self.cfg)
            cwd = spec.workspace
            if spec.kind == "execute":
                info = create_worktree(spec.workspace, task_id, self.cfg)
                cwd = info.path
                self.store.update_status(
                    task_id,
                    "starting",
                    worktree_path=info.path,
                    branch_name=info.branch,
                )
            elif spec.kind == "review":
                cwd = self._review_workspace(task_id, spec.workspace)

            def on_event(event_type: str, payload: dict[str, Any]) -> None:
                self.store.add_event(task_id, event_type, payload)

            def on_pid(pid: int) -> None:
                self.store.set_pid(task_id, pid)
                self.store.update_status(task_id, "running")

            self.store.add_event(
                task_id,
                "worker.gateway_selected",
                {
                    "gateway": spec.gateway,
                    "model": spec.model,
                    "upstream_model": spec.upstream_model,
                    "response_mode": spec.response_mode,
                    "provider": spec.provider,
                    "execution_channel": spec.execution_channel,
                    "required_capabilities": spec.required_capabilities,
                    "route_capabilities": spec.route_capabilities,
                    "catalog_revision": spec.catalog_revision,
                    "cache_cohort": spec.cache_cohort,
                },
            )

            worker = self.worker or build_worker(self.cfg, spec)
            result = worker.run(
                task_id,
                spec,
                cwd,
                on_event=on_event,
                on_pid=on_pid,
                is_cancelled=lambda: self.store.is_cancelled(task_id),
            )
            self._finish_task(task_id, spec, result)
        except (PolicyError, WorktreeError) as exc:
            self.store.update_status(task_id, "blocked", error=str(exc))
        except Exception as exc:
            self.store.update_status(task_id, "failed", error=f"Worker error: {exc}")

    def _finish_task(self, task_id: str, spec: TaskSpec, result: RunResult) -> None:
        if result.status != "completed":
            self.store.update_status(
                task_id,
                result.status,
                error=result.error,
                result_path=result.result_path,
            )
            return
        payload = result.result or {}
        if spec.kind == "plan":
            try:
                child_ids = self._expand_plan(task_id, spec, payload)
                payload = dict(payload)
                payload["child_task_ids"] = child_ids
            except PolicyError as exc:
                self.store.update_status(
                    task_id,
                    "failed",
                    error=f"Planner policy rejection: {exc}",
                    result=payload,
                    result_path=result.result_path,
                )
                return
        elif payload.get("status") in {"blocked", "failed"}:
            semantic_status = str(payload["status"])
            self.store.update_status(
                task_id,
                semantic_status,
                error=str(payload.get("summary") or f"Worker reported {semantic_status}"),
                result=payload,
                result_path=result.result_path,
            )
            return
        self.store.update_status(
            task_id,
            "completed",
            result=payload,
            result_path=result.result_path,
        )

    def _expand_plan(self, planner_id: str, planner: TaskSpec, plan: dict[str, Any]) -> list[str]:
        items = topological_order(validate_plan(plan, self.cfg))
        root_id = planner.root_id or planner_id
        generated = {str(item["id"]): f"task-{uuid.uuid4().hex[:12]}" for item in items}
        entries: list[tuple[TaskSpec, str, int]] = []
        for item in items:
            name = str(item["id"])
            kind = str(item.get("kind", "explore"))
            requested_effort = str(item["reasoning_effort"]) if item.get("reasoning_effort") else None
            profile = str(item["profile"]) if item.get("profile") else None
            try:
                selected = self.cfg.resolve_profile(
                    profile,
                    kind=kind,
                    model=str(item["model"]) if item.get("model") else None,
                    reasoning_effort=requested_effort,
                )
            except ValueError as exc:
                raise PolicyError(f"Invalid planned task {name!r}: {exc}") from exc
            reasoning_effort = selected.reasoning_effort
            execution_channel = str(item.get("execution_channel", "lightworker_worker"))
            raw_capabilities = item.get("required_capabilities", [])
            if not isinstance(raw_capabilities, list):
                raise PolicyError(f"Invalid planned task {name!r}: required_capabilities must be an array")
            required_capabilities = [str(value) for value in raw_capabilities]
            if execution_channel == "native_subagent" and "native_subagents" not in required_capabilities:
                required_capabilities.append("native_subagents")
            try:
                route = self.cfg.resolve_route(
                    reasoning_effort,
                    selected.model,
                    selected.gateway,
                    required_capabilities=required_capabilities,
                )
            except ValueError as exc:
                raise PolicyError(f"Invalid planned task {name!r}: {exc}") from exc
            status = "queued"
            if planner.mode == "plan_only" or (planner.mode == "auto_readonly" and kind == "execute"):
                status = "awaiting_approval"
            child = TaskSpec(
                task_id=generated[name],
                root_id=root_id,
                parent_id=planner_id,
                name=name,
                kind=kind,
                objective=str(item["objective"]),
                workspace=planner.workspace,
                model=route.model,
                profile=selected.profile,
                requested_model=str(item["model"]) if item.get("model") else None,
                requested_gateway=None,
                requested_reasoning_effort=requested_effort,
                gateway=route.gateway,
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
                context_pack_name=planner.context_pack_name,
                context_pack_version=planner.context_pack_version,
                context_pack_content=planner.context_pack_content,
                context_pack_hash=planner.context_pack_hash,
                reasoning_effort=reasoning_effort,
                sandbox="workspace-write" if kind == "execute" else "read-only",
                mode=planner.mode,
                timeout_seconds=int(item.get("timeout_seconds", planner.timeout_seconds)),
                allowed_paths=[str(value) for value in item.get("allowed_paths", [])],
                prohibited_actions=[str(value) for value in item.get("prohibited_actions", [])],
                success_criteria=[str(value) for value in item.get("success_criteria", [])],
                dependencies=[generated[str(dep)] for dep in item.get("dependencies", [])],
                metadata={
                    "planned_by": planner_id,
                    "profile_description": self.cfg.worker_profiles[selected.profile].description if selected.profile else "",
                },
            )
            configure_task_cache(self.cfg, child)
            validate_task(child, self.cfg)
            if status == "awaiting_approval":
                stamp_approval(child)
            entries.append((child, status, 0))
        child_ids = self.store.create_tasks(entries)
        for child_id, (child, _, _) in zip(child_ids, entries, strict=True):
            self.store.add_event(child_id, "worker.route_requested", {
                "profile": child.profile,
                "model": child.requested_model,
                "gateway": child.requested_gateway,
                "reasoning_effort": child.requested_reasoning_effort,
            })
            self.store.add_event(child_id, "worker.route_resolved", {
                "profile": child.profile,
                "model": child.model,
                "gateway": child.gateway,
                "upstream_model": child.upstream_model,
                "reasoning_effort": child.reasoning_effort,
                "response_mode": child.response_mode,
                "provider": child.provider,
                "billing_class": child.billing_class,
                "execution_channel": child.execution_channel,
                "required_capabilities": child.required_capabilities,
                "route_capabilities": child.route_capabilities,
                "catalog_revision": child.catalog_revision,
                "verification": "configured",
            })
            if child.approval_id:
                self.store.add_event(child_id, "approval.requested", {
                    "approval_id": child.approval_id,
                    "scope_digest": child.approval_scope_digest,
                    "scope_version": child.approval_scope.get("version"),
                })
            else:
                self.store.add_event(child_id, "worker.dispatch.accepted", {
                    "status": "queued",
                    "execution_channel": child.execution_channel,
                    "gateway": child.gateway,
                })
        return child_ids

    def cancel(self, task_id: str) -> bool:
        return self.store.cancel(task_id)
