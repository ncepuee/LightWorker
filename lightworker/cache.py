
"""Deterministic, explicit cache inputs for LightWorker.

This module deliberately never opens a workspace or expands a path.  A context
pack is caller-supplied text only, so adding caching cannot accidentally feed a
repository's secrets, logs, or instructions into a shared upstream cache.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


CONTEXT_PACK_DEFAULT_NAME = "inline"
CONTEXT_PACK_DEFAULT_VERSION = "context-pack.v1"
CONTEXT_PACK_MAX_BYTES = 32 * 1024
CACHE_WINDOW_MAX_SECONDS = 31 * 24 * 60 * 60
CACHE_COHORT_VERSION = "cache_cohort.v2"
PROMPT_PROTOCOL_VERSION = "lightworker.prompt.v4"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LIKELY_SECRET = re.compile(
    r"(?ix)(?:"
    r"[\"']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization)[\"']?"
    r"\s*[:=]\s*[\"']?(?!<REDACTED>)[^\"'\s,;]+"
    r"|bearer\s+(?!<REDACTED>)[A-Za-z0-9._~+/=-]{12,}"
    r"|\b(?:sk-|cpa-(?:local|admin)-|ark-)[A-Za-z0-9_-]{12,}\b"
    r")"
)


def canonical_lf(value: str) -> str:
    """Normalize line endings without reading or interpreting external data."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def canonical_json(value: Any) -> str:
    """Return one stable JSON representation for cache-key input."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"context pack {field} must be 1-128 safe identifier characters")
    return value


@dataclass(frozen=True, slots=True)
class ContextPack:
    """A bounded immutable, caller-provided prompt prefix.

    ``content`` is intentionally not returned by :func:`public_task`; it is
    persisted solely with the task specification so retries retain precisely
    the same input.
    """

    name: str
    version: str
    content: str
    sha256: str

    @property
    def bytes(self) -> int:
        return len(self.content.encode("utf-8"))

    def task_fields(self) -> dict[str, str]:
        return {
            "context_pack_name": self.name,
            "context_pack_version": self.version,
            "context_pack_content": self.content,
            "context_pack_hash": self.sha256,
        }


def normalize_context_pack(value: None | str | Mapping[str, Any]) -> ContextPack | None:
    """Validate an explicit pack and return its canonical, hashed form.

    Strings are convenient for local callers.  Mappings must contain exactly
    ``name``, ``version``, and ``content`` so unreviewed fields can never
    silently influence an upstream prompt or the cache key.
    """
    if value is None:
        return None
    if isinstance(value, str):
        name = CONTEXT_PACK_DEFAULT_NAME
        version = CONTEXT_PACK_DEFAULT_VERSION
        content = value
    elif isinstance(value, Mapping):
        expected = {"name", "version", "content"}
        keys = set(value)
        if keys != expected:
            missing = sorted(expected - keys)
            unexpected = sorted(keys - expected)
            details = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected {', '.join(unexpected)}")
            raise ValueError(f"context pack must contain only name, version, content ({'; '.join(details)})")
        name = _identifier(value["name"], "name")
        version = _identifier(value["version"], "version")
        content = value["content"]
    else:
        raise ValueError("context pack must be null, a string, or an object")
    if not isinstance(content, str):
        raise ValueError("context pack content must be a string")
    content = canonical_lf(content)
    size = len(content.encode("utf-8"))
    if size > CONTEXT_PACK_MAX_BYTES:
        raise ValueError(f"context pack exceeds the {CONTEXT_PACK_MAX_BYTES} byte limit")
    if _LIKELY_SECRET.search(content):
        raise ValueError("context pack appears to contain a credential; redact it before submission")
    # The hash covers the declared format as well as its text.  A pack format
    # upgrade must never be considered interchangeable just because a small
    # fixture happened to retain identical content.
    digest = sha256_text(canonical_json({"name": name, "version": version, "content": content}))
    return ContextPack(name=name, version=version, content=content, sha256=digest)


def cache_cohort_v2(
    *,
    gateway: str,
    response_mode: str,
    upstream_model: str,
    reasoning_effort: str,
    profile: str | None,
    profile_contract_hash: str,
    prompt_protocol: str,
    schema_hash: str,
    sandbox: str,
    context_pack_hash: str | None,
    config_scope: str | Mapping[str, Any],
    tool_contract: str | Mapping[str, Any],
) -> str:
    """Create a strict opaque v2 cache cohort key.

    Cache evidence must never be merged merely because two requests name the
    same model.  The returned opaque hash is safe to expose in task metadata;
    the canonical preimage is intentionally not persisted or displayed.
    """
    required = {
        "gateway": gateway,
        "response_mode": response_mode,
        "upstream_model": upstream_model,
        "reasoning_effort": reasoning_effort,
        "profile_contract_hash": profile_contract_hash,
        "prompt_protocol": prompt_protocol,
        "schema_hash": schema_hash,
        "sandbox": sandbox,
    }
    for field, item in required.items():
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"cache cohort {field} must be a non-empty string")
    if context_pack_hash is not None and (not isinstance(context_pack_hash, str) or not context_pack_hash):
        raise ValueError("cache cohort context_pack_hash must be null or a non-empty string")
    payload = {
        "version": CACHE_COHORT_VERSION,
        "gateway": canonical_lf(gateway).strip(),
        "response_mode": canonical_lf(response_mode).strip(),
        "upstream_model": canonical_lf(upstream_model).strip(),
        "reasoning_effort": canonical_lf(reasoning_effort).strip(),
        "profile": canonical_lf(profile).strip() if profile else "legacy",
        "profile_contract_hash": canonical_lf(profile_contract_hash).strip(),
        "prompt_protocol": canonical_lf(prompt_protocol).strip(),
        "schema_hash": canonical_lf(schema_hash).strip(),
        "sandbox": canonical_lf(sandbox).strip(),
        "context_pack_hash": canonical_lf(context_pack_hash).strip() if context_pack_hash else None,
        "config_scope": config_scope,
        "tool_contract": tool_contract,
    }
    return f"{CACHE_COHORT_VERSION}:{sha256_text(canonical_json(payload))}"


def configure_task_cache(cfg: Any, spec: Any, context_pack: object = ...) -> None:
    """Attach an explicit Context Pack and strict cohort to a resolved TaskSpec.

    ``...`` means preserve an existing pack (retries/escalations). Passing None
    deliberately clears it. This function never reads workspace files.
    """
    if context_pack is not ...:
        pack = normalize_context_pack(context_pack)  # type: ignore[arg-type]
        spec.context_pack_name = pack.name if pack else None
        spec.context_pack_version = pack.version if pack else None
        spec.context_pack_content = pack.content if pack else None
        spec.context_pack_hash = pack.sha256 if pack else None
    schema_name = "plan.schema.json" if spec.kind == "plan" else "result.schema.json"
    schema_path = cfg.schemas_dir / schema_name
    schema_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    profile = cfg.worker_profiles.get(spec.profile) if spec.profile else None
    contract = profile.description if profile else str(spec.metadata.get("profile_description") or "legacy")
    contract_hash = sha256_text(canonical_lf(contract).strip())
    gateway_config = cfg.gateway_config(str(spec.gateway or "legacy"))
    config_scope = {
        "declared": cfg.cache_config_scope,
        "isolated_user_config": bool(cfg.codex_ignore_user_config),
        "gateway_endpoint": gateway_config.base_url,
        "model_catalog": gateway_config.model_catalog,
    }
    spec.cache_cohort = cache_cohort_v2(
        gateway=str(spec.gateway or "legacy"),
        response_mode=str(spec.response_mode or "native"),
        upstream_model=str(spec.upstream_model or spec.model),
        reasoning_effort=str(spec.reasoning_effort),
        profile=spec.profile,
        profile_contract_hash=contract_hash,
        prompt_protocol=PROMPT_PROTOCOL_VERSION,
        schema_hash=schema_hash,
        sandbox=str(spec.sandbox),
        context_pack_hash=spec.context_pack_hash,
        config_scope=config_scope,
        tool_contract=cfg.cache_tool_contract,
    )
    spec.metadata = {
        **spec.metadata,
        "cache_cohort_version": CACHE_COHORT_VERSION,
        "context_pack_bytes": len((spec.context_pack_content or "").encode("utf-8")),
        "profile_contract_sha256": contract_hash,
        "schema_sha256": schema_hash,
    }
