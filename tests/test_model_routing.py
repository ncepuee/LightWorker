
from pathlib import Path

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
