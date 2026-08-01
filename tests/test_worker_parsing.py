import io
import json

from lightworker.config import Config
from lightworker.models import TaskSpec
from lightworker.worker import (
    CodexWorker,
    PROMPT_PROTOCOL_VERSION,
    build_prompt,
    build_stable_prefix,
    extract_usage,
    is_generic_result,
    parse_json_candidate,
    prompt_metadata,
    redact_value,
)


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


def test_generic_result_rejects_wrong_nested_types_and_extra_fields() -> None:
    valid = {
        "status": "completed",
        "summary": "ok",
        "evidence": [{"file": "a.py", "line": 1, "finding": "checked"}],
        "changed_files": ["a.py"],
        "tests": [{"command": "pytest", "status": "passed", "summary": "ok"}],
        "risks": [],
        "followups": [],
    }
    assert is_generic_result(valid)
    assert not is_generic_result({**valid, "status": "unknown"})
    assert not is_generic_result({**valid, "changed_files": [1]})
    assert not is_generic_result({**valid, "evidence": [{"file": "a.py"}]})
    assert not is_generic_result({**valid, "extra": True})


def test_structured_redaction_preserves_json_shape() -> None:
    value = {
        "type": "event",
        "payload": {"token": "secret-value", "items": ["Bearer abc.def.ghi", 3]},
    }
    redacted = redact_value(value)
    assert redacted["type"] == "event"
    assert redacted["payload"]["token"] == "<REDACTED>"
    assert redacted["payload"]["items"] == ["Bearer <REDACTED>", 3]


def test_prompt_v2_keeps_stable_contract_before_dynamic_context(tmp_path) -> None:
    spec = TaskSpec(
        objective="Inspect  spacing\r\nwithout collapsing it.  ",
        workspace="original",
        kind="explore",
        allowed_paths=["b.py ", "a.py", "a.py"],
        success_criteria=[" report  evidence  "],
        metadata={"routing_policy": {"z": 1, "a": 2}},
    )
    prompt = build_prompt(spec, execution_workspace=tmp_path)
    assert prompt.index(PROMPT_PROTOCOL_VERSION) < prompt.index("Objective:")
    assert str(tmp_path) in prompt
    assert "original" not in prompt
    assert prompt.index("- a.py") < prompt.index("- b.py")
    assert "Inspect  spacing\nwithout collapsing it." in prompt
    assert '{"a":2,"z":1}' in prompt


def test_prompt_fingerprints_separate_stable_prefix_from_task_content(tmp_path) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    first = TaskSpec(objective="one", workspace="repo", kind="execute")
    second = TaskSpec(objective="two", workspace="repo", kind="execute")
    first_prompt = build_prompt(first, execution_workspace=tmp_path / "a")
    second_prompt = build_prompt(second, execution_workspace=tmp_path / "b")
    first_meta = prompt_metadata(first, first_prompt, schema, "http://localhost/v1")
    second_meta = prompt_metadata(second, second_prompt, schema, "http://localhost/v1")
    assert build_stable_prefix(first) == build_stable_prefix(second)
    assert first_meta["stable_prefix_sha256"] == second_meta["stable_prefix_sha256"]
    assert first_meta["cache_cohort_sha256"] == second_meta["cache_cohort_sha256"]
    assert first_meta["prompt_sha256"] != second_meta["prompt_sha256"]
    assert "localhost" not in str(first_meta)
    assert "one" not in str(first_meta)


def test_extract_usage_normalizes_supported_cache_fields() -> None:
    assert extract_usage(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 900},
                "output_tokens": 50,
                "total_tokens": 1050,
            },
        }
    ) == {
        "input_tokens": 1000,
        "cached_input_tokens": 900,
        "uncached_input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 1050,
        "cache_hit_rate": 0.9,
    }
    assert extract_usage(
        {"usage": {"prompt_cache_hit_tokens": 9984, "prompt_cache_miss_tokens": 105}}
    ) == {
        "input_tokens": 10089,
        "cached_input_tokens": 9984,
        "uncached_input_tokens": 105,
        "cache_hit_rate": 0.989593,
    }


def test_extract_usage_rejects_invalid_token_values() -> None:
    assert extract_usage({"usage": {"input_tokens": True, "output_tokens": -1}}) is None
    assert extract_usage({"item": {"usage": {"input_tokens": 10}}}) is None
    inconsistent = extract_usage({"usage": {"input_tokens": 5, "cached_input_tokens": 8}})
    assert inconsistent == {"input_tokens": 5, "cached_input_tokens": 8}


def test_extract_usage_prefers_explicit_cache_hit_and_miss_totals() -> None:
    usage = extract_usage(
        {
            "usage": {
                "input_tokens": 999,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 20,
            }
        }
    )
    assert usage["input_tokens"] == 999
    assert usage["uncached_input_tokens"] == 20
    assert usage["cache_hit_rate"] == 0.8


class _CaptureInput(io.StringIO):
    def close(self) -> None:
        pass


class _CompletedProcess:
    def __init__(self) -> None:
        self.pid = 4321
        self.stdin = _CaptureInput()
        self.stdout = io.StringIO(
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 10,
                        "input_tokens_details": {"cached_tokens": 8},
                        "output_tokens": 2,
                    },
                    "item": [],
                }
            )
            + "\n"
        )
        self.stderr = io.StringIO("")

    def poll(self) -> int:
        return 0

    def wait(self, timeout=None) -> int:
        return 0


def test_worker_run_uses_execution_workspace_and_emits_cache_events(tmp_path, monkeypatch) -> None:
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()
    worker = CodexWorker(cfg)
    process = _CompletedProcess()
    monkeypatch.setattr(worker, "_command_prefix", lambda: ["codex"])
    monkeypatch.setattr("lightworker.worker.subprocess.Popen", lambda *_args, **_kwargs: process)
    events = []
    execution_workspace = tmp_path / "isolated-worktree"

    worker.run(
        "task-1",
        TaskSpec(objective="inspect", workspace=str(tmp_path / "source"), kind="review"),
        execution_workspace,
        lambda event_type, payload: events.append((event_type, payload)),
        lambda _pid: None,
        lambda: False,
    )

    written_prompt = process.stdin.getvalue()
    assert str(execution_workspace.resolve()) in written_prompt
    assert str((tmp_path / "source").resolve()) not in written_prompt
    prompt_event = next(payload for event_type, payload in events if event_type == "worker.prompt")
    usage_event = next(payload for event_type, payload in events if event_type == "worker.usage")
    assert prompt_event["prompt_sha256"]
    assert usage_event["cached_input_tokens"] == 8
    assert usage_event["cache_hit_rate"] == 0.8
    assert usage_event["source_event_type"] == "turn.completed"
    assert "inspect" not in str(prompt_event)


def test_worker_terminates_child_when_pid_callback_fails(tmp_path, monkeypatch) -> None:
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()
    worker = CodexWorker(cfg)
    process = _CompletedProcess()
    terminated = []
    monkeypatch.setattr(worker, "_command_prefix", lambda: ["codex"])
    monkeypatch.setattr("lightworker.worker.subprocess.Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr("lightworker.worker._terminate_process_tree", terminated.append)

    try:
        worker.run(
            "task-2",
            TaskSpec(objective="inspect", workspace=str(tmp_path), kind="explore"),
            tmp_path,
            lambda _event_type, _payload: None,
            lambda _pid: (_ for _ in ()).throw(RuntimeError("store unavailable")),
            lambda: False,
        )
    except RuntimeError as exc:
        assert str(exc) == "store unavailable"
    else:
        raise AssertionError("expected pid callback failure")

    assert terminated == [process]
