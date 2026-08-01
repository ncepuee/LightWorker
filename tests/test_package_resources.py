from __future__ import annotations

import json
from pathlib import Path

import lightworker


def test_runtime_resources_are_packaged() -> None:
    root = Path(lightworker.__file__).resolve().parent
    resources = [
        root / "web" / "index.html",
        root / "web" / "app.js",
        root / "web" / "styles.css",
        root / "web" / "logo.svg",
        root / "web" / "favicon.svg",
        root / "web" / "lightworker-app-icon.png",
        root / "schemas" / "plan.schema.json",
        root / "schemas" / "result.schema.json",
    ]
    assert all(path.is_file() for path in resources)
    for path in resources[-2:]:
        assert json.loads(path.read_text(encoding="utf-8"))["type"] == "object"
