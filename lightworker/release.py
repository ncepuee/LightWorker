"""Deterministic release pipeline implementing the repository release SOP.

The SOP (README-Badge-Release-Tag-CI) is a deterministic, auditable sequence:
merge the reviewed PR, bump the single version source, push only after local
verification, wait for main CI, build artifacts with checksums, tag only on a
green main, wait for tag CI, then create the immutable GitHub Release. Those
steps need network access to GitHub, which codex worker sandboxes correctly
deny, so the pipeline lives here as policy-checked native tooling instead of
an unsandboxed agent task.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path

MAX_CI_MINUTES = 20


def _run(name: str, cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> tuple[bool, str]:
    print(f"[release] {name}: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    detail = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        print(f"[release] {name} FAILED (exit {proc.returncode}):\n{detail[-2000:]}", flush=True)
    return proc.returncode == 0, detail


def bump_version_files(version: str) -> bool:
    """Update pyproject.toml and lightworker/__init__.py to `version`."""
    targets = {
        Path("pyproject.toml"): (re.compile(r'(?m)^version = "[^"]+"$'), f'version = "{version}"'),
        Path("lightworker") / "__init__.py": (re.compile(r'(?m)__version__ = "[^"]+"$'), f'__version__ = "{version}"'),
    }
    for path, (pattern, replacement) in targets.items():
        text = path.read_text(encoding="utf-8")
        if pattern.search(text) is None:
            print(f"[release] version anchor not found in {path}", flush=True)
            return False
        path.write_text(pattern.sub(replacement, text, count=1), encoding="utf-8", newline="")
    return True


def wait_ci(branch: str, deadline_minutes: int = MAX_CI_MINUTES) -> bool:
    """Poll GitHub Actions until the latest run for `branch` completes green."""
    print(f"[release] waiting for CI on {branch} (max {deadline_minutes} min)", flush=True)
    deadline = time.monotonic() + deadline_minutes * 60
    while time.monotonic() < deadline:
        ok, detail = _run("ci-status", ["gh", "run", "list", "--branch", branch, "--limit", "1", "--json", "status,conclusion"])
        if ok:
            try:
                import json

                run = json.loads(detail or "[]")
                status = run[0]["status"] if run else None
                conclusion = run[0].get("conclusion") if run else None
            except (ValueError, KeyError, IndexError):
                status, conclusion = None, None
            if status == "completed":
                if conclusion == "success":
                    print(f"[release] CI on {branch}: success", flush=True)
                    return True
                print(f"[release] CI on {branch}: {conclusion}", flush=True)
                return False
        time.sleep(20)
    print(f"[release] CI on {branch}: timed out", flush=True)
    return False


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_release(version: str, pr: int | None, notes_file: Path | None, workspace: Path) -> int:
    """Execute the SOP end to end; stops at the first failing step."""
    version = version.lstrip("v")
    wheel = f"dist/lightworker-{version}-py3-none-any.whl"
    sdist = f"dist/lightworker-{version}.tar.gz"
    sums = f"SHA256SUMS-v{version}.txt"

    ok, status = _run("git-clean-check", ["git", "status", "--porcelain"], cwd=workspace)
    if not ok or status.strip():
        print("[release] workspace is not clean; commit or remove local changes first", flush=True)
        return 1

    if pr is not None:
        ok, detail = _run("pr-state", ["gh", "pr", "view", str(pr), "--json", "state,mergeable"], cwd=workspace)
        if not ok or '"state":"OPEN"' not in detail.replace(" ", "") or '"mergeable":"MERGEABLE"' not in detail.replace(" ", ""):
            print(f"[release] PR #{pr} is not open/mergeable; refusing to continue", flush=True)
            return 1
        if not _run("pr-merge", ["gh", "pr", "merge", str(pr), "--squash", "--delete-branch"], cwd=workspace)[0]:
            return 1

    if not _run("fetch", ["git", "fetch", "origin", "--prune"], cwd=workspace)[0]:
        return 1
    if not _run("switch-main", ["git", "switch", "main"], cwd=workspace)[0]:
        return 1
    if not _run("pull-main", ["git", "pull", "--rebase", "origin", "main"], cwd=workspace)[0]:
        return 1
    if not bump_version_files(version):
        return 1
    if not _run("commit", ["git", "add", "pyproject.toml", "lightworker/__init__.py"], cwd=workspace)[0]:
        return 1
    if not _run("commit", ["git", "commit", "-m", f"release: v{version}"], cwd=workspace)[0]:
        return 1
    if not _run("push-main", ["git", "push", "origin", "main"], cwd=workspace)[0]:
        return 1
    if not wait_ci("main"):
        return 1
    if not _run("build", ["uv", "build"], cwd=workspace)[0]:
        if not _run("build", [sys.executable, "-m", "build"], cwd=workspace)[0]:
            return 1
    try:
        digest_lines = "".join(
            f"{file_sha256(workspace / name)}  {name}\n" for name in (sdist, wheel)
        )
    except OSError as exc:
        print(f"[release] build artifacts missing: {exc}", flush=True)
        return 1
    (workspace / sums).write_text(digest_lines, encoding="utf-8", newline="")
    print(f"[release] wrote {sums}", flush=True)
    if not _run("tag", ["git", "tag", "-a", f"v{version}", "-m", f"Release v{version}"], cwd=workspace)[0]:
        return 1
    if not _run("push-tag", ["git", "push", "origin", f"v{version}"], cwd=workspace)[0]:
        return 1
    if not wait_ci(f"v{version}"):
        return 1
    release_cmd = [
        "gh", "release", "create", f"v{version}",
        "--title", f"LightWorker v{version}",
        "--notes-file", str(notes_file) if notes_file else "--generate-notes",
        sdist, wheel, sums,
    ]
    ok, detail = _run("github-release", release_cmd, cwd=workspace)
    if not ok:
        return 1
    url = detail.strip().splitlines()[-1] if detail.strip() else f"v{version}"
    print(f"[release] DONE: {url}", flush=True)
    return 0
