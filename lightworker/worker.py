from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .config import Config, resolve_executable
from .models import RunResult, TaskSpec


EventCallback = Callable[[str, dict[str, Any]], None]
PidCallback = Callable[[int], None]
CancelCheck = Callable[[], bool]


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|authorization)(\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)
_SECRET_FIELD = re.compile(r"(?i)^(api[_-]?key|token|secret|authorization|password)$")


def redact_text(value: str) -> str:
    result = value
    result = _SECRET_PATTERNS[0].sub(r"\1\2<REDACTED>", result)
    result = _SECRET_PATTERNS[1].sub("Bearer <REDACTED>", result)
    result = _SECRET_PATTERNS[2].sub("<REDACTED>", result)
    return result


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): "<REDACTED>" if _SECRET_FIELD.fullmatch(str(key)) else redact_value(item)
            for key, item in value.items()
        }
    return value


def parse_json_candidate(raw: str) -> dict[str, Any] | None:
    candidates = [raw.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1].strip())
    for candidate in candidates:
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def is_generic_result(value: dict[str, Any]) -> bool:
    required = {"status", "summary", "evidence", "changed_files", "tests", "risks", "followups"}
    if set(value) != required:
        return False
    if value["status"] not in {"completed", "blocked", "failed"} or not isinstance(
        value["summary"], str
    ):
        return False
    string_lists = ("changed_files", "risks", "followups")
    if not all(isinstance(value[key], list) for key in string_lists):
        return False
    if not all(isinstance(item, str) for key in string_lists for item in value[key]):
        return False
    if not isinstance(value["evidence"], list) or not isinstance(value["tests"], list):
        return False
    for item in value["evidence"]:
        if not isinstance(item, dict) or set(item) != {"file", "line", "finding"}:
            return False
        line = item["line"]
        if not isinstance(item["file"], str) or not isinstance(item["finding"], str):
            return False
        if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
            return False
    for item in value["tests"]:
        if not isinstance(item, dict) or set(item) != {"command", "status", "summary"}:
            return False
        if not all(isinstance(item[key], str) for key in ("command", "status", "summary")):
            return False
    return True


def _reader(stream: Any, source: str, output: queue.Queue[tuple[str, str]]) -> None:
    try:
        for line in iter(stream.readline, ""):
            output.put((source, line.rstrip("\r\n")))
    finally:
        stream.close()


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def build_prompt(spec: TaskSpec) -> str:
    allowed = "\n".join(f"- {item}" for item in spec.allowed_paths) or "- Entire workspace"
    prohibited = "\n".join(f"- {item}" for item in spec.prohibited_actions) or "- No external writes or scope expansion"
    criteria = "\n".join(f"- {item}" for item in spec.success_criteria) or "- Provide evidence-backed results"
    role = {
        "plan": "Lead Planner",
        "explore": "Read-only Explorer",
        "execute": "Isolated Executor",
        "review": "Independent Reviewer",
    }[spec.kind]
    special = ""
    if spec.kind == "plan":
        special = f"""
Create a dependency-aware task DAG with no more than {spec.metadata.get('max_tasks', 6)} tasks.
Use only the model ids listed in the routing policy included below. Do not perform the work yourself.
Execution mode is {spec.mode}. In plan_only or auto_readonly mode, you may propose execute tasks; the runner will hold them for approval.
"""
    elif spec.kind in {"explore", "review"}:
        special = "Do not modify files. Cite concrete files, symbols, commands, and evidence."
    elif spec.kind == "execute":
        special = "Make the smallest in-scope change, run relevant tests, and do not commit, push, or merge."
    routing = spec.metadata.get("routing_policy", {})
    routing_text = json.dumps(routing, ensure_ascii=False, indent=2) if routing else "{}"
    return f"""You are the {role} in a bounded multi-agent workflow.

Objective:
{spec.objective}

Workspace:
{spec.workspace}

Allowed paths:
{allowed}

Prohibited actions:
{prohibited}

Success criteria:
{criteria}

Routing policy:
{routing_text}

{special}

Return only the JSON object required by the supplied output schema. Be explicit about uncertainty and missing evidence.
"""


