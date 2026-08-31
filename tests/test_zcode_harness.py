from pathlib import Path

import pytest

from lightworker.config import Config, load_config
from lightworker.models import TaskSpec
from lightworker.worker import CodexWorker, ZCodeWorker, build_worker, _zcode_environment


def make_config(tmp_path: Path, **runner) -> Config:
    config_path = tmp_path / "config.toml"
    lines = [f'{key} = {value!r}' if isinstance(value, str) else f'{key} = {value}' for key, value in runner.items()]
    if lines:
        config_path.write_text("[runner]\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return load_config(home=tmp_path, config_path=config_path)


def make_spec(**overrides) -> TaskSpec:
    defaults = {"objective": "inspect", "workspace": str(Path("."))}
    defaults.update(overrides)
    return TaskSpec(**defaults)


def test_factory_selects_harness(tmp_path):
    cfg = make_config(tmp_path)
    assert isinstance(build_worker(cfg, make_spec(harness="codex")), CodexWorker)
    assert isinstance(build_worker(cfg, make_spec(harness="zcode")), ZCodeWorker)


def test_factory_falls_back_to_configured_harness(tmp_path):
    cfg = make_config(tmp_path, worker_harness="zcode")
    assert isinstance(build_worker(cfg, make_spec(harness="codex", )), CodexWorker)
    assert isinstance(build_worker(cfg, make_spec(harness="unknown")), ZCodeWorker)


def test_unknown_spec_harness_falls_back_to_codex(tmp_path):
    cfg = make_config(tmp_path)
    assert isinstance(build_worker(cfg, make_spec(harness="claude")), CodexWorker)


def test_zcode_mode_mapping_is_never_yolo(tmp_path):
    worker = ZCodeWorker(make_config(tmp_path))
    assert worker._mode_for(make_spec(sandbox="read-only", kind="explore")) == "plan"
    assert worker._mode_for(make_spec(sandbox="read-only", kind="review")) == "plan"
    assert worker._mode_for(make_spec(sandbox="workspace-write", kind="explore")) == "plan"
    assert worker._mode_for(make_spec(sandbox="workspace-write", kind="execute")) == "edit"


def test_zcode_command_prefix_uses_cli_path_with_node(tmp_path):
    cli = tmp_path / "zcode.cjs"
    cli.write_text("// stub", encoding="utf-8")
    cfg = make_config(tmp_path, zcode_cli_path=str(cli))
    worker = ZCodeWorker(cfg)
    prefix = worker._command_prefix()
    assert prefix is not None
    assert Path(prefix[0]).name.lower().startswith("node")
    assert prefix[-1] == str(cli)


def test_zcode_command_prefix_missing_cli_path(tmp_path):
    cfg = make_config(tmp_path, zcode_cli_path=str(tmp_path / "missing.cjs"))
    assert ZCodeWorker(cfg)._command_prefix() is None


def test_zcode_environment_filters_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTWORKER_TEST_MARKER", "secret")
    monkeypatch.setenv("PATH", "keep-me")
    cfg = make_config(tmp_path)
    env = _zcode_environment(cfg)
    assert "LIGHTWORKER_TEST_MARKER" not in env
    assert env["PATH"] == "keep-me"


def test_config_rejects_unknown_harness(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[runner]\nworker_harness = "claude"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="worker_harness"):
        load_config(home=tmp_path, config_path=config_path)


def test_config_accepts_zcode_harness(tmp_path):
    cfg = make_config(tmp_path, worker_harness="zcode", zcode_command="zcode-dev")
    assert cfg.worker_harness == "zcode"
    assert cfg.zcode_command == "zcode-dev"
