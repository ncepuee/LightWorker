"""v0.8.0 M1 regression tests: backend session truth.

Covers: backend_session_id persistence, session extraction from worker
streams, pid-liveness restart reconciliation, and the unowned-dead-task
reaper that eliminates stuck "running" rows.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from lightworker.config import Config, load_config
from lightworker.models import TaskSpec
from lightworker.scheduler import Scheduler
from lightworker.store import TaskStore
from lightworker.worker import ZCodeWorker, extract_session_id, pid_alive


def make_config(tmp_path: Path, **runner) -> Config:
    config_path = tmp_path / "config.toml"
    lines = [f"{key} = {value!r}" if isinstance(value, str) else f"{key} = {value}" for key, value in runner.items()]
    if lines:
        config_path.write_text("[runner]\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return load_config(home=tmp_path / "state", config_path=config_path if lines else None)


# ---------------------------------------------------------------------------
# Session id extraction
# ---------------------------------------------------------------------------


def test_extract_session_id_from_codex_thread_event():
    assert extract_session_id({"type": "thread.started", "thread_id": "thr-123"}) == "thr-123"


def test_extract_session_id_alternate_keys():
    assert extract_session_id({"session_id": "sess-abc"}) == "sess-abc"
    assert extract_session_id({"sessionId": "doc-xyz"}) == "doc-xyz"


def test_extract_session_id_rejects_non_strings():
    assert extract_session_id({"thread_id": 12345}) is None
    assert extract_session_id({"type": "turn.started"}) is None
    assert extract_session_id({}) is None


# ---------------------------------------------------------------------------
# Store persistence
# ---------------------------------------------------------------------------


def test_store_migration_adds_backend_session_id(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    columns = {row["name"] for row in store._connection().execute("PRAGMA table_info(tasks)").fetchall()}
    assert "backend_session_id" in columns


def test_set_backend_session_persists_and_first_write_wins(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    task_id = store.create_task(TaskSpec(objective="x", workspace=str(tmp_path)))
    assert store.set_backend_session(task_id, "sess-first") is True
    assert store.set_backend_session(task_id, "sess-second") is False
    row = store.get_task(task_id)
    assert row["backend_session_id"] == "sess-first"
    events = [e["event_type"] for e in store.events(task_id, 0, 100)]
    assert "worker.session" in events


def test_set_backend_session_rejects_empty_or_overlong(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    task_id = store.create_task(TaskSpec(objective="x", workspace=str(tmp_path)))
    assert store.set_backend_session(task_id, "") is False
    assert store.set_backend_session(task_id, "x" * 300) is False


def test_public_task_exposes_backend_session_id(tmp_path: Path) -> None:
    from lightworker.models import public_task

    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    task_id = store.create_task(TaskSpec(objective="x", workspace=str(tmp_path)))
    store.set_backend_session(task_id, "sess-1")
    assert public_task(store.get_task(task_id))["backend_session_id"] == "sess-1"


# ---------------------------------------------------------------------------
# ZCode worker session capture (real subprocess with stub CLI)
# ---------------------------------------------------------------------------


def test_zcode_worker_captures_session_id_from_document(tmp_path: Path) -> None:
    cli = tmp_path / "zcode.cjs"
    cli.write_text(
        "const response = JSON.stringify({status:'completed',summary:'done',evidence:[],changed_files:[],tests:[],risks:[],followups:[]});\n"
        "process.stdout.write(JSON.stringify({sessionId:'sess_zcode_1',response,usage:{totalTokens:7}},null,2));\n",
        encoding="utf-8",
    )
    cfg = make_config(tmp_path, zcode_cli_path=str(cli))
    worker = ZCodeWorker(cfg)
    if worker._command_prefix() is None:
        pytest.skip("node is not available")
    result = worker.run(
        "task-sess",
        TaskSpec(objective="inspect", workspace=str(tmp_path), kind="explore"),
        tmp_path,
        on_event=lambda *args: None,
        on_pid=lambda pid: None,
        is_cancelled=lambda: False,
    )
    assert result.status == "completed"
    assert result.session_id == "sess_zcode_1"


# ---------------------------------------------------------------------------
# pid liveness probe
# ---------------------------------------------------------------------------


def test_pid_alive_for_current_process() -> None:
    assert pid_alive(os.getpid()) is True


def test_pid_alive_rejects_garbage() -> None:
    assert pid_alive(0) is False
    assert pid_alive(-5) is False


def test_pid_alive_false_for_exited_process(tmp_path: Path) -> None:
    proc = subprocess.Popen(["cmd.exe", "/c", "exit", "0"] if os.name == "nt" else ["true"])
    deadline = time.monotonic() + 5
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert proc.poll() is not None
    assert pid_alive(proc.pid) is False


# ---------------------------------------------------------------------------
# Restart reconciliation and reaper
# ---------------------------------------------------------------------------


def _running_task_with_pid(store: TaskStore, tmp_path: Path, pid: int | None) -> str:
    task_id = store.create_task(TaskSpec(objective="x", workspace=str(tmp_path), harness="codex"))
    store.update_status(task_id, "starting")
    if pid is not None:
        store.set_pid(task_id, pid)
    row = store.get_task(task_id)
    # set_pid only stores the value; force running status for the probe test.
    store._connection().execute("UPDATE tasks SET status='running' WHERE id=?", (task_id,))
    store._connection().commit()
    return task_id


def test_reconcile_keeps_running_task_with_alive_pid(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    task_id = _running_task_with_pid(store, tmp_path, os.getpid())
    orphaned = store.reconcile_after_restart(pid_alive=pid_alive)
    assert orphaned == 0
    assert store.get_task(task_id)["status"] == "running"
    event_types = [e["event_type"] for e in store.events(task_id, 0, 100)]
    assert "task.reconciled" in event_types


def test_reconcile_orphans_running_task_with_dead_pid(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    proc = subprocess.Popen(["cmd.exe", "/c", "exit", "0"] if os.name == "nt" else ["true"])
    deadline = time.monotonic() + 5
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    task_id = _running_task_with_pid(store, tmp_path, proc.pid)
    orphaned = store.reconcile_after_restart(pid_alive=pid_alive)
    assert orphaned == 1
    assert store.get_task(task_id)["status"] == "orphaned"


def test_reconcile_without_probe_orphans_everything(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    task_id = _running_task_with_pid(store, tmp_path, os.getpid())
    assert store.reconcile_after_restart(pid_alive=None) == 1
    assert store.get_task(task_id)["status"] == "orphaned"


def test_reaper_orphans_unowned_dead_process(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, poll_interval_seconds=0.01)
    store = TaskStore(cfg.db_path)
    proc = subprocess.Popen(["cmd.exe", "/c", "exit", "0"] if os.name == "nt" else ["true"])
    deadline = time.monotonic() + 5
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    task_id = _running_task_with_pid(store, tmp_path, proc.pid)

    class NullWorker:
        def run(self, *args, **kwargs):  # pragma: no cover - never dispatched
            raise AssertionError("no work should be dispatched")

    scheduler = Scheduler(cfg, store, worker=NullWorker())
    scheduler._reap_unowned_dead_tasks()
    assert store.get_task(task_id)["status"] == "orphaned"


def test_reaper_keeps_alive_unowned_process(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    store = TaskStore(cfg.db_path)
    task_id = _running_task_with_pid(store, tmp_path, os.getpid())

    class NullWorker:
        def run(self, *args, **kwargs):  # pragma: no cover - never dispatched
            raise AssertionError("no work should be dispatched")

    scheduler = Scheduler(cfg, store, worker=NullWorker())
    scheduler._reap_unowned_dead_tasks()
    assert store.get_task(task_id)["status"] == "running"


# ---------------------------------------------------------------------------
# ZCode environment passthrough (0.17+ built-in provider config discovery)
# ---------------------------------------------------------------------------


def test_zcode_environment_passes_through_zcode_runtime_hints(tmp_path, monkeypatch) -> None:
    from lightworker.worker import _zcode_environment

    monkeypatch.setenv("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", "C:/app/.zcode/v2/runtime/provider/zcode-builtin.json")
    monkeypatch.setenv("ZCODE_WINDOWS_APP_INSTALL_DIR", "D:/ZCode")
    monkeypatch.setenv("ZCODE_SECRET_MARKER", "not-a-secret-but-filtered-anyway")
    monkeypatch.setenv("LIGHTWORKER_TEST_MARKER", "secret")
    cfg = make_config(tmp_path)
    env = _zcode_environment(cfg)
    assert env["ZCODE_BUILTIN_PROVIDER_CONFIG_FILE"].endswith("zcode-builtin.json")
    assert env["ZCODE_WINDOWS_APP_INSTALL_DIR"] == "D:/ZCode"
    # ZCODE_ prefix passthrough is scoped: unrelated unprefixed vars stay out.
    assert "LIGHTWORKER_TEST_MARKER" not in env
