
from pathlib import Path
import time

from lightworker.config import Config
from lightworker.instance_lock import InstanceLock
from lightworker.scheduler import Scheduler
from lightworker.store import TaskStore


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
