from pathlib import Path

import pytest

from lightworker.config import load_config


def test_invalid_scheduler_limits_are_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[runner]\nmax_concurrency = 0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="max_concurrency"):
        load_config(home=tmp_path / "state", config_path=config_path)


def test_invalid_poll_interval_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[runner]\npoll_interval_seconds = -1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="poll_interval_seconds"):
        load_config(home=tmp_path / "state", config_path=config_path)
