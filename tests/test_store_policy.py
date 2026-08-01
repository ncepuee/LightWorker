from pathlib import Path

import pytest

from lightworker.config import Config
from lightworker.models import TaskSpec
from lightworker.policy import PolicyError, validate_plan, validate_task
from lightworker.store import TaskStore


def config(tmp_path: Path) -> Config:
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()
    return cfg


def test_dependency_becomes_ready_after_parent_completion(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    store = TaskStore(cfg.db_path)
    parent = TaskSpec(objective="inspect", workspace=str(tmp_path), model="gpt-5.6-terra")
    parent_id = store.create_task(parent)
    child = TaskSpec(
        objective="review",
        workspace=str(tmp_path),
        kind="review",
        model="deepseek/deepseek-v4-pro",
        dependencies=[parent_id],
    )
    child_id = store.create_task(child)
    assert [row["id"] for row in store.ready_tasks(10)] == [parent_id]
    store.update_status(parent_id, "completed", result={"summary": "ok"})
    assert [row["id"] for row in store.ready_tasks(10)] == [child_id]


def test_policy_forces_readonly_and_rejects_escape(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    spec = TaskSpec(
        objective="inspect",
        workspace=str(tmp_path),
        kind="explore",
        model="gpt-5.6-terra",
        sandbox="workspace-write",
    )
    assert validate_task(spec, cfg).sandbox == "read-only"
    spec.allowed_paths = [".."]
    with pytest.raises(PolicyError):
        validate_task(spec, cfg)


def test_plan_cycle_is_rejected(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    plan = {
        "tasks": [
            {"id": "a", "dependencies": ["b"]},
            {"id": "b", "dependencies": ["a"]},
        ]
    }
    with pytest.raises(PolicyError, match="cycle"):
        validate_plan(plan, cfg)
