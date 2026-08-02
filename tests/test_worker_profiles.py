
from pathlib import Path

import pytest

from lightworker.config import Config, GatewayConfig, load_config
from lightworker.models import TaskSpec, public_task


def test_builtin_worker_profiles_resolve_expected_roles(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)

    planner = cfg.resolve_profile("planner", kind="plan")
    fast = cfg.resolve_profile("fast_worker", kind="explore")
    deep = cfg.resolve_profile("deep_worker", kind="execute")
    reviewer = cfg.resolve_profile("reviewer", kind="review")

    assert (planner.model, planner.reasoning_effort) == ("gpt-5.6-sol", "high")
    assert (fast.model, fast.reasoning_effort) == ("deepseek/deepseek-v4-flash", "low")
    assert (deep.model, deep.reasoning_effort) == ("gpt-5.6-luna", "max")
    assert (reviewer.model, reviewer.reasoning_effort) == ("gpt-5.6-terra", "high")


def test_resolve_profile_retains_legacy_no_profile_model_routing(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)

    selected = cfg.resolve_profile(None, reasoning_effort="low")

    assert selected.profile is None
    assert selected.model == "deepseek/deepseek-v4-flash"
    assert selected.reasoning_effort == "low"


def test_profile_allows_explicit_overrides_and_enforces_kind(tmp_path: Path) -> None:
    cfg = Config(home=tmp_path)
    cfg.gateways["local"] = GatewayConfig("local", "http://127.0.0.1:19999/v1")
    selected = cfg.resolve_profile(
        "fast_worker",
        kind="explore",
        model="gpt-5.6-terra",
        gateway="local",
        reasoning_effort="medium",
    )

    assert (selected.model, selected.gateway, selected.reasoning_effort) == (
        "gpt-5.6-terra", "local", "medium"
    )
    with pytest.raises(ValueError, match="does not allow"):
        cfg.resolve_profile("planner", kind="execute")
    with pytest.raises(ValueError, match="Unknown worker profile"):
        cfg.resolve_profile("missing")


def test_worker_profiles_load_from_toml_and_public_task_exposes_audit_request_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """[worker_profiles.docs]
description = "Read documentation only."
model = "gpt-5.6-terra"
reasoning_effort = "medium"
allowed_kinds = ["explore"]
""",
        encoding="utf-8",
    )
    cfg = load_config(home=tmp_path / "state", config_path=config_path)
    assert cfg.resolve_profile("docs", kind="explore").model == "gpt-5.6-terra"

    spec = TaskSpec(
        objective="inspect",
        workspace=str(tmp_path),
        profile="docs",
        requested_gateway="opencodex",
        requested_reasoning_effort="medium",
    )
    task = public_task({"id": "task-1", "spec_json": __import__("json").dumps(spec.to_dict())})
    assert task["profile"] == "docs"
    assert task["requested_gateway"] == "opencodex"
    assert task["requested_reasoning_effort"] == "medium"


def test_invalid_profile_configuration_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.toml"
    config_path.write_text(
        """[worker_profiles.bad]
description = "Bad route"
model = "gpt-5.6-terra"
reasoning_effort = "unsupported"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unsupported reasoning effort"):
        load_config(home=tmp_path / "other", config_path=config_path)


def test_legacy_model_allowlist_does_not_fail_before_a_profile_is_requested(tmp_path: Path) -> None:
    config_path = tmp_path / "legacy.toml"
    config_path.write_text(
        """[policy]
allowed_models = ["gpt-5.6-sol"]
""",
        encoding="utf-8",
    )

    cfg = load_config(home=tmp_path / "state", config_path=config_path)

    assert cfg.allowed_models == ("gpt-5.6-sol",)
    assert cfg.worker_profiles["deep_worker"].model == "gpt-5.6-luna"
