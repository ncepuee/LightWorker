"""Regression tests for v0.7.1 ZCode routing fixes.

Covers: batch harness preservation, planner children carrying harness,
gateway-free ZCode delegation, plan schema harness enum, example TOML
escaping, and secret-free ZCode provider reporting in doctor.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from lightworker.config import Config, load_config
from lightworker.models import KNOWN_HARNESSES
from lightworker.policy import PolicyError
from lightworker.scheduler import Scheduler
from lightworker.service import LightWorkerService
from lightworker.store import TaskStore

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_service(tmp_path: Path, **runner) -> tuple[LightWorkerService, TaskStore, Scheduler]:
    config_path = tmp_path / "config.toml"
    lines = [f"{key} = {value!r}" if isinstance(value, str) else f"{key} = {value}" for key, value in runner.items()]
    if lines:
        config_path.write_text("[runner]\n" + "\n".join(lines) + "\n", encoding="utf-8")
    cfg = load_config(home=tmp_path / "state", config_path=config_path if lines else None)
    cfg.ensure_dirs()
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    return LightWorkerService(cfg, store, scheduler), store, scheduler


def batch_result_specs(store: TaskStore, root_id: str) -> dict[str, dict]:
    specs = {}
    for row in store.list_tasks(root_id=root_id):
        public = {**row, **json.loads(row["spec_json"] or "{}")}
        specs[public.get("name") or row["id"]] = public
    return specs


# ---------------------------------------------------------------------------
# 1. delegate_batch must preserve the requested harness
# ---------------------------------------------------------------------------


def test_delegate_batch_preserves_zcode_harness(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)
    result = service.delegate_batch([
        {
            "id": "scan",
            "kind": "explore",
            "harness": "zcode",
            "objective": "scan module layout",
            "workspace": str(tmp_path),
        },
        {
            "id": "read",
            "kind": "review",
            "harness": "codex",
            "objective": "review findings",
            "workspace": str(tmp_path),
            "dependencies": ["scan"],
        },
    ])
    specs = batch_result_specs(store, result["root_id"])
    assert specs["scan"]["harness"] == "zcode"
    assert specs["scan"]["gateway"] is None
    assert specs["scan"]["upstream_model"] is None
    assert specs["scan"]["provider"] == "zcode"
    assert specs["read"]["harness"] == "codex"


def test_delegate_batch_defaults_harness_to_config(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path, worker_harness="zcode")
    result = service.delegate_batch([
        {"id": "solo", "kind": "explore", "objective": "look around", "workspace": str(tmp_path)},
    ])
    specs = batch_result_specs(store, result["root_id"])
    assert specs["solo"]["harness"] == "zcode"
    assert specs["solo"]["model"] == "zcode-managed"


def test_delegate_batch_rejects_zcode_native_subagent(tmp_path: Path) -> None:
    service, _store, _ = make_service(tmp_path)
    with pytest.raises(PolicyError, match="native_subagent"):
        service.delegate_batch([
            {
                "id": "bad",
                "kind": "explore",
                "harness": "zcode",
                "execution_channel": "native_subagent",
                "objective": "impossible combination",
                "workspace": str(tmp_path),
            },
        ])


def test_delegate_batch_rejects_zcode_gateway(tmp_path: Path) -> None:
    service, _store, _ = make_service(tmp_path)
    with pytest.raises(PolicyError, match="gateway"):
        service.delegate_batch([
            {
                "id": "bad",
                "kind": "explore",
                "harness": "zcode",
                "gateway": "opencodex",
                "objective": "impossible combination",
                "workspace": str(tmp_path),
            },
        ])


def test_delegate_batch_unknown_harness_rejected(tmp_path: Path) -> None:
    service, _store, _ = make_service(tmp_path)
    with pytest.raises(PolicyError, match="Unknown harness"):
        service.delegate_batch([
            {"id": "bad", "kind": "explore", "harness": "claude", "objective": "x", "workspace": str(tmp_path)},
        ])


# ---------------------------------------------------------------------------
# 2. delegate_task must not require gateways for ZCode
# ---------------------------------------------------------------------------


def test_delegate_task_zcode_queues_without_gateways(tmp_path: Path) -> None:
    service, store, _ = make_service(tmp_path)
    result = service.delegate_task({
        "kind": "explore",
        "harness": "zcode",
        "objective": "summarize project structure",
        "workspace": str(tmp_path),
        "required_capabilities": ["web_search"],
    })
    row = store.get_task(result["task_id"])
    assert row["status"] == "queued"
    spec = json.loads(row["spec_json"])
    assert spec["harness"] == "zcode"
    assert spec["model"] == "zcode-managed"
    assert spec["gateway"] is None
    assert spec["upstream_model"] is None
    assert spec["route_capabilities"] == ["web_search"]


def test_delegate_task_zcode_rejects_gateway(tmp_path: Path) -> None:
    service, _store, _ = make_service(tmp_path)
    with pytest.raises(PolicyError, match="gateway"):
        service.delegate_task({
            "kind": "explore",
            "harness": "zcode",
            "gateway": "opencodex",
            "objective": "x",
            "workspace": str(tmp_path),
        })


def test_delegate_task_zcode_queues_with_gateways_configured(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[runner]\n"
        'default_gateway = "opencodex"\n'
        "\n[gateways.opencodex]\n"
        'base_url = "http://127.0.0.1:10100/v1"\n'
        'response_mode = "native"\n'
        "enabled = true\n",
        encoding="utf-8",
    )
    cfg = load_config(home=tmp_path / "state", config_path=config_path)
    cfg.ensure_dirs()
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    service = LightWorkerService(cfg, store, scheduler)
    result = service.delegate_task({
        "kind": "explore",
        "harness": "zcode",
        "objective": "work even with gateways configured",
        "workspace": str(tmp_path),
    })
    spec = json.loads(store.get_task(result["task_id"])["spec_json"])
    assert spec["harness"] == "zcode"
    assert spec["gateway"] is None
    assert spec["model"] == "zcode-managed"


# ---------------------------------------------------------------------------
# 3. Planner children must be able to run on ZCode
# ---------------------------------------------------------------------------


def plan_payload(harness: str | None) -> dict:
    task = {
        "id": "inspect",
        "kind": "explore",
        "objective": "inspect files",
        "dependencies": [],
        "reasoning_effort": "medium",
        "timeout_seconds": 60,
        "allowed_paths": [],
        "prohibited_actions": [],
        "success_criteria": ["report findings"],
    }
    if harness is not None:
        task["harness"] = harness
    return {"summary": "test plan", "tasks": [task]}


def test_expand_plan_zcode_child_keeps_harness(tmp_path: Path) -> None:
    from lightworker.models import TaskSpec

    cfg = Config(home=tmp_path / "state")
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    planner_spec = TaskSpec(objective="plan", workspace=str(tmp_path), kind="plan", model="gpt-5.6-sol")
    planner_id = store.create_task(planner_spec)
    child_ids = scheduler._expand_plan(planner_id, planner_spec, plan_payload("zcode"))
    row = store.get_task(child_ids[0])
    spec = json.loads(row["spec_json"])
    assert spec["harness"] == "zcode"
    assert spec["gateway"] is None
    assert spec["model"] == "zcode-managed"
    assert row["status"] == "queued"


def test_expand_plan_defaults_child_harness_to_config(tmp_path: Path) -> None:
    from lightworker.models import TaskSpec

    config_path = tmp_path / "config.toml"
    config_path.write_text('[runner]\nworker_harness = "zcode"\n', encoding="utf-8")
    cfg = load_config(home=tmp_path / "state", config_path=config_path)
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    planner_spec = TaskSpec(objective="plan", workspace=str(tmp_path), kind="plan", model="gpt-5.6-sol")
    planner_id = store.create_task(planner_spec)
    child_ids = scheduler._expand_plan(planner_id, planner_spec, plan_payload(None))
    spec = json.loads(store.get_task(child_ids[0])["spec_json"])
    assert spec["harness"] == "zcode"


def test_expand_plan_rejects_unknown_child_harness(tmp_path: Path) -> None:
    from lightworker.models import TaskSpec

    cfg = Config(home=tmp_path / "state")
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    planner_spec = TaskSpec(objective="plan", workspace=str(tmp_path), kind="plan", model="gpt-5.6-sol")
    planner_id = store.create_task(planner_spec)
    with pytest.raises(PolicyError, match="unknown harness"):
        scheduler._expand_plan(planner_id, planner_spec, plan_payload("claude"))


def test_expand_plan_rejects_zcode_native_subagent_child(tmp_path: Path) -> None:
    from lightworker.models import TaskSpec

    cfg = Config(home=tmp_path / "state")
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    planner_spec = TaskSpec(objective="plan", workspace=str(tmp_path), kind="plan", model="gpt-5.6-sol")
    planner_id = store.create_task(planner_spec)
    plan = plan_payload("zcode")
    plan["tasks"][0]["execution_channel"] = "native_subagent"
    with pytest.raises(PolicyError, match="native_subagent"):
        scheduler._expand_plan(planner_id, planner_spec, plan)


# ---------------------------------------------------------------------------
# 4. Schema and config example
# ---------------------------------------------------------------------------


def test_plan_schema_declares_harness_enum() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "plan.schema.json").read_text(encoding="utf-8"))
    harness = schema["properties"]["tasks"]["items"]["properties"]["harness"]
    assert sorted(harness["enum"]) == sorted(KNOWN_HARNESSES)


def test_config_example_toml_parses_with_windows_paths() -> None:
    data = tomllib.loads((REPO_ROOT / "config.example.toml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)


@pytest.mark.parametrize("line", [
    "zcode_cli_path = 'D:\\ZCode\\resources\\glm\\zcode.cjs'",
    'zcode_cli_path = "D:\\\\ZCode\\\\resources\\\\glm\\\\zcode.cjs"',
])
def test_zcode_cli_path_toml_forms_parse(line: str) -> None:
    data = tomllib.loads(f"[runner]\n{line}\n")
    assert data["runner"]["zcode_cli_path"] == "D:\\ZCode\\resources\\glm\\zcode.cjs"


# ---------------------------------------------------------------------------
# 5. Doctor reports provider facts without leaking key material
# ---------------------------------------------------------------------------


def test_doctor_reports_zcode_provider_without_secrets(tmp_path: Path, monkeypatch) -> None:
    zcode_config = tmp_path / "zcode-config.json"
    zcode_config.write_text(json.dumps({
        "provider": {
            "zai": {
                "kind": "anthropic",
                "name": "BigModel GLM Coding Plan",
                "options": {"apiKeyRequired": True, "baseURL": "https://open.bigmodel.cn/api/anthropic", "apiKey": "sk-secret-value-should-never-leak"},
                "models": {"glm-5.3": {"name": "GLM-5.3"}, "glm-5.3-flash": {"name": "GLM-5.3-Flash"}},
            },
        },
        "model": {"main": "zai/glm-5.3", "lite": "zai/glm-5.3-flash"},
    }), encoding="utf-8")
    monkeypatch.setenv("ZCODE_CONFIG_PATH", str(zcode_config))
    service, _store, _scheduler = make_service(tmp_path)
    doctor = service.doctor()
    provider = doctor["zcode_provider"]
    assert provider["main_model"] == "zai/glm-5.3"
    assert provider["provider"]["base_url"] == "https://open.bigmodel.cn/api/anthropic"
    assert provider["provider"]["api_key_configured"] is True
    serialized = json.dumps(doctor)
    assert "sk-secret-value-should-never-leak" not in serialized


def test_doctor_zcode_provider_absent_when_no_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZCODE_CONFIG_PATH", str(tmp_path / "missing.json"))
    service, _store, _scheduler = make_service(tmp_path)
    assert service.doctor()["zcode_provider"] is None


# ---------------------------------------------------------------------------
# 6. Scheduler must not migrate ZCode tasks onto a gateway
# ---------------------------------------------------------------------------


class RecordingWorker:
    def __init__(self) -> None:
        self.specs: list = []

    def run(self, task_id, spec, cwd, on_event, on_pid, is_cancelled):
        self.specs.append(spec)
        on_pid(4321)
        on_event("turn.started", {"type": "turn.started"})
        return RunResult(
            status="completed",
            result={"status": "completed", "summary": "done", "evidence": [], "changed_files": [], "tests": [], "risks": [], "followups": []},
        )


def test_scheduler_preserves_zcode_route_fields_at_dispatch(tmp_path: Path) -> None:
    from lightworker.models import RunResult

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[runner]\n"
        'default_gateway = "opencodex"\n'
        "\n[gateways.opencodex]\n"
        'base_url = "http://127.0.0.1:10100/v1"\n'
        'response_mode = "native"\n'
        "enabled = true\n",
        encoding="utf-8",
    )
    cfg = load_config(home=tmp_path / "state", config_path=config_path)
    cfg.ensure_dirs()
    store = TaskStore(cfg.db_path)
    worker = RecordingWorker()
    scheduler = Scheduler(cfg, store, worker=worker)
    service = LightWorkerService(cfg, store, scheduler)
    result = service.delegate_task({
        "kind": "explore",
        "harness": "zcode",
        "objective": "route fields must survive dispatch",
        "workspace": str(tmp_path),
    })
    assert scheduler.run_until_idle(timeout=5)
    spec = json.loads(store.get_task(result["task_id"])["spec_json"])
    assert spec["gateway"] is None
    assert spec["provider"] == "zcode"
    assert spec["model"] == "zcode-managed"
    assert worker.specs[0].harness == "zcode"
