
from lightworker.models import TaskSpec
from lightworker.config import Config, GatewayConfig
from lightworker.worker import build_prompt, build_worker_environment, extract_observed_model, extract_usage, gateway_codex_args, is_generic_result, normalize_worker_result, parse_json_candidate, prompt_metadata, redact_text, redact_value


def test_parses_fenced_json() -> None:
    assert parse_json_candidate('before\n```json\n{"summary":"ok","tasks":[]}\n```') == {
        "summary": "ok",
        "tasks": [],
    }


def test_generic_result_requires_protocol_fields() -> None:
    assert not is_generic_result({"summary": "ok"})
    assert is_generic_result(
        {
            "status": "completed",
            "summary": "ok",
            "evidence": [],
            "changed_files": [],
            "tests": [],
            "risks": [],
            "followups": [],
        }
    )


def test_normalize_worker_result_fills_missing_lists_and_preserves_unknown_json() -> None:
    result = normalize_worker_result(
        {
            "status": "completed",
            "summary": "ok",
            "provider_trace": {"request_id": "synthetic"},
        }
    )
    assert result["schema_valid"] is True
    assert result["schema_status"] == "normalized"
    assert result["evidence"] == []
    assert result["changed_files"] == []
    assert result["tests"] == []
    assert result["risks"] == []
    assert result["followups"] == []
    assert result["raw_json"] == {"provider_trace": {"request_id": "synthetic"}}


def test_normalize_worker_result_rejects_invalid_status_or_nested_schema() -> None:
    invalid_status = normalize_worker_result({"status": "ok", "summary": "bad"})
    assert invalid_status["status"] == "failed"
    assert invalid_status["schema_valid"] is False
    assert invalid_status["schema_status"] == "invalid"
    assert invalid_status["raw_json"]["status"] == "ok"

    invalid_evidence = normalize_worker_result(
        {
            "status": "completed",
            "summary": "bad evidence",
            "evidence": [{"file": "a.py", "line": "1", "finding": "wrong type"}],
            "changed_files": [],
            "tests": [],
            "risks": [],
            "followups": [],
        }
    )
    assert invalid_evidence["schema_status"] == "invalid"
    assert invalid_evidence["raw_json"]["evidence"][0]["line"] == "1"


def test_normalize_worker_result_redacts_unknown_json_before_audit_storage() -> None:
    result = normalize_worker_result(
        {
            "status": "completed",
            "summary": "ok",
            "api_key": "synthetic-secret",
        }
    )
    assert result["schema_status"] == "normalized"
    assert result["raw_json"]["api_key"] == "<REDACTED>"


def test_prompt_prefix_is_stable_and_usage_is_groupable(tmp_path) -> None:
    first = TaskSpec(objective="one", workspace=str(tmp_path), kind="explore", cache_cohort="opencodex:native:model")
    second = TaskSpec(objective="two", workspace=str(tmp_path), kind="explore", cache_cohort="opencodex:native:model")
    assert build_prompt(first).split("Task-specific context:")[0] == build_prompt(second).split("Task-specific context:")[0]
    usage = extract_usage({"type": "turn.completed", "usage": {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 80}}})
    assert usage and usage["cache_hit_rate"] == 0.8


def test_observed_model_requires_upstream_event_evidence() -> None:
    event = {"type": "response.completed", "response": {"model": "deepseek-v4-flash"}}
    assert extract_observed_model(event) == "deepseek-v4-flash"
    assert extract_observed_model({"type": "turn.completed", "requested_model": "gpt-5.6-sol"}) is None


def test_prompt_metadata_exposes_context_pack_audit_fields(tmp_path) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    spec = TaskSpec(
        objective="inspect",
        workspace=str(tmp_path),
        context_pack_name="project",
        context_pack_hash="pack-sha",
        metadata={"context_pack_bytes": 123},
    )
    metadata = prompt_metadata(spec, build_prompt(spec), schema)
    assert (metadata["context_pack_name"], metadata["context_pack_sha256"], metadata["context_pack_bytes"]) == ("project", "pack-sha", 123)


def test_structured_redaction_covers_compound_credential_fields() -> None:
    value = {"access_token": "synthetic", "nested": {"client_secret": "synthetic", "private-key": "synthetic"}, "model": "safe"}
    assert redact_value(value) == {"access_token": "<REDACTED>", "nested": {"client_secret": "<REDACTED>", "private-key": "<REDACTED>"}, "model": "safe"}


def test_raw_text_redaction_covers_quoted_json_credentials() -> None:
    safe = redact_text('{"access_token":"synthetic-value","client_secret":"another-value"')
    assert "synthetic-value" not in safe
    assert "another-value" not in safe
    assert safe.count("<REDACTED>") == 2


def test_raw_text_redaction_covers_local_gateway_key_prefixes() -> None:
    safe = redact_text("cpa-local-syntheticCredential123 ark-1234567890-abcdefghijkl")
    assert "syntheticCredential123" not in safe
    assert "abcdefghijkl" not in safe
    assert safe.count("<REDACTED>") == 2


def test_legacy_environment_preserves_existing_openai_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-legacy-key")
    cfg = Config(home=tmp_path)
    environment = build_worker_environment(cfg, cfg.gateway_config("legacy"))
    assert environment["OPENAI_API_KEY"] == "synthetic-legacy-key"


def test_registered_gateway_environment_filters_unselected_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UNRELATED_ACCESS_TOKEN", "synthetic-unrelated")
    cfg = Config(home=tmp_path, default_gateway="opencodex")
    gateway = GatewayConfig("opencodex", "http://127.0.0.1:10100/v1")
    cfg.gateways["opencodex"] = gateway
    assert "UNRELATED_ACCESS_TOKEN" not in build_worker_environment(cfg, gateway)


def test_authenticated_gateway_uses_custom_codex_provider_without_secret_in_args(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLIPROXYAPI_CLIENT_KEY", "synthetic-client-key")
    cfg = Config(home=tmp_path, default_gateway="cliproxyapi")
    gateway = GatewayConfig(
        "cliproxyapi",
        "http://127.0.0.1:8317/v1",
        "translated",
        api_key_env="CLIPROXYAPI_CLIENT_KEY",
    )
    cfg.gateways["cliproxyapi"] = gateway
    args = gateway_codex_args(gateway)
    environment = build_worker_environment(cfg, gateway)
    assert 'model_provider="cliproxyapi"' in args
    assert 'model_providers.cliproxyapi.env_key="CLIPROXYAPI_CLIENT_KEY"' in args
    assert 'model_providers.cliproxyapi.supports_websockets=false' in args
    assert "synthetic-client-key" not in str(args)
    assert environment["CLIPROXYAPI_CLIENT_KEY"] == "synthetic-client-key"
