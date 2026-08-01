from lightworker.worker import is_generic_result, parse_json_candidate, redact_value


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
