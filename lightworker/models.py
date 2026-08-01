from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "blocked", "orphaned"}
ACTIVE_STATUSES = {"starting", "running", "finishing"}
KNOWN_STATUSES = {
    "queued",
    "starting",
    "running",
    "finishing",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "blocked",
    "orphaned",
}
KNOWN_KINDS = {"plan", "explore", "execute", "review"}
READ_ONLY_KINDS = {"plan", "explore", "review"}


@dataclass(slots=True)
class TaskSpec:
    objective: str
    workspace: str
    kind: str = "explore"
    model: str = "gpt-5.6-terra"
    reasoning_effort: str = "medium"
    sandbox: str = "read-only"
    mode: str = "auto_readonly"
    timeout_seconds: int = 1800
    allowed_paths: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    task_id: str | None = None
    parent_id: str | None = None
    root_id: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunResult:
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    exit_code: int | None = None
    result_path: str | None = None


@dataclass(slots=True)
class WorktreeInfo:
    path: str
    branch: str


def public_task(row: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, secret-free task representation for CLI/MCP clients."""
    keys = (
        "id",
        "root_id",
        "parent_id",
        "name",
        "kind",
        "objective",
        "workspace",
        "model",
        "reasoning_effort",
        "sandbox",
        "mode",
        "status",
        "priority",
        "attempt",
        "timeout_seconds",
        "created_at",
        "started_at",
        "finished_at",
        "pid",
        "worktree_path",
        "branch_name",
        "result_path",
        "error",
    )
    return {key: row.get(key) for key in keys}
