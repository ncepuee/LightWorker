from pathlib import Path

from lightworker.config import Config
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
