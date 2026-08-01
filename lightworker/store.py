from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

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
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, created_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_root ON tasks(root_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
            """
        )

    def add_event(self, task_id: str, event_type: str, payload: Any | None = None) -> int:
        cur = self._connection().execute(
            "INSERT INTO events(task_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (task_id, event_type, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
        )
        return int(cur.lastrowid)

    def create_task(self, spec: TaskSpec, status: str = "queued", priority: int = 0) -> str:
        task_id = spec.task_id or f"task-{uuid.uuid4().hex[:12]}"
        root_id = spec.root_id or task_id
        payload = spec.to_dict()
        payload["task_id"] = task_id
        payload["root_id"] = root_id
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO tasks(
                    id,root_id,parent_id,name,kind,objective,workspace,model,
                    reasoning_effort,sandbox,mode,status,priority,timeout_seconds,
                    spec_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    task_id,
                    root_id,
                    spec.parent_id,
                    spec.name,
                    spec.kind,
                    spec.objective,
                    spec.workspace,
                    spec.model,
                    spec.reasoning_effort,
                    spec.sandbox,
                    spec.mode,
                    status,
                    priority,
                    spec.timeout_seconds,
                    json.dumps(payload, ensure_ascii=False),
                    utc_now(),
                ),
            )
            for dependency in spec.dependencies:
                conn.execute(
                    "INSERT INTO dependencies(task_id,depends_on) VALUES(?,?)",
                    (task_id, dependency),
                )
        self.add_event(task_id, "task.created", {"status": status, "kind": spec.kind})
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self._connection().execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_spec(self, task_id: str) -> TaskSpec:
        row = self.get_task(task_id)
        if not row:
            raise KeyError(task_id)
        data = json.loads(row["spec_json"])
        return TaskSpec(**data)

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

    def ready_tasks(self, limit: int) -> list[dict[str, Any]]:
        rows = self._connection().execute(
            """
            SELECT t.* FROM tasks t
            WHERE t.status='queued'
              AND NOT EXISTS (
                SELECT 1 FROM dependencies d
                JOIN tasks parent ON parent.id=d.depends_on
                WHERE d.task_id=t.id AND parent.status!='completed'
              )
            ORDER BY t.priority DESC, t.created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def claim_task(self, task_id: str) -> str | None:
        lease_id = uuid.uuid4().hex
        with self.transaction(immediate=True) as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='starting',lease_id=?,attempt=attempt+1 WHERE id=? AND status='queued'",
                (lease_id, task_id),
            )
            if cur.rowcount != 1:
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
        expected_statuses: set[str] | None = None,
    ) -> bool:
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
        where = "id=?"
        if expected_statuses is None:
            placeholders = ",".join("?" for _ in TERMINAL_STATUSES)
            where += f" AND status NOT IN ({placeholders})"
            values.extend(sorted(TERMINAL_STATUSES))
        else:
            if not expected_statuses:
                return False
            placeholders = ",".join("?" for _ in expected_statuses)
            where += f" AND status IN ({placeholders})"
            values.extend(sorted(expected_statuses))
        cur = self._connection().execute(
            f"UPDATE tasks SET {','.join(fields)} WHERE {where}", values
        )
        if cur.rowcount:
            self.add_event(task_id, f"task.{status}", {"error": error} if error else {})
        return bool(cur.rowcount)

    def set_pid(self, task_id: str, pid: int) -> None:
        self._connection().execute("UPDATE tasks SET pid=? WHERE id=?", (pid, task_id))
        self.add_event(task_id, "worker.started", {"pid": pid})

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
            "UPDATE tasks SET status='cancelled',finished_at=? WHERE id=? AND status NOT IN ('finishing','completed','failed','cancelled','blocked','orphaned')",
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
                "SELECT id FROM tasks WHERE status IN ('starting','running','finishing')"
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
            "SELECT 1 FROM tasks WHERE status IN ('queued','starting','running','finishing') LIMIT 1"
        ).fetchone()
        return row is not None
