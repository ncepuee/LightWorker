from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .cache import CACHE_WINDOW_MAX_SECONDS
from .models import ACTIVE_STATUSES, TERMINAL_STATUSES, TaskSpec


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class TaskStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.initialize()

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self._connection()
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def initialize(self) -> None:
        conn = self._connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                root_id TEXT,
                parent_id TEXT,
                name TEXT,
                kind TEXT NOT NULL,
                objective TEXT NOT NULL,
                workspace TEXT NOT NULL,
                model TEXT NOT NULL,
                reasoning_effort TEXT NOT NULL,
                sandbox TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                attempt INTEGER NOT NULL DEFAULT 0,
                timeout_seconds INTEGER NOT NULL,
                spec_json TEXT NOT NULL,
                result_json TEXT,
                result_path TEXT,
                error TEXT,
                pid INTEGER,
                lease_id TEXT,
                native_thread_id TEXT,
                native_host_id TEXT,
                native_lease_id TEXT,
                native_lease_expires_at TEXT,
                native_dispatch_attempts INTEGER NOT NULL DEFAULT 0,
                native_last_state TEXT,
                worktree_path TEXT,
                branch_name TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY(parent_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS dependencies (
                task_id TEXT NOT NULL,
                depends_on TEXT NOT NULL,
                PRIMARY KEY(task_id, depends_on),
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(depends_on) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS root_budgets (
                root_id TEXT PRIMARY KEY,
                max_concurrency INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                max_retries INTEGER NOT NULL,
                max_escalations INTEGER NOT NULL,
                attempts_used INTEGER NOT NULL DEFAULT 0,
                retries_used INTEGER NOT NULL DEFAULT 0,
                escalations_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_event_id INTEGER NOT NULL UNIQUE,
                event_key TEXT,
                task_id TEXT NOT NULL,
                cache_cohort TEXT,
                cache_cohort_sha256 TEXT,
                gateway TEXT,
                model TEXT,
                route_verification TEXT NOT NULL DEFAULT 'unverified',
                context_pack_hash TEXT,
                context_pack_bytes INTEGER NOT NULL DEFAULT 0,
                prompt_protocol TEXT,
                input_tokens INTEGER NOT NULL CHECK(input_tokens > 0),
                cached_input_tokens INTEGER NOT NULL CHECK(
                    cached_input_tokens >= 0 AND cached_input_tokens <= input_tokens
                ),
                uncached_input_tokens INTEGER NOT NULL CHECK(uncached_input_tokens >= 0),
                cache_hit_rate REAL NOT NULL CHECK(cache_hit_rate >= 0 AND cache_hit_rate <= 1),
                cohort_class TEXT NOT NULL CHECK(cohort_class IN ('cold', 'warm', 'indeterminate')),
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(source_event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS usage_event_receipts (
                source_event_id INTEGER PRIMARY KEY,
                disposition TEXT NOT NULL CHECK(disposition IN ('inserted', 'duplicate', 'invalid')),
                processed_at TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, created_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_root ON tasks(root_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
            CREATE INDEX IF NOT EXISTS idx_usage_samples_metrics
                ON usage_samples(created_at, model, gateway, cohort_class);
            CREATE INDEX IF NOT EXISTS idx_usage_samples_cohort
                ON usage_samples(cache_cohort, cache_cohort_sha256, gateway, model, created_at, task_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_samples_event_key
                ON usage_samples(event_key) WHERE event_key IS NOT NULL;
            """
        )
        self._ensure_usage_sample_columns(conn)
        self._ensure_task_columns(conn)
        conn.execute(
            """
            UPDATE usage_samples SET cohort_class='indeterminate'
            WHERE cache_cohort NOT LIKE 'cache_cohort.v2:%'
               OR prompt_protocol NOT IN ('lightworker.prompt.v4','lightworker.prompt.v5')
               OR prompt_protocol IS NULL
               OR route_verification='mismatch'
            """
        )
        self._backfill_usage_samples()

    @staticmethod
    def _ensure_usage_sample_columns(conn: sqlite3.Connection) -> None:
        existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(usage_samples)").fetchall()}
        additions = {
            "route_verification": "TEXT NOT NULL DEFAULT 'unverified'",
            "context_pack_hash": "TEXT",
            "context_pack_bytes": "INTEGER NOT NULL DEFAULT 0",
            "prompt_protocol": "TEXT",
        }
        for name, declaration in additions.items():
            if name not in existing:
                try:
                    conn.execute(f"ALTER TABLE usage_samples ADD COLUMN {name} {declaration}")
                except sqlite3.OperationalError as exc:
                    # Another process may have completed the additive migration
                    # after this connection read PRAGMA table_info.
                    if "duplicate column name" not in str(exc).lower():
                        raise

    @staticmethod
    def _ensure_task_columns(conn: sqlite3.Connection) -> None:
        existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        additions = {
            "native_thread_id": "TEXT",
            "native_host_id": "TEXT",
            "native_lease_id": "TEXT",
            "native_lease_expires_at": "TEXT",
            "native_dispatch_attempts": "INTEGER NOT NULL DEFAULT 0",
            "native_last_state": "TEXT",
        }
        for name, declaration in additions.items():
            if name not in existing:
                try:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {declaration}")
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise

    def _backfill_usage_samples(self) -> None:
        """Materialize one bounded batch of historical usage events.

        A receipt records invalid and duplicate events too, so malformed legacy
        telemetry is not reparsed on every process startup.
        """
        while True:
            with self.transaction(immediate=True) as conn:
                rows = conn.execute(
                    """
                    SELECT e.id,e.task_id,e.payload_json,e.created_at
                    FROM events e
                    LEFT JOIN usage_event_receipts receipt ON receipt.source_event_id=e.id
                    WHERE e.event_type='worker.usage' AND receipt.source_event_id IS NULL
                    ORDER BY e.id
                    LIMIT 1000
                    """
                ).fetchall()
                for row in rows:
                    try:
                        payload = json.loads(row["payload_json"])
                    except (TypeError, json.JSONDecodeError):
                        conn.execute(
                            "INSERT OR IGNORE INTO usage_event_receipts VALUES(?,?,?)",
                            (int(row["id"]), "invalid", utc_now()),
                        )
                        continue
                    disposition = self._materialize_usage_sample(
                        conn, int(row["id"]), str(row["task_id"]), payload, str(row["created_at"])
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO usage_event_receipts VALUES(?,?,?)",
                        (int(row["id"]), disposition, utc_now()),
                    )
            if len(rows) < 1000:
                break

    def add_event(self, task_id: str, event_type: str, payload: Any | None = None) -> int:
        payload = payload or {}
        created_at = utc_now()
        with self.transaction(immediate=event_type == "worker.usage") as conn:
            cur = conn.execute(
                "INSERT INTO events(task_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
                (task_id, event_type, json.dumps(payload, ensure_ascii=False), created_at),
            )
            event_id = int(cur.lastrowid)
            if event_type == "worker.usage":
                disposition = self._materialize_usage_sample(conn, event_id, task_id, payload, created_at)
                conn.execute(
                    "INSERT INTO usage_event_receipts VALUES(?,?,?)",
                    (event_id, disposition, utc_now()),
                )
        return event_id

    @staticmethod
    def _usage_sample_values(payload: Any) -> dict[str, Any] | None:
        """Return normalized cache-usage values, or skip an invalid usage event.

        Usage is observed telemetry: a malformed provider event must remain in the
        event log, but must never distort token-weighted cache metrics.
        """
        if not isinstance(payload, dict):
            return None

        def token(name: str) -> int | None:
            value = payload.get(name)
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        input_tokens = token("input_tokens")
        cached_tokens = token("cached_input_tokens")
        if input_tokens is None or cached_tokens is None or input_tokens <= 0:
            return None
        if cached_tokens < 0 or cached_tokens > input_tokens:
            return None

        # Compute misses from the validated total rather than trusting an optional
        # upstream field that can be rounded or inconsistent across gateways.
        uncached_tokens = input_tokens - cached_tokens
        declared_uncached = token("uncached_input_tokens")
        if declared_uncached is not None and declared_uncached != uncached_tokens:
            return None

        def text(name: str) -> str | None:
            value = payload.get(name)
            return value.strip() if isinstance(value, str) and value.strip() else None

        return {
            "cache_cohort": text("cache_cohort"),
            "cache_cohort_sha256": text("cache_cohort_sha256"),
            "gateway": text("gateway"),
            "model": text("model"),
            "route_verification": text("route_verification") or "unverified",
            "context_pack_hash": text("context_pack_sha256"),
            "context_pack_bytes": token("context_pack_bytes") or 0,
            "prompt_protocol": text("prompt_protocol"),
            "warm_window_seconds": token("cache_warm_window_seconds"),
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_tokens,
            "uncached_input_tokens": uncached_tokens,
            "cache_hit_rate": cached_tokens / input_tokens,
        }

    @staticmethod
    def _event_key(payload: Any, task_id: str, values: dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            raise TypeError("usage payload must be a mapping")
        value = payload.get("event_id")
        if not isinstance(value, bool) and isinstance(value, (str, int)):
            value = str(value).strip()
            if value:
                return f"event:{task_id}:{value}"
        # Some gateways emit the same final usage once in response.completed
        # and again in turn.completed without an upstream event id.  Collapse
        # only identical usage within the same task; identical requests in
        # separate tasks are legitimate cache samples.
        fingerprint = {
            "task_id": task_id,
            "cache_cohort": values["cache_cohort"],
            "cache_cohort_sha256": values["cache_cohort_sha256"],
            "gateway": values["gateway"],
            "model": values["model"],
            "input_tokens": values["input_tokens"],
            "cached_input_tokens": values["cached_input_tokens"],
            "uncached_input_tokens": values["uncached_input_tokens"],
        }
        digest = hashlib.sha256(
            json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"usage:{digest}"

    def _materialize_usage_sample(
        self,
        conn: sqlite3.Connection,
        source_event_id: int,
        task_id: str,
        payload: Any,
        created_at: str,
    ) -> str:
        values = self._usage_sample_values(payload)
        if values is None:
            return "invalid"
        warm_window = values["warm_window_seconds"]
        if warm_window is None:
            warm_window = 300
        if warm_window <= 0 or warm_window > CACHE_WINDOW_MAX_SECONDS:
            return "invalid"
        # A cohort is strict only when every routing dimension that scopes an
        # upstream cache is known.  Missing metadata remains useful telemetry,
        # but cannot truthfully be called either a cold or warm cache request.
        strict = all(
            values[name] is not None
            for name in ("cache_cohort", "cache_cohort_sha256", "gateway", "model")
        ) and str(values["cache_cohort"]).startswith("cache_cohort.v2:") \
          and values["prompt_protocol"] in {"lightworker.prompt.v4", "lightworker.prompt.v5"}
        cohort_class = "indeterminate"
        if strict and values["route_verification"] != "mismatch":
            warm_cutoff = datetime.fromisoformat(created_at).timestamp() - warm_window
            warm_cutoff_at = datetime.fromtimestamp(warm_cutoff, UTC).isoformat()
            earlier = conn.execute(
                """
                SELECT 1 FROM usage_samples
                WHERE cache_cohort=? AND cache_cohort_sha256=? AND gateway=? AND model=?
                  AND task_id<>?
                  AND created_at>=?
                  AND cohort_class IN ('cold','warm')
                  AND route_verification!='mismatch'
                LIMIT 1
                """,
                (
                    values["cache_cohort"], values["cache_cohort_sha256"],
                    values["gateway"], values["model"], task_id,
                    warm_cutoff_at,
                ),
            ).fetchone()
            cohort_class = "warm" if earlier else "cold"
        cur = conn.execute(
            """
            INSERT INTO usage_samples(
                source_event_id,event_key,task_id,cache_cohort,cache_cohort_sha256,
                gateway,model,route_verification,context_pack_hash,context_pack_bytes,prompt_protocol,
                input_tokens,cached_input_tokens,uncached_input_tokens,
                cache_hit_rate,cohort_class,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT DO NOTHING
            """,
            (
                source_event_id, self._event_key(payload, task_id, values), task_id,
                values["cache_cohort"], values["cache_cohort_sha256"], values["gateway"],
                values["model"], values["route_verification"], values["context_pack_hash"],
                values["context_pack_bytes"], values["prompt_protocol"],
                values["input_tokens"], values["cached_input_tokens"],
                values["uncached_input_tokens"], values["cache_hit_rate"], cohort_class,
                created_at,
            ),
        )
        return "inserted" if cur.rowcount else "duplicate"

    def cache_metrics(
        self,
        model: str | None = None,
        gateway: str | None = None,
        window_seconds: int = 7 * 24 * 60 * 60,
    ) -> dict[str, Any]:
        """Return cache metrics aggregated from materialized usage samples only."""
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, int)
            or window_seconds <= 0
            or window_seconds > CACHE_WINDOW_MAX_SECONDS
        ):
            raise ValueError(f"window_seconds must be between 1 and {CACHE_WINDOW_MAX_SECONDS}")
        cutoff = datetime.now(UTC).timestamp() - window_seconds
        cutoff_at = datetime.fromtimestamp(cutoff, UTC).isoformat()
        clauses = ["created_at>=?"]
        params: list[Any] = [cutoff_at]
        if model is not None:
            clauses.append("model=?")
            params.append(model)
        if gateway is not None:
            clauses.append("gateway=?")
            params.append(gateway)
        where = " WHERE " + " AND ".join(clauses)

        def aggregate(classification: str | None = None) -> dict[str, Any]:
            scoped_where = where
            scoped_params = list(params)
            if classification is not None:
                scoped_where += " AND cohort_class=?"
                scoped_params.append(classification)
            row = self._connection().execute(
                f"""
                SELECT COUNT(*) AS samples,
                       COALESCE(SUM(CASE WHEN route_verification='verified' THEN 1 ELSE 0 END), 0) AS verified_samples,
                       COALESCE(SUM(CASE WHEN route_verification='unverified' THEN 1 ELSE 0 END), 0) AS unverified_samples,
                       COALESCE(SUM(CASE WHEN route_verification='verified' THEN input_tokens ELSE 0 END), 0) AS verified_input_tokens,
                       COALESCE(SUM(CASE WHEN route_verification='verified' THEN cached_input_tokens ELSE 0 END), 0) AS verified_cached_input_tokens,
                       COALESCE(SUM(CASE WHEN route_verification='verified' THEN uncached_input_tokens ELSE 0 END), 0) AS verified_uncached_input_tokens,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                       COALESCE(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                       MAX(created_at) AS recent_at
                FROM usage_samples{scoped_where}
                """,
                scoped_params,
            ).fetchone()
            result = dict(row)
            result["samples"] = int(result["samples"])
            result["verified_samples"] = int(result["verified_samples"])
            result["unverified_samples"] = int(result["unverified_samples"])
            for name in (
                "input_tokens", "cached_input_tokens", "uncached_input_tokens",
                "verified_input_tokens", "verified_cached_input_tokens", "verified_uncached_input_tokens",
            ):
                result[name] = int(result[name])
            result["cache_hit_rate"] = (
                result["cached_input_tokens"] / result["input_tokens"]
                if result["input_tokens"] else None
            )
            result["verified_cache_hit_rate"] = (
                result["verified_cached_input_tokens"] / result["verified_input_tokens"]
                if result["verified_input_tokens"] else None
            )
            return result

        cohort_rows = self._connection().execute(
            f"""
            SELECT cache_cohort,cache_cohort_sha256,gateway,model,cohort_class,
                   MAX(context_pack_hash) AS context_pack_hash,
                   MAX(context_pack_bytes) AS context_pack_bytes,
                   MAX(prompt_protocol) AS prompt_protocol,
                   SUM(CASE WHEN route_verification='verified' THEN 1 ELSE 0 END) AS verified_samples,
                   SUM(CASE WHEN route_verification='verified' THEN input_tokens ELSE 0 END) AS verified_input_tokens,
                   SUM(CASE WHEN route_verification='verified' THEN cached_input_tokens ELSE 0 END) AS verified_cached_input_tokens,
                   COUNT(*) AS samples,
                   SUM(input_tokens) AS input_tokens,
                   SUM(cached_input_tokens) AS cached_input_tokens,
                   SUM(uncached_input_tokens) AS uncached_input_tokens,
                   MAX(created_at) AS recent_at
            FROM usage_samples{where}
            GROUP BY cache_cohort,cache_cohort_sha256,gateway,model,cohort_class
            ORDER BY recent_at DESC, cache_cohort_sha256, gateway, model
            """,
            params,
        ).fetchall()
        cohorts: list[dict[str, Any]] = []
        for row in cohort_rows:
            item = dict(row)
            item["samples"] = int(item["samples"])
            item["verified_samples"] = int(item["verified_samples"] or 0)
            for name in (
                "input_tokens", "cached_input_tokens", "uncached_input_tokens",
                "verified_input_tokens", "verified_cached_input_tokens",
            ):
                item[name] = int(item[name])
            item["cache_hit_rate"] = item["cached_input_tokens"] / item["input_tokens"]
            item["verified_cache_hit_rate"] = (
                item["verified_cached_input_tokens"] / item["verified_input_tokens"]
                if item["verified_input_tokens"] else None
            )
            cohorts.append(item)
        return {
            "window_seconds": window_seconds,
            "model": model,
            "gateway": gateway,
            "overall": aggregate(),
            "cold": aggregate("cold"),
            "warm": aggregate("warm"),
            "indeterminate": aggregate("indeterminate"),
            "cohorts": cohorts,
        }

    def cache_audit(self, task_id: str) -> dict[str, Any] | None:
        row = self._connection().execute(
            """
            SELECT cache_cohort,cache_cohort_sha256,gateway,model,route_verification,
                   context_pack_hash,context_pack_bytes,prompt_protocol,input_tokens,
                   cached_input_tokens,uncached_input_tokens,cache_hit_rate,cohort_class,created_at
            FROM usage_samples WHERE task_id=? ORDER BY id DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    def create_task(
        self,
        spec: TaskSpec,
        status: str = "queued",
        priority: int = 0,
        root_budget: dict[str, int] | None = None,
    ) -> str:
        if root_budget and not (spec.root_id or spec.task_id):
            spec = TaskSpec(**spec.to_dict())
            spec.task_id = f"task-{uuid.uuid4().hex[:12]}"
        budgets = {str(spec.root_id or spec.task_id): root_budget} if root_budget else None
        return self.create_tasks([(spec, status, priority)], root_budgets=budgets)[0]

    def create_tasks(
        self,
        entries: list[tuple[TaskSpec, str, int]],
        *,
        root_budgets: dict[str, dict[str, int]] | None = None,
    ) -> list[str]:
        prepared: list[tuple[str, str, TaskSpec, str, int, dict[str, Any]]] = []
        for spec, status, priority in entries:
            task_id = spec.task_id or f"task-{uuid.uuid4().hex[:12]}"
            root_id = spec.root_id or task_id
            payload = spec.to_dict()
            payload["task_id"] = task_id
            payload["root_id"] = root_id
            prepared.append((task_id, root_id, spec, status, priority, payload))
        with self.transaction(immediate=True) as conn:
            now = utc_now()
            for root_id, budget in (root_budgets or {}).items():
                conn.execute(
                    """
                    INSERT INTO root_budgets(
                        root_id,max_concurrency,max_attempts,max_retries,max_escalations,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?) ON CONFLICT(root_id) DO NOTHING
                    """,
                    (
                        root_id,
                        int(budget["max_concurrency"]),
                        int(budget["max_attempts"]),
                        int(budget["max_retries"]),
                        int(budget["max_escalations"]),
                        now,
                        now,
                    ),
                )
            for task_id, root_id, spec, status, priority, payload in prepared:
                conn.execute(
                    """
                    INSERT INTO tasks(
                        id,root_id,parent_id,name,kind,objective,workspace,model,
                        reasoning_effort,sandbox,mode,status,priority,timeout_seconds,
                        spec_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        task_id, root_id, spec.parent_id, spec.name, spec.kind, spec.objective,
                        spec.workspace, spec.model, spec.reasoning_effort, spec.sandbox, spec.mode,
                        status, priority, spec.timeout_seconds, json.dumps(payload, ensure_ascii=False), now,
                    ),
                )
                for dependency in spec.dependencies:
                    conn.execute(
                        "INSERT INTO dependencies(task_id,depends_on) VALUES(?,?)",
                        (task_id, dependency),
                    )
        for task_id, _, spec, status, _, _ in prepared:
            self.add_event(task_id, "task.created", {"status": status, "kind": spec.kind})
        return [task_id for task_id, *_ in prepared]

    def ensure_root_budget(
        self,
        root_id: str,
        *,
        max_concurrency: int = 2,
        max_attempts: int = 8,
        max_retries: int = 1,
        max_escalations: int = 1,
    ) -> dict[str, Any]:
        now = utc_now()
        values = (
            root_id,
            max(1, int(max_concurrency)),
            max(1, int(max_attempts)),
            max(0, int(max_retries)),
            max(0, int(max_escalations)),
            now,
            now,
        )
        self._connection().execute(
            """
            INSERT INTO root_budgets(
                root_id,max_concurrency,max_attempts,max_retries,max_escalations,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(root_id) DO NOTHING
            """,
            values,
        )
        return self.root_budget(root_id)

    def root_budget(self, root_id: str) -> dict[str, Any]:
        row = self._connection().execute(
            "SELECT * FROM root_budgets WHERE root_id=?", (root_id,)
        ).fetchone()
        if not row:
            return self.ensure_root_budget(root_id)
        budget = dict(row)
        active = self._connection().execute(
            "SELECT COUNT(*) FROM tasks WHERE root_id=? AND status IN ('starting','awaiting_native_dispatch','native_dispatching','running')",
            (root_id,),
        ).fetchone()[0]
        budget["active_workers"] = int(active)
        return budget

    def reserve_budget(self, root_id: str, counter: str) -> bool:
        columns = {"retry": ("retries_used", "max_retries"), "escalation": ("escalations_used", "max_escalations")}
        if counter not in columns:
            raise ValueError(f"Unsupported budget counter: {counter}")
        used, maximum = columns[counter]
        self.ensure_root_budget(root_id)
        with self.transaction(immediate=True) as conn:
            cur = conn.execute(
                f"UPDATE root_budgets SET {used}={used}+1,updated_at=? WHERE root_id=? AND {used} < {maximum}",
                (utc_now(), root_id),
            )
            return cur.rowcount == 1

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self._connection().execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_spec(self, task_id: str) -> TaskSpec:
        row = self.get_task(task_id)
        if not row:
            raise KeyError(task_id)
        data = json.loads(row["spec_json"])
        return TaskSpec(**data)

    def update_spec(self, task_id: str, spec: TaskSpec) -> None:
        """Persist an additive TaskSpec migration without changing task identity or status."""
        payload = spec.to_dict()
        payload["task_id"] = task_id
        self._connection().execute(
            "UPDATE tasks SET spec_json=?,model=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), spec.model, task_id),
        )

    def list_tasks(
        self,
        status: str | None = None,
        root_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("status=?")
            values.append(status)
        if root_id:
            clauses.append("root_id=?")
            values.append(root_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(max(1, min(limit, 1000)))
        rows = self._connection().execute(
            f"SELECT * FROM tasks{where} ORDER BY created_at DESC LIMIT ?", values
        ).fetchall()
        return [dict(row) for row in rows]

    def dependencies(self, task_id: str) -> list[str]:
        rows = self._connection().execute(
            "SELECT depends_on FROM dependencies WHERE task_id=? ORDER BY depends_on", (task_id,)
        ).fetchall()
        return [str(row[0]) for row in rows]

    def purge_terminal_tasks(self, statuses: set[str] | None = None) -> int:
        """Delete terminal (finished) tasks and their dependent rows.

        Only tasks in a terminal state are removed; active or pending work is
        never touched.  Events, usage samples, dependencies and orphaned root
        budgets are cleaned up via cascading deletes / explicit statements.
        Returns the number of deleted tasks.
        """
        targets = tuple(sorted(statuses or TERMINAL_STATUSES))
        placeholders = ",".join("?" for _ in targets)
        with self.transaction(immediate=True) as conn:
            rows = conn.execute(
                f"SELECT id FROM tasks WHERE status IN ({placeholders})", targets
            ).fetchall()
            ids = [str(row[0]) for row in rows]
            if not ids:
                return 0
            id_placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM tasks WHERE id IN ({id_placeholders})", ids)
            conn.execute(
                """
                DELETE FROM root_budgets
                WHERE root_id NOT IN (SELECT DISTINCT root_id FROM tasks WHERE root_id IS NOT NULL)
                """
            )
        return len(ids)

    def ready_tasks(self, limit: int) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            """
            WITH ready AS (
                SELECT t.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY t.root_id ORDER BY t.priority DESC, t.created_at ASC
                       ) AS root_round
                FROM tasks t
                WHERE t.status='queued'
                  AND NOT EXISTS (
                    SELECT 1 FROM dependencies d
                    JOIN tasks parent ON parent.id=d.depends_on
                    WHERE d.task_id=t.id AND parent.status!='completed'
                  )
                  AND (
                    SELECT COUNT(*) FROM tasks active
                    WHERE active.root_id=t.root_id AND active.status IN ('starting','awaiting_native_dispatch','native_dispatching','running')
                  ) < COALESCE(
                    (SELECT budget.max_concurrency FROM root_budgets budget WHERE budget.root_id=t.root_id),
                    2
                  )
            )
            SELECT * FROM ready
            ORDER BY root_round ASC, priority DESC, created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def claim_task(self, task_id: str) -> str | None:
        lease_id = uuid.uuid4().hex
        exhausted = False
        with self.transaction(immediate=True) as conn:
            row = conn.execute("SELECT root_id FROM tasks WHERE id=? AND status='queued'", (task_id,)).fetchone()
            if not row:
                return None
            root_id = str(row[0])
            now = utc_now()
            conn.execute(
                """
                INSERT INTO root_budgets(root_id,max_concurrency,max_attempts,max_retries,max_escalations,created_at,updated_at)
                VALUES(?,2,8,1,1,?,?) ON CONFLICT(root_id) DO NOTHING
                """,
                (root_id, now, now),
            )
            budget = conn.execute("SELECT * FROM root_budgets WHERE root_id=?", (root_id,)).fetchone()
            active = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE root_id=? AND status IN ('starting','awaiting_native_dispatch','native_dispatching','running')", (root_id,)
            ).fetchone()[0]
            if int(active) >= int(budget["max_concurrency"]):
                return None
            if int(budget["attempts_used"]) >= int(budget["max_attempts"]):
                conn.execute(
                    "UPDATE tasks SET status='blocked',error=?,finished_at=? WHERE id=? AND status='queued'",
                    ("Root task attempt budget exhausted", now, task_id),
                )
                exhausted = True
            if exhausted:
                lease_id = ""
            else:
                cur = conn.execute(
                    "UPDATE tasks SET status='starting',lease_id=?,attempt=attempt+1 WHERE id=? AND status='queued'",
                    (lease_id, task_id),
                )
                if cur.rowcount != 1:
                    return None
                conn.execute(
                    "UPDATE root_budgets SET attempts_used=attempts_used+1,updated_at=? WHERE root_id=?",
                    (now, root_id),
                )
        if exhausted:
            self.add_event(task_id, "budget.exhausted", {"counter": "attempts"})
            return None
        self.add_event(task_id, "task.claimed", {"lease_id": lease_id})
        return lease_id

    def update_status(
        self,
        task_id: str,
        status: str,
        *,
        error: str | None = None,
        result: dict[str, Any] | None = None,
        result_path: str | None = None,
        pid: int | None = None,
        worktree_path: str | None = None,
        branch_name: str | None = None,
    ) -> None:
        fields = ["status=?"]
        values: list[Any] = [status]
        if status == "running":
            fields.append("started_at=COALESCE(started_at, ?)")
            values.append(utc_now())
        if status in TERMINAL_STATUSES or status == "awaiting_approval":
            fields.append("finished_at=?")
            values.append(utc_now())
        optional = {
            "error": error,
            "result_json": json.dumps(result, ensure_ascii=False) if result is not None else None,
            "result_path": result_path,
            "pid": pid,
            "worktree_path": worktree_path,
            "branch_name": branch_name,
        }
        for key, value in optional.items():
            if value is not None:
                fields.append(f"{key}=?")
                values.append(value)
        values.append(task_id)
        self._connection().execute(f"UPDATE tasks SET {','.join(fields)} WHERE id=?", values)
        self.add_event(task_id, f"task.{status}", {"error": error} if error else {})

    def set_pid(self, task_id: str, pid: int) -> None:
        self._connection().execute("UPDATE tasks SET pid=? WHERE id=?", (pid, task_id))
        self.add_event(task_id, "worker.started", {"pid": pid})

    def stage_native_dispatch(self, task_id: str) -> bool:
        """Expose a claimed native task to the Codex-host bridge, never codex exec."""
        cur = self._connection().execute(
            """
            UPDATE tasks SET status='awaiting_native_dispatch',lease_id=NULL,native_last_state='queued'
            WHERE id=? AND status='starting'
            """,
            (task_id,),
        )
        if cur.rowcount:
            self.add_event(task_id, "native.dispatch_ready", {})
        return bool(cur.rowcount)

    def claim_native_dispatches(self, host_id: str, limit: int = 1, lease_seconds: int = 90) -> list[dict[str, Any]]:
        if not host_id or len(host_id) > 128:
            raise ValueError("host_id must be 1..128 characters")
        lease_seconds = max(15, min(int(lease_seconds), 3600))
        claimed: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        expires = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self.transaction(immediate=True) as conn:
            rows = conn.execute(
                """SELECT * FROM tasks WHERE status='awaiting_native_dispatch'
                   ORDER BY priority DESC,created_at ASC LIMIT ?""",
                (max(1, min(int(limit), 12)),),
            ).fetchall()
            for row in rows:
                task_id = str(row["id"])
                lease_id = uuid.uuid4().hex
                cur = conn.execute(
                    """UPDATE tasks SET status='native_dispatching',native_host_id=?,native_lease_id=?,
                       native_lease_expires_at=?,native_dispatch_attempts=native_dispatch_attempts+1,
                       native_last_state='claimed' WHERE id=? AND status='awaiting_native_dispatch'""",
                    (host_id, lease_id, expires, task_id),
                )
                if cur.rowcount:
                    item = dict(row)
                    item.update({"native_host_id": host_id, "native_lease_id": lease_id, "native_lease_expires_at": expires})
                    claimed.append(item)
        for row in claimed:
            self.add_event(str(row["id"]), "native.dispatch_claimed", {"host_id": host_id, "lease_expires_at": expires})
        return claimed

    def native_started(self, task_id: str, lease_id: str, thread_id: str) -> bool:
        if not thread_id or len(thread_id) > 256:
            raise ValueError("thread_id must be 1..256 characters")
        cur = self._connection().execute(
            """UPDATE tasks SET status='running',native_thread_id=?,native_last_state='running',
               started_at=COALESCE(started_at, ?) WHERE id=? AND status='native_dispatching' AND native_lease_id=?""",
            (thread_id, utc_now(), task_id, lease_id),
        )
        if cur.rowcount:
            self.add_event(task_id, "native.subagent_started", {"thread_id": thread_id})
        return bool(cur.rowcount)

    def native_event(self, task_id: str, lease_id: str, event_type: str, payload: dict[str, Any] | None = None) -> bool:
        if not event_type.startswith("native.") or len(event_type) > 96:
            raise ValueError("event_type must start with native.")
        payload = payload or {}
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > 16_384:
            raise ValueError("native event payload exceeds 16 KiB")
        expires = (datetime.now(UTC) + timedelta(seconds=90)).isoformat()
        cur = self._connection().execute(
            """UPDATE tasks SET native_lease_expires_at=?,native_last_state=?
               WHERE id=? AND status IN ('native_dispatching','running') AND native_lease_id=?""",
            (expires, event_type, task_id, lease_id),
        )
        if cur.rowcount:
            self.add_event(task_id, event_type, payload)
        return bool(cur.rowcount)

    def native_complete(self, task_id: str, lease_id: str, status: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> bool:
        if status not in {"completed", "failed", "cancelled", "blocked"}:
            raise ValueError("native completion status is invalid")
        cur = self._connection().execute(
            """UPDATE tasks SET status=?,result_json=?,error=?,finished_at=?,native_last_state=?,
               native_lease_expires_at=NULL WHERE id=? AND status IN ('native_dispatching','running') AND native_lease_id=?""",
            (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error, utc_now(), status, task_id, lease_id),
        )
        if cur.rowcount:
            self.add_event(task_id, "native.subagent_completed", {"status": status, "error": error})
        return bool(cur.rowcount)

    def requeue_expired_native_dispatches(self) -> int:
        now = utc_now()
        with self.transaction(immediate=True) as conn:
            rows = conn.execute(
                "SELECT id FROM tasks WHERE status='native_dispatching' AND native_lease_expires_at<?", (now,)
            ).fetchall()
            conn.execute(
                """UPDATE tasks SET status='awaiting_native_dispatch',native_lease_id=NULL,
                   native_lease_expires_at=NULL,native_last_state='lease_expired'
                   WHERE status='native_dispatching' AND native_lease_expires_at<?""",
                (now,),
            )
        for row in rows:
            self.add_event(str(row["id"]), "native.dispatch_lease_expired", {})
        return len(rows)

    def approve(self, task_id: str) -> bool:
        cur = self._connection().execute(
            "UPDATE tasks SET status='queued',finished_at=NULL,error=NULL WHERE id=? AND status='awaiting_approval'",
            (task_id,),
        )
        if cur.rowcount:
            self.add_event(task_id, "task.approved", {})
        return bool(cur.rowcount)

    def cancel(self, task_id: str) -> bool:
        cur = self._connection().execute(
            "UPDATE tasks SET status='cancelled',finished_at=? WHERE id=? AND status NOT IN ('completed','failed','cancelled','blocked')",
            (utc_now(), task_id),
        )
        if cur.rowcount:
            self.add_event(task_id, "task.cancel_requested", {})
        return bool(cur.rowcount)

    def is_cancelled(self, task_id: str) -> bool:
        row = self._connection().execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        return bool(row and row[0] == "cancelled")

    def events(self, task_id: str, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            "SELECT * FROM events WHERE task_id=? AND id>? ORDER BY id LIMIT ?",
            (task_id, after_id, max(1, min(limit, 2000))),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def reconcile_after_restart(self) -> int:
        with self.transaction(immediate=True) as conn:
            rows = conn.execute(
                "SELECT id FROM tasks WHERE status IN ('starting','native_dispatching','running')"
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE tasks SET status='orphaned',error=?,finished_at=? WHERE id=?",
                    ("Runner restarted while task was active", utc_now(), row[0]),
                )
        for row in rows:
            self.add_event(str(row[0]), "task.orphaned", {})
        return len(rows)

    def block_failed_dependencies(self) -> int:
        rows = self._connection().execute(
            """
            SELECT DISTINCT t.id FROM tasks t
            JOIN dependencies d ON d.task_id=t.id
            JOIN tasks parent ON parent.id=d.depends_on
            WHERE t.status='queued' AND parent.status IN ('failed','cancelled','blocked','orphaned')
            """
        ).fetchall()
        for row in rows:
            self.update_status(str(row[0]), "blocked", error="A dependency did not complete")
        return len(rows)

    def active_count(self) -> int:
        marks = ",".join("?" for _ in ACTIVE_STATUSES)
        row = self._connection().execute(
            f"SELECT COUNT(*) FROM tasks WHERE status IN ({marks})", tuple(ACTIVE_STATUSES)
        ).fetchone()
        return int(row[0])

    def has_pending_work(self) -> bool:
        row = self._connection().execute(
            # Native states are owned by the interactive Codex host.  A local
            # scheduler is idle once it has staged their durable tickets.
            "SELECT 1 FROM tasks WHERE status IN ('queued','starting','running') LIMIT 1"
        ).fetchone()
        return row is not None
