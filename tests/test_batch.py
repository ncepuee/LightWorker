
from pathlib import Path

import pytest

from lightworker.config import Config
from lightworker.policy import PolicyError
from lightworker.scheduler import Scheduler
from lightworker.service import LightWorkerService
from lightworker.store import TaskStore


def test_batch_resolves_name_dependencies(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    service = LightWorkerService(cfg, store, scheduler)
    result = service.delegate_batch(
        [
            {
                "id": "inspect",
                "objective": "inspect",
                "workspace": str(tmp_path),
                "kind": "explore",
                "model": "gpt-5.6-terra",
            },
            {
                "id": "review",
                "objective": "review",
                "workspace": str(tmp_path),
                "kind": "review",
                "model": "deepseek/deepseek-v4-pro",
                "dependencies": ["inspect"],
            },
        ]
    )
    ids = {item["name"]: item["task_id"] for item in result["tasks"]}
    assert store.dependencies(ids["review"]) == [ids["inspect"]]


def test_invalid_late_batch_item_creates_nothing(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path / "state")
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    with pytest.raises(PolicyError, match="Invalid batch task"):
        service.delegate_batch([
            {"id": "valid", "objective": "inspect", "workspace": str(tmp_path)},
            {"id": "invalid", "objective": "review", "workspace": str(tmp_path), "profile": "missing"},
        ])
    assert store.list_tasks() == []


def test_batch_rejects_external_parent_relationship(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path / "state")
    service = LightWorkerService(cfg, TaskStore(cfg.db_path), None)  # type: ignore[arg-type]
    with pytest.raises(PolicyError, match="cannot declare parent_id"):
        service.delegate_batch([
            {"id": "child", "objective": "inspect", "workspace": str(tmp_path), "parent_id": "task-external"}
        ])
