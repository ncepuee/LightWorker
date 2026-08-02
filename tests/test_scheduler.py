
from __future__ import annotations

from pathlib import Path
import time

import pytest

from lightworker.config import Config
from lightworker.models import RunResult, TaskSpec
from lightworker.policy import PolicyError
from lightworker.scheduler import Scheduler
from lightworker.service import LightWorkerService
from lightworker.store import TaskStore


class FakeWorker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, task_id, spec, cwd, on_event, on_pid, is_cancelled):
        self.calls.append(task_id)
        on_pid(1000 + len(self.calls))
        on_event("turn.started", {"type": "turn.started"})
        if spec.kind == "plan":
            return RunResult(
                status="completed",
                result={
                    "summary": "test plan",
                    "tasks": [
                        {
                            "id": "inspect",
                            "kind": "explore",
                            "objective": "inspect files",
                            "dependencies": [],
                            "model": "gpt-5.6-terra",
                            "reasoning_effort": "medium",
                            "timeout_seconds": 60,
                            "allowed_paths": [],
                            "prohibited_actions": [],
                            "success_criteria": ["report findings"],
                        },
                        {
                            "id": "fix",
                            "kind": "execute",
                            "objective": "fix issue",
                            "dependencies": ["inspect"],
                            "model": "gpt-5.6-sol",
                            "reasoning_effort": "high",
                            "timeout_seconds": 60,
                            "allowed_paths": [],
                            "prohibited_actions": [],
                            "success_criteria": ["tests pass"],
                        },
                    ],
                },
            )
        return RunResult(
            status="completed",
            result={
                "status": "completed",
                "summary": "done",
                "evidence": [],
                "changed_files": [],
                "tests": [],
                "risks": [],
                "followups": [],
            },
        )


def test_auto_readonly_runs_explorer_and_holds_executor(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path / "state", poll_interval_seconds=0.01)
    cfg.ensure_dirs()
    store = TaskStore(cfg.db_path)
    worker = FakeWorker()
    scheduler = Scheduler(cfg, store, worker=worker)
    service = LightWorkerService(cfg, store, scheduler)
    root = service.orchestrate("solve it", str(tmp_path), mode="auto_readonly")
    assert scheduler.run_until_idle(timeout=5)
    rows = store.list_tasks(root_id=root["root_task_id"])
    by_kind = {row["kind"]: row for row in rows}
    assert by_kind["plan"]["status"] == "completed"
    assert by_kind["explore"]["status"] == "completed"
    assert by_kind["execute"]["status"] == "awaiting_approval"


def test_invalid_late_planned_child_creates_no_partial_children(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path / "state")
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store, worker=FakeWorker())
    planner = TaskSpec(objective="plan", workspace=str(tmp_path), kind="plan", model="gpt-5.6-sol")
    planner_id = store.create_task(planner)
    plan = {
        "summary": "invalid late child",
        "tasks": [
            {"id": "first", "kind": "explore", "objective": "ok", "dependencies": []},
            {"id": "second", "kind": "review", "objective": "bad", "dependencies": ["first"], "profile": "missing"},
        ],
    }
    with pytest.raises(PolicyError, match="Invalid planned task"):
        scheduler._expand_plan(planner_id, planner, plan)
    assert [row["id"] for row in store.list_tasks(root_id=planner_id)] == [planner_id]


def test_cache_affinity_is_bounded_by_root_fairness(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path / "state")
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store, worker=FakeWorker())
    a = store.create_task(TaskSpec(objective="a", workspace=str(tmp_path), root_id="root-a", cache_cohort="cold"))
    b = store.create_task(TaskSpec(objective="b", workspace=str(tmp_path), root_id="root-b", cache_cohort="warm"))
    rows = store.ready_tasks(10)
    scheduler._last_root_id = "root-b"
    scheduler._last_cache_cohort = "warm"
    scheduler._last_cache_dispatch_at = time.monotonic()
    scheduler._cache_affinity_streak = 0
    ordered = scheduler._order_ready(rows)
    assert ordered[0][0]["id"] == b and ordered[0][1]
    scheduler._note_dispatch(ordered[0][0])

    rows = store.ready_tasks(10)
    ordered = scheduler._order_ready(rows)
    assert ordered[0][0]["id"] == a
    assert not ordered[0][1]
