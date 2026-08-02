
from pathlib import Path

import pytest

from lightworker.config import Config, GatewayConfig, ModelRoute, load_config, write_default_config
from lightworker.models import RunResult, TaskSpec
from lightworker.policy import PolicyError
from lightworker.scheduler import Scheduler
from lightworker.service import LightWorkerService
from lightworker.store import TaskStore


def configured(tmp_path: Path) -> Config:
    cfg = Config(home=tmp_path, codex_ignore_user_config=True, default_gateway="opencodex")
    cfg.gateways = {
        "opencodex": GatewayConfig("opencodex", "http://127.0.0.1:10100/v1", "native"),
        "cliproxyapi": GatewayConfig("cliproxyapi", "http://127.0.0.1:8317/v1", "translated", api_key_env="CLIPROXYAPI_CLIENT_KEY"),
    }
    cfg.model_routes = {
        "deepseek/deepseek-v4-flash": ModelRoute(
            primary="opencodex", fallback=("cliproxyapi",),
            upstream_models={"cliproxyapi": "deepseek-v4-flash"},
        )
    }
    return cfg


def test_route_is_sticky_and_maps_fallback_upstream_model(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    service = LightWorkerService(cfg, TaskStore(cfg.db_path), None)  # type: ignore[arg-type]
    created = service.delegate_task({"objective": "inspect files", "workspace": str(tmp_path), "reasoning_effort": "low"})
    task = service.task(created["task_id"])
    assert (task["gateway"], task["upstream_model"], task["response_mode"], task["fallback_gateway"]) == (
        "opencodex", "deepseek/deepseek-v4-flash", "native", "cliproxyapi"
    )
    cfg.default_gateway = "cliproxyapi"
    assert service.task(created["task_id"])["gateway"] == "opencodex"


def test_profile_resolves_route_and_exposes_budgeted_audit(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    service = LightWorkerService(cfg, TaskStore(cfg.db_path), None)  # type: ignore[arg-type]
    created = service.delegate_task({
        "objective": "inspect files",
        "workspace": str(tmp_path),
        "profile": "fast_worker",
    })
    task = service.task(created["task_id"])
    assert (task["profile"], task["model"], task["reasoning_effort"]) == (
        "fast_worker", "deepseek/deepseek-v4-flash", "low"
    )
    assert task["route_audit"]["requested"]["profile"] == "fast_worker"
    assert task["route_audit"]["verification"] == "unverified"
    assert any(event["event_type"] == "worker.route_resolved" for event in service.events(created["task_id"])["events"])
    assert task["budget"]["max_escalations"] == 1


def test_root_budget_is_created_atomically_and_validated(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    created = service.delegate_task({
        "objective": "inspect",
        "workspace": str(tmp_path),
        "budget": {"max_concurrency": 1, "max_attempts": 2, "max_retries": 0, "max_escalations": 0},
    })
    budget = service.task(created["task_id"])["budget"]
    assert (budget["max_concurrency"], budget["max_attempts"], budget["max_retries"], budget["max_escalations"]) == (1, 2, 0, 0)
    with pytest.raises(PolicyError, match="budget must be an object"):
        service.delegate_task({"objective": "bad", "workspace": str(tmp_path), "budget": "unbounded"})


def test_reading_legacy_task_uses_current_config_budget_defaults(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    cfg.root_max_concurrency = 1
    cfg.root_max_attempts = 3
    store = TaskStore(cfg.db_path)
    task_id = store.create_task(TaskSpec(objective="legacy", workspace=str(tmp_path)))
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    budget = service.task(task_id)["budget"]
    assert (budget["max_concurrency"], budget["max_attempts"]) == (1, 3)


def test_legacy_orchestrate_respects_models_planner_default(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    cfg.model_defaults["planner"] = "gpt-5.5"
    service = LightWorkerService(cfg, TaskStore(cfg.db_path), None)  # type: ignore[arg-type]
    created = service.orchestrate("plan", str(tmp_path))
    task = service.task(created["root_task_id"])
    assert task["profile"] is None
    assert task["model"] == "gpt-5.5"


def test_external_delegation_depth_is_enforced(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    root = service.delegate_task({"objective": "root", "workspace": str(tmp_path)})["task_id"]
    child = service.delegate_task({"objective": "child", "workspace": str(tmp_path), "parent_id": root})["task_id"]
    with pytest.raises(PolicyError, match="Delegation depth"):
        service.delegate_task({"objective": "grandchild", "workspace": str(tmp_path), "parent_id": child})


def test_dependency_only_task_inherits_dependency_root_budget(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    root = service.delegate_task({"objective": "root", "workspace": str(tmp_path)})["task_id"]
    child = service.delegate_task({
        "objective": "child",
        "workspace": str(tmp_path),
        "dependencies": [root],
    })["task_id"]
    assert service.task(child)["root_id"] == root


def test_context_pack_reuses_strict_cohort_without_public_content(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    service = LightWorkerService(cfg, TaskStore(cfg.db_path), None)  # type: ignore[arg-type]
    shared = {"name": "repo-map", "version": "v1", "content": "Stable reviewed architecture context."}
    first = service.delegate_task({"objective": "inspect a", "workspace": str(tmp_path), "profile": "fast_worker", "context_pack": shared})
    second = service.delegate_task({"objective": "inspect b", "workspace": str(tmp_path), "profile": "fast_worker", "context_pack": shared})
    one, two = service.task(first["task_id"]), service.task(second["task_id"])
    assert one["cache_cohort"] == two["cache_cohort"]
    assert one["cache_cohort"].startswith("cache_cohort.v2:")
    assert one["context_pack_hash"] == two["context_pack_hash"]
    assert "Stable reviewed" not in str(one)

    changed = service.delegate_task({"objective": "inspect c", "workspace": str(tmp_path), "profile": "fast_worker", "context_pack": {**shared, "version": "v2"}})
    assert service.task(changed["task_id"])["cache_cohort"] != one["cache_cohort"]


def test_schema_invalid_readonly_task_can_escalate_only_within_budget(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    created = service.delegate_task({
        "objective": "inspect files",
        "workspace": str(tmp_path),
        "profile": "fast_worker",
    })
    store.update_status(created["task_id"], "completed", result={"schema_valid": False, "summary": "bad shape"})
    escalated = service.escalate(created["task_id"])
    task = service.task(escalated["task_id"])
    assert (task["profile"], task["model"], task["reasoning_effort"], task["parent_id"]) == (
        "deep_worker", "gpt-5.6-luna", "max", created["task_id"]
    )
    assert task["budget"]["escalations_used"] == 1
    with pytest.raises(PolicyError, match="escalation budget exhausted"):
        service.escalate(created["task_id"])


def test_failed_review_escalates_to_deep_worker(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    created = service.delegate_task({
        "objective": "review evidence",
        "workspace": str(tmp_path),
        "kind": "review",
        "profile": "reviewer",
    })
    store.update_status(created["task_id"], "failed", error="insufficient evidence")
    escalated = service.escalate(created["task_id"])
    assert service.task(escalated["task_id"])["profile"] == "deep_worker"


def test_explicit_unconfigured_gateway_is_rejected(tmp_path: Path) -> None:
    service = LightWorkerService(configured(tmp_path), TaskStore(tmp_path / "db.sqlite"), None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not configured for model"):
        service.delegate_task({"objective": "inspect", "workspace": str(tmp_path), "model": "gpt-5.6-sol", "gateway": "cliproxyapi"})


def test_manual_fallback_clones_failed_readonly_task(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    created = service.delegate_task({"objective": "inspect", "workspace": str(tmp_path), "reasoning_effort": "low"})
    store.update_status(created["task_id"], "failed", error="gateway unavailable")
    retried = service.retry_fallback(created["task_id"])
    task = service.task(retried["task_id"])
    assert (task["gateway"], task["upstream_model"], task["response_mode"]) == ("cliproxyapi", "deepseek-v4-flash", "translated")
    assert service.task(created["task_id"])["gateway"] == "opencodex"


def test_execute_fallback_is_forbidden(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = TaskStore(cfg.db_path)
    service = LightWorkerService(cfg, store, None)  # type: ignore[arg-type]
    created = service.delegate_task({"objective": "change", "workspace": str(tmp_path), "kind": "execute", "reasoning_effort": "low", "mode": "auto_execute"})
    store.update_status(created["task_id"], "failed", error="gateway unavailable")
    with pytest.raises(PolicyError, match="read-only"):
        service.retry_fallback(created["task_id"])


def test_new_toml_parses_protocol_modes(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('''[runner]\ndefault_gateway="opencodex"\n[gateways.opencodex]\nbase_url="http://127.0.0.1:10100/v1"\nresponse_mode="native"\n[gateways.cliproxyapi]\nbase_url="http://127.0.0.1:8317/v1"\nresponse_mode="translated"\napi_key_env="CLIPROXYAPI_CLIENT_KEY"\n[model_routes."deepseek/deepseek-v4-flash"]\nprimary="opencodex"\nfallback=["cliproxyapi"]\n[model_routes."deepseek/deepseek-v4-flash".upstream_models]\ncliproxyapi="deepseek-v4-flash"\n''', encoding="utf-8")
    cfg = load_config(home=tmp_path / "state", config_path=path)
    assert cfg.gateways["cliproxyapi"].api_key_env == "CLIPROXYAPI_CLIENT_KEY"


def test_isolated_init_values_round_trip_into_gateway_registry(tmp_path: Path) -> None:
    cfg = Config(
        home=tmp_path / "state",
        codex_ignore_user_config=True,
        codex_base_url="http://127.0.0.1:19999/v1",
        codex_model_catalog=str(tmp_path / "catalog.json"),
        default_gateway="opencodex",
    )
    cfg.gateways["opencodex"] = GatewayConfig(
        "opencodex", cfg.codex_base_url, "native", model_catalog=cfg.codex_model_catalog
    )
    write_default_config(cfg)
    loaded = load_config(home=cfg.home)
    assert loaded.gateways["opencodex"].base_url == "http://127.0.0.1:19999/v1"
    assert loaded.gateways["opencodex"].model_catalog == str((tmp_path / "catalog.json").resolve())


class CaptureWorker:
    def __init__(self) -> None:
        self.spec = None

    def run(self, task_id, spec, cwd, on_event, on_pid, is_cancelled):
        self.spec = spec
        on_pid(1234)
        return RunResult(status="completed", result={"status": "completed", "summary": "ok", "evidence": [], "changed_files": [], "tests": [], "risks": [], "followups": []})


def test_legacy_queued_task_is_migrated_before_execution(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    cfg.poll_interval_seconds = 0.01
    store = TaskStore(cfg.db_path)
    task_id = store.create_task(TaskSpec(objective="old task", workspace=str(tmp_path), model="deepseek/deepseek-v4-flash", reasoning_effort="low"))
    worker = CaptureWorker()
    scheduler = Scheduler(cfg, store, worker=worker)
    assert scheduler.run_until_idle(timeout=5)
    assert worker.spec.gateway == "opencodex"
    assert store.get_spec(task_id).gateway == "opencodex"
    assert any(event["event_type"] == "task.route_migrated" for event in store.events(task_id))
