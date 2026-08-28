from pathlib import Path

import pytest

from lightworker.config import Config
from lightworker.service import LightWorkerService
from lightworker.store import TaskStore


def test_automatic_model_routing_uses_flash_only_for_low_effort(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]

    low = service.delegate_task(
        {
            "objective": "format a list",
            "workspace": str(tmp_path),
            "kind": "explore",
            "reasoning_effort": "low",
        }
    )
    high = service.delegate_task(
        {
            "objective": "design an architecture",
            "workspace": str(tmp_path),
            "kind": "review",
            "reasoning_effort": "high",
        }
    )

    assert service.task(low["task_id"])["model"] == "deepseek/deepseek-v4-flash"
    assert service.task(high["task_id"])["model"] == "gpt-5.6-sol"


def test_execute_without_profile_routes_to_cost_efficient_executor(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]

    task = service.delegate_task(
        {
            "objective": "implement the parser",
            "workspace": str(tmp_path),
            "kind": "execute",
        }
    )

    assert service.task(task["task_id"])["model"] == "gpt-5.6-luna"
    assert task["status"] == "awaiting_approval"


def test_explicit_model_overrides_execute_default(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]

    task = service.delegate_task(
        {
            "objective": "implement the parser",
            "workspace": str(tmp_path),
            "kind": "execute",
            "model": "gpt-5.6-sol",
        }
    )

    assert service.task(task["task_id"])["model"] == "gpt-5.6-sol"


def test_review_without_profile_keeps_reasoning_default(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]

    task = service.delegate_task(
        {
            "objective": "audit the diff",
            "workspace": str(tmp_path),
            "kind": "review",
        }
    )

    assert service.task(task["task_id"])["model"] == "gpt-5.6-sol"


def test_executor_profile_is_luna_max_and_execute_only(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)

    selected = cfg.resolve_profile("executor", kind="execute")
    assert selected.model == "gpt-5.6-luna"
    assert selected.reasoning_effort == "max"

    with pytest.raises(ValueError, match="does not allow task kind"):
        cfg.resolve_profile("executor", kind="explore")
