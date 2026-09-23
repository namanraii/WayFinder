"""LLM Orchestrator — spec §9.3.

Thin, vendor-agnostic wrapper responsible for:
- prompt templating + versioning (every prompt has a version string, logged)
- schema-validated structured output (reject-and-retry on validation failure)
- centralized guardrail enforcement (banned-phrase, citation, tier gate) run
  on every generation BEFORE it is written to the database
- audit logging of every generation call (§17 generation_audit_log, §18.9)
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

from app.db import sqlite
from app.llm import guardrails

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=64)
def _load_prompt_cached(prompt_name: str) -> str:
    """Read and cache prompt file contents — avoids repeated disk I/O per request."""
    path = PROMPTS_DIR / f"{prompt_name}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@dataclass
class GenerationResult:
    ok: bool
    output: Any = None
    errors: list[str] = field(default_factory=list)
    blocked: bool = False  # guardrail block after retry
    model_version: str = ""
    prompt_version: str = ""
    guardrail_checks: dict = field(default_factory=dict)


class LLMOrchestrator:
    def __init__(self, provider=None, audit: bool = True):
        if provider is None:
            from app.llm.providers import default_provider

            provider = default_provider()
        self.provider = provider
        self.model_version = getattr(provider, "model_version", "unknown")
        self.audit = audit

    def load_prompt(self, prompt_name: str) -> str:
        """Return cached prompt text — first call reads disk, subsequent calls are O(1)."""
        return _load_prompt_cached(prompt_name)

    def generate(
        self,
        *,
        prompt_name: str,
        prompt_version: str,
        inputs: dict,
        validator: Optional[Callable[[Any], tuple[bool, list[str]]]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        max_retries: int = 1,
    ) -> GenerationResult:
        prompt_text = self.load_prompt(prompt_name)
        attempts: list[str] = []
        for attempt in range(max_retries + 1):
            if attempt > 0:
                # error-correction follow-up (§9.2): feed validation errors back
                inputs = {**inputs, "_correction": "; ".join(attempts)}
            raw = self.provider.complete(
                prompt_name=prompt_name, prompt_text=prompt_text, inputs=inputs
            )
            checks = {
                "banned_phrases": guardrails.find_banned_phrases(json.dumps(raw, default=str)),
            }
            if checks["banned_phrases"]:
                attempts.append(f"banned phrasing present: {checks['banned_phrases']}")
                continue
            if validator is not None:
                ok, errors = validator(raw)
                if not ok:
                    attempts.extend(errors)
                    continue
            result = GenerationResult(
                ok=True,
                output=raw,
                model_version=self.model_version,
                prompt_version=prompt_version,
                guardrail_checks={k: (not v if isinstance(v, list) else v) for k, v in checks.items()},
            )
            self._audit(entity_type, entity_id, prompt_version, result.guardrail_checks)
            return result

        # exhausted retries — blocked and flagged for manual review (§18.2)
        result = GenerationResult(
            ok=False,
            blocked=True,
            errors=attempts,
            model_version=self.model_version,
            prompt_version=prompt_version,
            guardrail_checks={"passed": False},
        )
        self._audit(entity_type, entity_id, prompt_version, result.guardrail_checks)
        return result

    def _audit(self, entity_type, entity_id, prompt_version, checks: dict) -> None:
        if not self.audit:
            return
        try:
            # Reuse the thread-local connection — avoids opening a new
            # connection for every audit log entry during pipeline runs.
            conn = sqlite.connect()
            sqlite.insert(conn, "generation_audit_log", {
                "audit_id": f"aud_{uuid.uuid4().hex[:10]}",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "model_version": self.model_version,
                "prompt_version": prompt_version,
                "guardrail_checks_passed": checks,
            })
            conn.commit()
        except Exception:
            pass  # audit failure must never crash a generation path

