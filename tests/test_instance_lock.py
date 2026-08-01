from pathlib import Path
import threading
import time

from lightworker.config import Config
from lightworker.instance_lock import InstanceLock
from lightworker.models import RunResult, TaskSpec
from lightworker.scheduler import Scheduler
from lightworker.store import TaskStore


class BlockingWorker:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, task_id, spec, cwd, on_event, on_pid, is_cancelled):
        on_pid(4242)
        self.started.set()
        assert self.release.wait(timeout=5)
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


def test_only_one_instance_holds_scheduler_lock(tmp_path: Path) -> None:
    path = tmp_path / "scheduler.lock"
    first = InstanceLock(path)
    second = InstanceLock(path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_standby_scheduler_takes_over_after_active_stops(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path, poll_interval_seconds=0.05)
    first = Scheduler(cfg, TaskStore(cfg.db_path))
    second = Scheduler(cfg, TaskStore(cfg.db_path))
    try:
        assert first.start_background()
        assert not second.start_background(allow_passive=True)
        assert second.is_background_alive
        assert not second.owns_instance_lock

        first.stop(wait=True)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not second.owns_instance_lock:
            time.sleep(0.02)
        assert second.owns_instance_lock
        assert second.is_background_alive
    finally:
        if first.is_background_alive:
            first.stop(wait=True)
        second.stop(wait=True)


def test_shutdown_keeps_instance_lock_until_active_worker_exits(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path, poll_interval_seconds=0.01)
    store = TaskStore(cfg.db_path)
    worker = BlockingWorker()
    scheduler = Scheduler(cfg, store, worker=worker)
    spec = TaskSpec(
        objective="block until released",
        workspace=str(tmp_path),
        model="gpt-5.6-terra",
    )
    store.create_task(spec)
    assert scheduler.start_background()
    assert worker.started.wait(timeout=2)

    stopping = threading.Thread(target=scheduler.stop, kwargs={"wait": True})
    stopping.start()
    time.sleep(0.05)
    probe = InstanceLock(cfg.scheduler_lock_path)
    assert not probe.acquire()

    worker.release.set()
    stopping.join(timeout=2)
    assert not stopping.is_alive()
    assert probe.acquire()
    probe.release()
