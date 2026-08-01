from __future__ import annotations

from pathlib import Path

from lightworker.config import Config
from lightworker.models import RunResult, TaskSpec, WorktreeInfo
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


def test_cancelled_task_cannot_be_overwritten_by_worker_completion(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store, worker=FakeWorker())
    spec = TaskSpec(objective="inspect", workspace=str(tmp_path), model="gpt-5.6-terra")
    task_id = store.create_task(spec)
    assert store.claim_task(task_id)
    assert store.cancel(task_id)

    scheduler._finish_task(
        task_id,
        spec,
        RunResult(
            status="completed",
            result={
                "status": "completed",
                "summary": "late result",
                "evidence": [],
                "changed_files": [],
                "tests": [],
                "risks": [],
                "followups": [],
            },
        ),
    )

    assert store.get_task(task_id)["status"] == "cancelled"
    scheduler.stop(wait=True)


def test_cancel_during_worktree_creation_does_not_start_worker(tmp_path: Path, monkeypatch) -> None:
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()
    store = TaskStore(cfg.db_path)
    worker = FakeWorker()
    scheduler = Scheduler(cfg, store, worker=worker)
    spec = TaskSpec(
        objective="change one file",
        workspace=str(tmp_path),
        kind="execute",
        model="gpt-5.6-sol",
        sandbox="workspace-write",
        mode="auto_execute",
    )
    task_id = store.create_task(spec)
    lease_id = store.claim_task(task_id)
    assert lease_id

    def cancel_while_creating(*_args, **_kwargs):
        assert store.cancel(task_id)
        return WorktreeInfo(path=str(tmp_path), branch=f"lightworker/{task_id}")

    monkeypatch.setattr("lightworker.scheduler.create_worktree", cancel_while_creating)
    scheduler._run_task(task_id, lease_id)

    assert worker.calls == []
    assert store.get_task(task_id)["status"] == "cancelled"
    scheduler.stop(wait=True)
