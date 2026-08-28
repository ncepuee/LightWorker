from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from .models import TaskSpec


APPROVAL_SCOPE_VERSION = "approval_scope.v1"


def build_approval_scope(spec: TaskSpec) -> dict[str, Any]:
    """Return the exact, secret-free authority a user is being asked to grant."""
    objective_hash = hashlib.sha256(spec.objective.strip().encode("utf-8")).hexdigest()
    return {
        "version": APPROVAL_SCOPE_VERSION,
        "objective_sha256": objective_hash,
        "kind": spec.kind,
        "workspace": spec.workspace,
        "sandbox": spec.sandbox,
        "mode": spec.mode,
        "execution_channel": spec.execution_channel,
        "gateway": spec.gateway,
        "upstream_model": spec.upstream_model,
        "provider": spec.provider,
        "required_capabilities": sorted(spec.required_capabilities),
        "route_capabilities": sorted(spec.route_capabilities),
        "catalog_revision": spec.catalog_revision,
        "allowed_paths": sorted(spec.allowed_paths),
        "prohibited_actions": sorted(spec.prohibited_actions),
        "timeout_seconds": int(spec.timeout_seconds),
        "worktree_required": spec.kind == "execute",
        "write_scope": "isolated_git_worktree" if spec.kind == "execute" else "read_only",
    }


def scope_digest(scope: dict[str, Any]) -> str:
    canonical = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stamp_approval(spec: TaskSpec) -> None:
    scope = build_approval_scope(spec)
    spec.approval_id = f"approval-{uuid.uuid4().hex[:16]}"
    spec.approval_scope = scope
    spec.approval_scope_digest = scope_digest(scope)


def verify_approval(spec: TaskSpec, approval_id: str | None, digest: str | None) -> None:
    if not spec.approval_id or not spec.approval_scope_digest:
        return  # Historical tasks created before approval_scope.v1.
    current_scope = build_approval_scope(spec)
    current_digest = scope_digest(current_scope)
    if current_digest != spec.approval_scope_digest:
        raise ValueError("Task approval scope changed after it was presented; review the task again")
    if approval_id != spec.approval_id or digest != spec.approval_scope_digest:
        raise ValueError("Approval id or scope digest does not match the pending request")