class CodexWorker:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def available(self) -> bool:
        return resolve_executable(self.cfg.codex_command) is not None

    def _command_prefix(self) -> list[str] | None:
        executable = resolve_executable(self.cfg.codex_command)
        if not executable:
            return None
        path = Path(executable)
        if os.name == "nt" and path.suffix.lower() == ".cmd":
            script = path.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            node = path.parent / "node.exe"
            node_command = str(node) if node.exists() else resolve_executable("node")
            if script.exists() and node_command:
                return [node_command, str(script)]
        return [executable]

    def run(
        self,
        task_id: str,
        spec: TaskSpec,
        cwd: str | Path,
        on_event: EventCallback,
        on_pid: PidCallback,
        is_cancelled: CancelCheck,
    ) -> RunResult:
        result_path = self.cfg.results_dir / f"{task_id}.json"
        schema_name = "plan.schema.json" if spec.kind == "plan" else "result.schema.json"
        schema_path = self.cfg.schemas_dir / schema_name
        prefix = self._command_prefix()
        if not prefix:
            return RunResult(status="failed", error=f"Codex command not found: {self.cfg.codex_command}")
        args = [
            *prefix,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            spec.sandbox,
            "--cd",
            str(Path(cwd).resolve()),
            "--model",
            spec.model,
            "--config",
            f'model_reasoning_effort="{spec.reasoning_effort}"',
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(result_path),
        ]
        if self.cfg.codex_ignore_user_config:
            args.append("--ignore-user-config")
            if self.cfg.codex_base_url:
                args.extend(["--config", f'openai_base_url="{self.cfg.codex_base_url}"'])
            if self.cfg.codex_model_catalog:
                catalog = str(Path(self.cfg.codex_model_catalog).expanduser().resolve()).replace("\\", "\\\\")
                args.extend(["--config", f'model_catalog_json="{catalog}"'])
        if not (Path(cwd) / ".git").exists():
            args.append("--skip-git-repo-check")
        args.append("-")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "NO_COLOR": "1",
            }
        )
        kwargs: dict[str, Any] = {
            "cwd": str(Path(cwd).resolve()),
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
            "creationflags": creationflags,
            "env": environment,
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen(args, **kwargs)
        on_pid(process.pid)
        assert process.stdin is not None
        process.stdin.write(build_prompt(spec))
        process.stdin.close()
        output: queue.Queue[tuple[str, str]] = queue.Queue()
        threads = [
            threading.Thread(target=_reader, args=(process.stdout, "stdout", output), daemon=True),
            threading.Thread(target=_reader, args=(process.stderr, "stderr", output), daemon=True),
        ]
        for thread in threads:
            thread.start()
        started = time.monotonic()
        last_agent_message: str | None = None
        cancelled = False
        timed_out = False
        while process.poll() is None or any(thread.is_alive() for thread in threads) or not output.empty():
            if is_cancelled() and process.poll() is None:
                cancelled = True
                _terminate_process_tree(process)
            if time.monotonic() - started > spec.timeout_seconds and process.poll() is None:
                timed_out = True
                _terminate_process_tree(process)
            try:
                source, line = output.get(timeout=0.1)
            except queue.Empty:
                continue
            if not line:
                continue
            if source == "stdout":
                try:
                    event = redact_value(json.loads(line))
                    event_type = str(event.get("type", "worker.event"))
                    on_event(event_type, event)
                    item = event.get("item") or {}
                    if item.get("type") == "agent_message" and item.get("text"):
                        last_agent_message = str(item["text"])
                except json.JSONDecodeError:
                    on_event("worker.stdout", {"text": redact_text(line)})
            else:
                on_event("worker.stderr", {"text": redact_text(line)})
        exit_code = process.wait()
        if cancelled:
            return RunResult(status="cancelled", error="Task was cancelled", exit_code=exit_code)
        if timed_out:
            return RunResult(status="failed", error="Task timed out", exit_code=exit_code)
        if exit_code != 0:
            return RunResult(status="failed", error=f"Codex exited with code {exit_code}", exit_code=exit_code)
        raw = result_path.read_text(encoding="utf-8") if result_path.exists() else (last_agent_message or "")
        result = parse_json_candidate(raw)
        if result is not None:
            result = redact_value(result)
            if result_path.exists():
                result_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
        else:
            raw = redact_text(raw)
            if result_path.exists():
                result_path.write_text(raw, encoding="utf-8")
        if result is None:
            if spec.kind != "plan" and raw.strip():
                return RunResult(
                    status="completed",
                    result={
                        "status": "completed",
                        "summary": raw.strip(),
                        "evidence": [],
                        "changed_files": [],
                        "tests": [],
                        "risks": ["Worker returned text instead of the required JSON schema"],
                        "followups": ["Use an independent reviewer when structured evidence is required"],
                        "schema_valid": False,
                        "raw_text": raw.strip(),
                    },
                    exit_code=exit_code,
                    result_path=str(result_path) if result_path.exists() else None,
                )
            return RunResult(
                status="failed",
                error="Final result did not contain a valid JSON object",
                exit_code=exit_code,
                result_path=str(result_path) if result_path.exists() else None,
            )
        if spec.kind != "plan" and not is_generic_result(result):
            return RunResult(
                status="completed",
                result={
                    "status": str(result.get("status", "completed")),
                    "summary": str(result.get("summary") or raw.strip()),
                    "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
                    "changed_files": result.get("changed_files") if isinstance(result.get("changed_files"), list) else [],
                    "tests": result.get("tests") if isinstance(result.get("tests"), list) else [],
                    "risks": ["Worker JSON did not match the required result schema"],
                    "followups": ["Use an independent reviewer when structured evidence is required"],
                    "schema_valid": False,
                    "raw_json": result,
                },
                exit_code=exit_code,
                result_path=str(result_path) if result_path.exists() else None,
            )
        result["schema_valid"] = True
        return RunResult(
            status="completed",
            result=result,
            exit_code=exit_code,
            result_path=str(result_path),
        )
