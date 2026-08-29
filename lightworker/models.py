from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "blocked", "orphaned"}
# Native work remains active while the Codex host owns the spawned thread.
ACTIVE_STATUSES = {"starting", "awaiting_native_dispatch", "native_dispatching", "running"}
KNOWN_STATUSES = {
    "queued",
    "starting",
    "awaiting_native_dispatch",
    "native_dispatching",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "blocked",
    "orphaned",
}
KNOWN_KINDS = {"plan", "explore", "execute", "review", "image"}
READ_ONLY_KINDS = {"plan", "explore", "review", "image"}
KNOWN_EXECUTION_CHANNELS = {"lightworker_worker", "native_subagent"}


@dataclass(slots=True)
class TaskSpec:
    objective: str
    workspace: str
    kind: str = "explore"
    model: str = "gpt-5.6-terra"
    profile: str | None = None
    requested_model: str | None = None
    requested_gateway: str | None = None
    requested_reasoning_effort: str | None = None
    gateway: str | None = None
    upstream_model: str | None = None
    response_mode: str | None = None
    fallback_gateway: str | None = None
    provider: str | None = None
    billing_class: str | None = None
    execution_channel: str = "lightworker_worker"
    required_capabilities: list[str] = field(default_factory=list)
    route_capabilities: list[str] = field(default_factory=list)
    catalog_revision: str | None = None
    approval_id: str | None = None
    approval_scope_digest: str | None = None
    approval_scope: dict[str, Any] = field(default_factory=dict)
    cache_cohort: str | None = None
    context_pack_name: str | None = None
    context_pack_version: str | None = None
    context_pack_content: str | None = None
    context_pack_hash: str | None = None
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
        "profile",
        "requested_model",
        "requested_gateway",
        "requested_reasoning_effort",
        "gateway",
        "upstream_model",
        "response_mode",
        "fallback_gateway",
        "provider",
        "billing_class",
        "execution_channel",
        "required_capabilities",
        "route_capabilities",
        "catalog_revision",
        "approval_id",
        "approval_scope_digest",
        "approval_scope",
        "cache_cohort",
        "context_pack_name",
        "context_pack_version",
        "context_pack_hash",
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
        "native_thread_id",
        "native_host_id",
        "native_lease_expires_at",
        "native_dispatch_attempts",
        "native_last_state",
        "worktree_path",
        "branch_name",
        "result_path",
        "error",
    )
    spec: dict[str, Any] = {}
    if row.get("spec_json"):
        try:
            import json

            spec = json.loads(row["spec_json"])
        except (TypeError, ValueError):
            spec = {}
    return {key: row.get(key, spec.get(key)) for key in keys}
