
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


def test_root_budget_limits_concurrency_without_starving_another_root(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    store = TaskStore(cfg.db_path)
    first = TaskSpec(objective="one", workspace=str(tmp_path), root_id="root-a")
    second = TaskSpec(objective="two", workspace=str(tmp_path), root_id="root-a")
    other = TaskSpec(objective="other", workspace=str(tmp_path), root_id="root-b")
    first_id = store.create_task(first)
    second_id = store.create_task(second)
    other_id = store.create_task(other)
    store.ensure_root_budget("root-a", max_concurrency=1, max_attempts=3)
    store.ensure_root_budget("root-b", max_concurrency=1, max_attempts=3)

    assert store.claim_task(first_id)
    assert [row["id"] for row in store.ready_tasks(10)] == [other_id]
    assert store.claim_task(second_id) is None
    assert store.claim_task(other_id)
    store.update_status(first_id, "completed", result={"summary": "ok"})
    assert store.claim_task(second_id)


def test_root_budget_blocks_attempts_and_reserves_retry_once(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    store = TaskStore(cfg.db_path)
    task = TaskSpec(objective="one", workspace=str(tmp_path), root_id="root-budget")
    task_id = store.create_task(task)
    store.ensure_root_budget(
        "root-budget", max_concurrency=1, max_attempts=1, max_retries=1, max_escalations=0
    )
    assert store.reserve_budget("root-budget", "retry")
    assert not store.reserve_budget("root-budget", "retry")
    assert not store.reserve_budget("root-budget", "escalation")
    assert store.claim_task(task_id)

    blocked = TaskSpec(objective="two", workspace=str(tmp_path), root_id="root-budget")
    blocked_id = store.create_task(blocked)
    store.update_status(task_id, "completed", result={"summary": "ok"})
    assert store.claim_task(blocked_id) is None
    assert store.get_task(blocked_id)["status"] == "blocked"
    assert store.root_budget("root-budget")["attempts_used"] == 1


def test_ready_tasks_round_robin_across_roots(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    store = TaskStore(cfg.db_path)
    ids: dict[str, str] = {}
    for root in ("root-a", "root-b"):
        store.ensure_root_budget(root, max_concurrency=2)
        for index in (1, 2):
            ids[f"{root}-{index}"] = store.create_task(
                TaskSpec(objective=f"{root}-{index}", workspace=str(tmp_path), root_id=root)
            )
    ready = store.ready_tasks(4)
    roots = [row["root_id"] for row in ready]
    assert roots[:2] == ["root-a", "root-b"]
    assert roots[2:] == ["root-a", "root-b"]
