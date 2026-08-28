from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import Config
from .models import WorktreeInfo


class WorktreeError(RuntimeError):
    pass


def _git(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def git_root(workspace: str | Path) -> Path | None:
    path = Path(workspace).resolve()
    result = _git(path, "rev-parse", "--show-toplevel", check=False)
    if result.returncode:
        return None
    return Path(result.stdout.strip()).resolve()


def _ref_exists(root: Path, ref: str) -> bool:
    result = _git(root, "show-ref", "--verify", "--quiet", ref, check=False)
    return result.returncode == 0


def create_worktree(workspace: str | Path, task_id: str, cfg: Config) -> WorktreeInfo:
    workspace_path = Path(workspace).resolve()
    root = git_root(workspace_path)
    if root is None:
        raise WorktreeError("Write tasks require a Git repository")
    dirty = _git(root, "status", "--porcelain").stdout.strip()
    if dirty and not cfg.allow_dirty_worktree_source:
        raise WorktreeError(
            "Source repository has uncommitted changes; commit/stash them or explicitly allow dirty sources"
        )
    safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id)[:60]
    if not safe_id:
        raise WorktreeError("Task id does not contain a safe worktree name")
    target = (cfg.worktrees_dir / safe_id).resolve()
    branch = f"lightworker/{safe_id}"
    worktrees_root = cfg.worktrees_dir.resolve()
    if target == worktrees_root or worktrees_root not in target.parents:
        raise WorktreeError("Resolved worktree path escapes the LightWorker state directory")
    if target.exists():
        raise WorktreeError(f"Worktree path already exists: {target}")
    local_ref = f"refs/heads/{branch}"
    remote_ref = f"refs/remotes/origin/{branch}"
    if _ref_exists(root, local_ref):
        raise WorktreeError(f"LightWorker branch ref already exists: {local_ref}")
    if _ref_exists(root, remote_ref):
        raise WorktreeError(f"LightWorker remote tracking ref already exists: {remote_ref}")
    result = _git(root, "worktree", "add", "-b", branch, str(target), "HEAD", check=False)
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise WorktreeError(f"git worktree add failed: {message}")
    actual_branch = _git(target, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if actual_branch.returncode or actual_branch.stdout.strip() != branch:
        raise WorktreeError("Created worktree is not attached to the expected LightWorker branch")
    actual_root = git_root(target)
    if actual_root != target:
        raise WorktreeError("Created worktree root does not match the reserved LightWorker directory")
    relative_workspace = workspace_path.relative_to(root)
    isolated_workspace = (target / relative_workspace).resolve()
    if not isolated_workspace.is_dir():
        raise WorktreeError(f"Workspace subdirectory is missing from worktree: {relative_workspace}")
    return WorktreeInfo(path=str(isolated_workspace), branch=branch)
