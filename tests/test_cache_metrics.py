from pathlib import Path
import sqlite3

import pytest

from lightworker.cache import CACHE_WINDOW_MAX_SECONDS
from lightworker.config import Config
from lightworker.models import TaskSpec
from lightworker.service import LightWorkerService
from lightworker.store import TaskStore


def store_for(tmp_path: Path) -> TaskStore:
    config = Config(home=tmp_path / "state")
    config.ensure_dirs()
    return TaskStore(config.db_path)


def task(store: TaskStore, tmp_path: Path, name: str) -> str:
    return store.create_task(TaskSpec(objective=name, workspace=str(tmp_path)))


def usage(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "cache_cohort": "cache_cohort.v2:opencodex:deepseek:worker",
        "cache_cohort_sha256": "cohort-one",
        "gateway": "opencodex",
        "model": "deepseek/deepseek-v4-flash",
        "input_tokens": 100,
        "cached_input_tokens": 80,
        "uncached_input_tokens": 20,
        "cache_hit_rate": 0.8,
        "prompt_protocol": "lightworker.prompt.v4",
    }
    values.update(overrides)
    return values


def test_cache_metrics_classifies_cross_task_cohort_warm_and_weights_tokens(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    first, second = task(store, tmp_path, "one"), task(store, tmp_path, "two")
    store.add_event(first, "worker.usage", usage(input_tokens=100, cached_input_tokens=60, uncached_input_tokens=40))
    store.add_event(first, "worker.usage", usage(input_tokens=50, cached_input_tokens=40, uncached_input_tokens=10))
    store.add_event(second, "worker.usage", usage(input_tokens=200, cached_input_tokens=190, uncached_input_tokens=10))

    metrics = store.cache_metrics(window_seconds=3600)
    assert metrics["overall"]["samples"] == 3
    assert metrics["overall"]["input_tokens"] == 350
    assert metrics["overall"]["cached_input_tokens"] == 290
    assert metrics["overall"]["uncached_input_tokens"] == 60
    assert metrics["overall"]["cache_hit_rate"] == 290 / 350
    assert metrics["cold"]["samples"] == 2
    assert metrics["warm"]["samples"] == 1
    assert metrics["warm"]["cache_hit_rate"] == 0.95
    assert metrics["indeterminate"]["samples"] == 0
    assert metrics["cohorts"][0]["recent_at"]


def test_cache_metrics_marks_incomplete_and_ignores_invalid_or_duplicate_samples(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    first, second = task(store, tmp_path, "one"), task(store, tmp_path, "two")
    store.add_event(first, "worker.usage", usage(cache_cohort_sha256=None))
    store.add_event(first, "worker.usage", usage(input_tokens=0, cached_input_tokens=0, uncached_input_tokens=0))
    store.add_event(first, "worker.usage", usage(input_tokens=10, cached_input_tokens=11, uncached_input_tokens=-1))
    store.add_event(second, "worker.usage", usage(event_id="usage-1"))
    store.add_event(second, "worker.usage", usage(event_id="usage-1"))

    metrics = store.cache_metrics(window_seconds=3600)
    assert metrics["overall"]["samples"] == 2
    assert metrics["indeterminate"]["samples"] == 1
    assert metrics["cold"]["samples"] == 1
    assert metrics["warm"]["samples"] == 0


def test_cache_metrics_filters_materialized_samples_without_reading_events(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    first, second = task(store, tmp_path, "one"), task(store, tmp_path, "two")
    store.add_event(first, "worker.usage", usage(model="deepseek/deepseek-v4-flash", gateway="opencodex"))
    store.add_event(second, "worker.usage", usage(model="deepseek/deepseek-v4-pro", gateway="cliproxy"))

    metrics = store.cache_metrics(model="deepseek/deepseek-v4-flash", gateway="opencodex", window_seconds=3600)
    assert metrics["overall"]["samples"] == 1
    assert metrics["overall"]["input_tokens"] == 100
    assert metrics["cold"]["samples"] == 1


def test_service_reports_warm_target_only_after_required_samples(tmp_path: Path) -> None:
    config = Config(home=tmp_path / "state", cache_min_warm_samples=1, cache_target_hit_rate=0.9)
    store = TaskStore(config.db_path)
    first, second = task(store, tmp_path, "one"), task(store, tmp_path, "two")
    store.add_event(first, "worker.usage", usage(route_verification="verified", input_tokens=100, cached_input_tokens=50, uncached_input_tokens=50))
    store.add_event(second, "worker.usage", usage(route_verification="verified", input_tokens=200, cached_input_tokens=190, uncached_input_tokens=10))
    service = LightWorkerService(config, store, None)  # type: ignore[arg-type]
    metrics = service.cache_metrics(window_seconds=3600)
    assert metrics["warm"]["samples"] == 1
    assert metrics["warm"]["cache_hit_rate"] == 0.95
    assert metrics["warm"]["verified_cache_hit_rate"] == 0.95
    assert metrics["target"]["status"] == "achieved"


def test_legacy_cohort_is_indeterminate_and_cannot_satisfy_target(tmp_path: Path) -> None:
    config = Config(home=tmp_path / "state", cache_min_warm_samples=1, cache_target_hit_rate=0.9)
    store = TaskStore(config.db_path)
    first, second = task(store, tmp_path, "one"), task(store, tmp_path, "two")
    legacy = usage(
        cache_cohort="legacy:deepseek",
        prompt_protocol="lightworker.prompt.v3",
        route_verification="verified",
        cached_input_tokens=99,
        uncached_input_tokens=1,
    )
    store.add_event(first, "worker.usage", legacy)
    store.add_event(second, "worker.usage", legacy)
    metrics = LightWorkerService(config, store, None).cache_metrics(window_seconds=3600)  # type: ignore[arg-type]
    assert metrics["indeterminate"]["samples"] == 2
    assert metrics["warm"]["samples"] == 0
    assert metrics["target"]["status"] == "insufficient_samples"


def test_unverified_warm_samples_cannot_satisfy_verified_target(tmp_path: Path) -> None:
    config = Config(home=tmp_path / "state", cache_min_warm_samples=2, cache_target_hit_rate=0.9)
    store = TaskStore(config.db_path)
    ids = [task(store, tmp_path, str(index)) for index in range(4)]
    store.add_event(ids[0], "worker.usage", usage(route_verification="verified"))
    store.add_event(ids[1], "worker.usage", usage(route_verification="verified", cached_input_tokens=95, uncached_input_tokens=5))
    store.add_event(ids[2], "worker.usage", usage(cached_input_tokens=100, uncached_input_tokens=0))
    store.add_event(ids[3], "worker.usage", usage(cached_input_tokens=100, uncached_input_tokens=0))
    metrics = LightWorkerService(config, store, None).cache_metrics(window_seconds=3600)  # type: ignore[arg-type]
    assert metrics["warm"]["samples"] == 3
    assert metrics["warm"]["verified_samples"] == 1
    assert metrics["target"]["status"] == "unverified_route"
    assert metrics["target"]["remaining_samples"] == 1


def test_target_never_combines_gateways_or_strict_cohorts(tmp_path: Path) -> None:
    config = Config(home=tmp_path / "state", cache_min_warm_samples=2, cache_target_hit_rate=0.9)
    store = TaskStore(config.db_path)
    for gateway, cohort in (("opencodex", "cohort-one"), ("cliproxy", "cohort-two")):
        first, second = task(store, tmp_path, gateway + "-one"), task(store, tmp_path, gateway + "-two")
        sample = usage(
            gateway=gateway,
            cache_cohort=f"cache_cohort.v2:{cohort}",
            cache_cohort_sha256=cohort,
            route_verification="verified",
            cached_input_tokens=95,
            uncached_input_tokens=5,
        )
        store.add_event(first, "worker.usage", sample)
        store.add_event(second, "worker.usage", sample)
    metrics = LightWorkerService(config, store, None).cache_metrics(window_seconds=3600)  # type: ignore[arg-type]
    assert metrics["warm"]["verified_samples"] == 2
    assert metrics["target"]["status"] == "insufficient_samples"
    assert all(item["verified_samples"] == 1 for item in metrics["target"]["cohorts"])


def test_usage_without_event_id_is_deduplicated_within_task_only(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    first, second = task(store, tmp_path, "one"), task(store, tmp_path, "two")
    store.add_event(first, "worker.usage", usage())
    store.add_event(first, "worker.usage", usage())
    store.add_event(second, "worker.usage", usage())
    assert store.cache_metrics(window_seconds=3600)["overall"]["samples"] == 2


def test_invalid_historical_usage_gets_receipt_and_is_not_rescanned(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    task_id = task(store, tmp_path, "one")
    event_id = store.add_event(task_id, "worker.usage", {"input_tokens": 0})
    receipt = store._connection().execute(
        "SELECT disposition FROM usage_event_receipts WHERE source_event_id=?", (event_id,)
    ).fetchone()
    assert receipt["disposition"] == "invalid"
    TaskStore(store.db_path)
    count = store._connection().execute(
        "SELECT COUNT(*) FROM usage_event_receipts WHERE source_event_id=?", (event_id,)
    ).fetchone()[0]
    assert count == 1


def test_historical_backfill_runs_all_bounded_batches(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    task_id = task(store, tmp_path, "legacy-batch")
    payload = __import__("json").dumps(usage(), ensure_ascii=False)
    created_at = __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
    store._connection().executemany(
        "INSERT INTO events(task_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
        [(task_id, "worker.usage", payload, created_at) for _ in range(1001)],
    )
    migrated = TaskStore(store.db_path)
    receipts = migrated._connection().execute("SELECT COUNT(*) FROM usage_event_receipts").fetchone()[0]
    assert receipts == 1001


def test_cache_metric_windows_are_bounded_before_datetime_conversion(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    with pytest.raises(ValueError, match="between 1"):
        store.cache_metrics(window_seconds=CACHE_WINDOW_MAX_SECONDS + 1)
    task_id = task(store, tmp_path, "oversized-window")
    event_id = store.add_event(
        task_id,
        "worker.usage",
        usage(cache_warm_window_seconds=CACHE_WINDOW_MAX_SECONDS + 1),
    )
    receipt = store._connection().execute(
        "SELECT disposition FROM usage_event_receipts WHERE source_event_id=?", (event_id,)
    ).fetchone()
    assert receipt["disposition"] == "invalid"


def test_usage_sample_schema_migrates_from_early_cache_lab_table(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE usage_samples (
        id INTEGER PRIMARY KEY, source_event_id INTEGER UNIQUE, event_key TEXT,
        task_id TEXT, cache_cohort TEXT, cache_cohort_sha256 TEXT, gateway TEXT,
        model TEXT, input_tokens INTEGER, cached_input_tokens INTEGER,
        uncached_input_tokens INTEGER, cache_hit_rate REAL, cohort_class TEXT,
        created_at TEXT
    )""")
    conn.commit()
    conn.close()
    store = TaskStore(db)
    columns = {row[1] for row in store._connection().execute("PRAGMA table_info(usage_samples)")}
    assert {"route_verification", "context_pack_hash", "context_pack_bytes", "prompt_protocol"} <= columns
