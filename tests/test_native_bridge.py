from pathlib import Path

import pytest

from lightworker.config import Config, GatewayConfig, ModelRoute
from lightworker.scheduler import Scheduler
from lightworker.service import LightWorkerService
from lightworker.store import TaskStore


class NeverRunWorker:
    def run(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("native_subagent must never fall back to codex exec")


def native_config(tmp_path: Path) -> Config:
    cfg = Config(home=tmp_path, default_gateway="opencodex", poll_interval_seconds=0.01)
    cfg.gateways = {
        "opencodex": GatewayConfig(
            "opencodex", "http://127.0.0.1:10100/v1", "native",
            capabilities=("responses", "codex_tools", "native_subagents"),
        )
    }
    cfg.model_routes = {"deepseek/deepseek-v4-flash": ModelRoute(primary="opencodex")}
    return cfg


def test_native_ticket_is_dispatched_by_host_and_persists_thread_result(tmp_path: Path) -> None:
    cfg = native_config(tmp_path)
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store, worker=NeverRunWorker())  # type: ignore[arg-type]
    service = LightWorkerService(cfg, store, scheduler)
    created = service.delegate_task({
        "objective": "inspect this repository", "workspace": str(tmp_path), "kind": "explore",
        "execution_channel": "native_subagent", "mode": "auto_readonly",
    })
    assert scheduler.run_until_idle(timeout=2)
    assert service.task(created["task_id"])["status"] == "awaiting_native_dispatch"

    claimed = service.claim_native_dispatches("codex-session-test", limit=3)
    assert len(claimed["tickets"]) == 1
    ticket = claimed["tickets"][0]
    assert ticket["objective"] == "inspect this repository"
    assert service.native_started(ticket["task_id"], ticket["lease_id"], "thread-native-1")["status"] == "running"
    assert service.native_event(ticket["task_id"], ticket["lease_id"], "native.progress", {"phase": "scan"})["accepted"]
    assert service.native_completed(
        ticket["task_id"], ticket["lease_id"], "completed", {"summary": "done"}
    )["status"] == "completed"
    task = service.task(ticket["task_id"])
    assert task["native_thread_id"] == "thread-native-1"
    assert task["result"]["summary"] == "done"


def test_native_lease_rejects_duplicate_completion(tmp_path: Path) -> None:
    cfg = native_config(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    created = service.delegate_task({
        "objective": "inspect", "workspace": str(tmp_path), "execution_channel": "native_subagent"
    })
    # Simulate scheduler staging without starting a real runner.
    assert store.claim_task(created["task_id"])
    assert store.stage_native_dispatch(created["task_id"])
    ticket = service.claim_native_dispatches("host")["tickets"][0]
    service.native_started(ticket["task_id"], ticket["lease_id"], "thread-1")
    service.native_completed(ticket["task_id"], ticket["lease_id"], "completed", {"summary": "ok"})
    with pytest.raises(Exception, match="stale|terminal"):
        service.native_completed(ticket["task_id"], ticket["lease_id"], "completed", {"summary": "again"})
