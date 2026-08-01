from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .config import Config
from .instance_lock import InstanceLock
from .models import RunResult, TaskSpec
from .policy import PolicyError, topological_order, validate_plan, validate_task
from .store import TaskStore
from .worker import CodexWorker
from .worktree import WorktreeError, create_worktree


class Scheduler:
    def __init__(self, cfg: Config, store: TaskStore, worker: CodexWorker | None = None):
        self.cfg = cfg
        self.store = store
        self.worker = worker or CodexWorker(cfg)
        self._executor = ThreadPoolExecutor(
            max_workers=cfg.max_concurrency, thread_name_prefix="lightworker"
        )
        self._futures: dict[str, Future[None]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._instance_lock = InstanceLock(cfg.scheduler_lock_path)
        self._owns_instance_lock = False

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
                for row in self.store.ready_tasks(available):
                    task_id = str(row["id"])
                    lease = self.store.claim_task(task_id)
                    if not lease:
                        continue
                    future = self._executor.submit(self._run_task, task_id, lease)
                    with self._lock:
                        self._futures[task_id] = future
            self._stop.wait(self.cfg.poll_interval_seconds)
        self._collect_finished()

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
            spec = validate_task(self.store.get_spec(task_id), self.cfg)
            cwd = spec.workspace
            if spec.kind == "execute":
                if self.store.is_cancelled(task_id):
                    return
                info = create_worktree(spec.workspace, task_id, self.cfg)
                cwd = info.path
                if not self.store.update_status(
                    task_id,
                    "starting",
                    worktree_path=info.path,
                    branch_name=info.branch,
                    expected_statuses={"starting"},
                ):
                    return
            elif spec.kind == "review":
                cwd = self._review_workspace(task_id, spec.workspace)

            def on_event(event_type: str, payload: dict[str, Any]) -> None:
                self.store.add_event(task_id, event_type, payload)

            def on_pid(pid: int) -> None:
                self.store.set_pid(task_id, pid)
                self.store.update_status(task_id, "running", expected_statuses={"starting"})

            if self.store.is_cancelled(task_id):
                return

            result = self.worker.run(
                task_id,
                spec,
                cwd,
                on_event=on_event,
                on_pid=on_pid,
                is_cancelled=lambda: self.store.is_cancelled(task_id),
            )
            self._finish_task(task_id, spec, result)
        except (PolicyError, WorktreeError) as exc:
            self.store.update_status(
                task_id,
                "blocked",
                error=str(exc),
                expected_statuses={"starting", "running"},
            )
        except Exception as exc:
            self.store.update_status(
                task_id,
                "failed",
                error=f"Worker error: {exc}",
                expected_statuses={"starting", "running"},
            )

    def _finish_task(self, task_id: str, spec: TaskSpec, result: RunResult) -> None:
        if result.status != "completed":
            self.store.update_status(
                task_id,
                result.status,
                error=result.error,
                result_path=result.result_path,
                expected_statuses={"starting", "running"},
            )
            return
        payload = result.result or {}
        if spec.kind == "plan":
            if not self.store.update_status(
                task_id,
                "finishing",
                expected_statuses={"starting", "running"},
            ):
                return
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
                    expected_statuses={"finishing"},
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
                expected_statuses={"starting", "running"},
            )
            return
        self.store.update_status(
            task_id,
            "completed",
            result=payload,
            result_path=result.result_path,
            expected_statuses={"finishing"} if spec.kind == "plan" else {"starting", "running"},
        )

    def _expand_plan(self, planner_id: str, planner: TaskSpec, plan: dict[str, Any]) -> list[str]:
        items = topological_order(validate_plan(plan, self.cfg))
        root_id = planner.root_id or planner_id
        generated = {str(item["id"]): f"task-{uuid.uuid4().hex[:12]}" for item in items}
        child_ids: list[str] = []
        for item in items:
            name = str(item["id"])
            kind = str(item.get("kind", "explore"))
            reasoning_effort = str(item.get("reasoning_effort", "medium"))
            model = self.cfg.route_model(reasoning_effort, item.get("model"))
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
                model=model,
                reasoning_effort=reasoning_effort,
                sandbox="workspace-write" if kind == "execute" else "read-only",
                mode=planner.mode,
                timeout_seconds=int(item.get("timeout_seconds", planner.timeout_seconds)),
                allowed_paths=[str(value) for value in item.get("allowed_paths", [])],
                prohibited_actions=[str(value) for value in item.get("prohibited_actions", [])],
                success_criteria=[str(value) for value in item.get("success_criteria", [])],
                dependencies=[generated[str(dep)] for dep in item.get("dependencies", [])],
                metadata={"planned_by": planner_id},
            )
            validate_task(child, self.cfg)
            child_ids.append(self.store.create_task(child, status=status))
        return child_ids

    def cancel(self, task_id: str) -> bool:
        return self.store.cancel(task_id)
