"""Resolution Artifact and Prep Pack service (spec §§7.5–7.6, 14.3).

Drafts are deliberately template fills, not free-form legal argument.  The
service also has its own tier check as defense in depth; the REST endpoint
checks before calling it so a blocked request never reaches the LLM.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.db import sqlite
from app.llm import guardrails
from app.llm.orchestrator import LLMOrchestrator
from app.models import DecisionPoint, PrepPack, ResolutionArtifact
from app.services.repository import (
    artifact_from_row,
    load_clauses,
    load_decision,
    load_document,
    prep_pack_from_row,
    utcnow,
)

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

# Precompiled regexes to avoid re-compilation on every artifact generation
_FIRST_DATE_ISO = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_FIRST_DATE_SLASH = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]20\d{2})\b")
_MONEY_RE = re.compile(r"(?:₹|\$|USD\s?|INR\s?)[\d,]+(?:\.\d{2})?", re.IGNORECASE)

# Fixed field lists are intentionally kept beside the template IDs.  They are
# the contract passed to the model and prevent it from filling arbitrary facts.
TEMPLATE_FIELDS: dict[str, list[str]] = {
    "objection_letter_v1": ["authority_name", "tenant_name", "date", "notice_date", "objection_grounds"],
    "clarification_email_v1": ["recipient", "clause_reference", "specific_question", "sender_name"],
    "formal_notice_v1": ["recipient", "sender", "date", "effective_date", "reason"],
    "deposit_itemization_request_v1": ["landlord_name", "tenant_name", "date", "deposit_amount", "move_out_date"],
    "arbitration_optout_v1": ["service_name", "account_identifier", "date", "opt_out_deadline"],
    "data_deletion_request_v1": ["service_name", "account_identifier", "date", "applicable_regulation_reference"],
}


class ArtifactGenerationBlocked(PermissionError):
    """Raised when a decision's deterministic triage tier forbids a draft."""

    def __init__(self, triage_tier: Optional[str]):
        self.triage_tier = triage_tier
        super().__init__(f"Draft artifact generation is not permitted for tier {triage_tier!r}")


def template_for_decision(conn, decision_id: str, decision: Optional[DecisionPoint] = None) -> str:
    """Select a fixed template from document-derived clause types only."""
    decision = decision or load_decision(conn, decision_id)
    if decision is None:
        raise KeyError(f"Decision {decision_id!r} was not found")
    clauses = {c.clause_id: c for c in load_clauses(conn, decision.document_id)}
    selected = [clauses[cid] for cid in decision.triggering_clause_ids if cid in clauses]
    types = {clause.clause_type for clause in selected}
    text = " ".join(c.original_text.lower() for c in selected)

    if "arbitration_optout" in types:
        return "arbitration_optout_v1"
    if any(term in text for term in ("delete my data", "data deletion", "erase personal data", "privacy request")):
        return "data_deletion_request_v1"
    if "deposit" in text or "security deposit" in text:
        return "deposit_itemization_request_v1"
    if "termination" in types and "notice" in text:
        return "formal_notice_v1"
    if any(term in text for term in ("unclear", "clarify", "ambigu")):
        return "clarification_email_v1"
    return "objection_letter_v1"


@lru_cache(maxsize=16)
def _read_template(template_id: str) -> str:
    """Cached template reader to eliminate repetitive disk I/O."""
    if template_id not in TEMPLATE_FIELDS:
        raise ValueError(f"Unsupported template_id {template_id!r}")
    path = TEMPLATES_DIR / f"{template_id}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Template file is missing: {path}")
    return path.read_text(encoding="utf-8").strip()


def _first_date(text: str) -> Optional[str]:
    """Find an explicit ISO/slash-style date without inventing a date."""
    m = _FIRST_DATE_ISO.search(text)
    if m:
        return m.group(1)
    m = _FIRST_DATE_SLASH.search(text)
    return m.group(1) if m else None


def _money(text: str) -> Optional[str]:
    match = _MONEY_RE.search(text)
    return match.group(0) if match else None


def extract_facts(conn, decision_id: str, option_id: Optional[str] = None, decision: Optional[DecisionPoint] = None) -> dict[str, str]:
    """Extract only document-supported values for a fixed template.

    Names and account numbers are intentionally not guessed.  Their bracketed
    placeholders are returned through ``fields_to_fill`` for the user.
    """
    decision = decision or load_decision(conn, decision_id)
    if decision is None:
        raise KeyError(f"Decision {decision_id!r} was not found")
    doc = load_document(conn, decision.document_id)
    clauses_by_id = {c.clause_id: c for c in load_clauses(conn, decision.document_id)}
    clauses = [clauses_by_id[cid] for cid in decision.triggering_clause_ids if cid in clauses_by_id]
    joined_text = "\n".join(c.original_text for c in clauses)
    first_clause = clauses[0] if clauses else None
    facts: dict[str, str] = {"date": date.today().isoformat()}

    if first_clause:
        facts["clause_reference"] = first_clause.clause_title or first_clause.clause_id
        # This is a faithful clause summary from extraction, not a user-specific
        # argument.  A user can edit it before sending.
        if first_clause.plain_language:
            facts["objection_grounds"] = first_clause.plain_language
    explicit_date = _first_date(joined_text)
    if explicit_date:
        facts["notice_date"] = explicit_date
        facts["move_out_date"] = explicit_date
    amount = _money(joined_text)
    if amount:
        facts["deposit_amount"] = amount
    if decision.deadline:
        facts["opt_out_deadline"] = decision.deadline

    # The choice is grounded in the decision options, but it is not placed into
    # a template field unless a template explicitly asks for it.
    if option_id:
        matching = next((opt for opt in decision.options if opt.option_id == option_id), None)
        if matching is None:
            raise ValueError(f"Option {option_id!r} is not part of this decision")

    # Keep this read so a missing document is surfaced early rather than after
    # an artifact has been generated.  It also makes future party extraction
    # naturally available without changing the public service contract.
    if doc is None:
        raise KeyError(f"Document {decision.document_id!r} was not found")
    return facts


def _validate_artifact_output(raw: Any) -> tuple[bool, list[str]]:
    if not isinstance(raw, dict):
        return False, ["Artifact output must be a JSON object"]
    content = raw.get("content")
    remaining = raw.get("fields_to_fill")
    errors: list[str] = []
    if not isinstance(content, str) or not content.strip():
        errors.append("Artifact content must be a non-empty string")
    if not isinstance(remaining, list) or not all(isinstance(item, str) for item in remaining):
        errors.append("fields_to_fill must be a list of strings")
    return not errors, errors


def _with_disclaimer(content: str) -> str:
    content = content.strip()
    return content if guardrails.DISCLAIMER in content else f"{content}\n\n{guardrails.DISCLAIMER}"


def get_artifact(conn, artifact_id: str) -> Optional[ResolutionArtifact]:
    row = sqlite.get(conn, "resolution_artifacts", "artifact_id", artifact_id)
    return artifact_from_row(row) if row else None


def existing_artifact_for_decision(conn, decision_id: str) -> Optional[ResolutionArtifact]:
    row = sqlite.query(
        conn,
        "SELECT * FROM resolution_artifacts WHERE decision_id = ? ORDER BY generated_at DESC, artifact_id DESC LIMIT 1",
        (decision_id,),
    )
    return artifact_from_row(row[0]) if row else None


def generate_artifact(
    conn,
    decision_id: str,
    *,
    option_id: Optional[str] = None,
    template_id: Optional[str] = None,
    orchestrator: Optional[LLMOrchestrator] = None,
) -> ResolutionArtifact:
    """Generate and persist one editable, send-ready template draft."""
    decision = load_decision(conn, decision_id)
    if decision is None:
        raise KeyError(f"Decision {decision_id!r} was not found")
    if not guardrails.check_tier_gate(decision.triage_tier):
        raise ArtifactGenerationBlocked(decision.triage_tier)

    template_id = template_id or template_for_decision(conn, decision_id, decision=decision)
    structure = _read_template(template_id)
    facts = extract_facts(conn, decision_id, option_id, decision=decision)
    fields = TEMPLATE_FIELDS[template_id]
    artifact_id = f"artifact_{uuid.uuid4().hex[:12]}"
    orchestrator = orchestrator or LLMOrchestrator()
    result = orchestrator.generate(
        prompt_name="artifact_generation_v1",
        prompt_version="artifact_generation_v1",
        inputs={
            "template_id": template_id,
            "template_structure": structure,
            "template_fields": fields,
            "extracted_facts": facts,
            "disclaimer": guardrails.DISCLAIMER,
        },
        validator=_validate_artifact_output,
        entity_type="artifact",
        entity_id=artifact_id,
    )
    if not result.ok:
        raise RuntimeError("Artifact generation was blocked by validation or guardrails: " + "; ".join(result.errors))

    raw = result.output
    artifact = ResolutionArtifact(
        artifact_id=artifact_id,
        decision_id=decision_id,
        type=template_id.removesuffix("_v1"),
        status="draft",
        content=_with_disclaimer(raw["content"]),
        fields_to_fill=sorted(set(raw["fields_to_fill"])),
        generated_at=utcnow(),
        disclaimer=guardrails.DISCLAIMER,
        model_version=result.model_version,
        prompt_version=result.prompt_version,
    )
    sqlite.insert(conn, "resolution_artifacts", {
        "artifact_id": artifact.artifact_id,
        "decision_id": artifact.decision_id,
        "type": artifact.type,
        "status": artifact.status,
        "content": artifact.content,
        "fields_to_fill": artifact.fields_to_fill,
        "generated_at": artifact.generated_at.isoformat(),
        "model_version": artifact.model_version,
        "prompt_version": artifact.prompt_version,
    })
    sqlite.update(conn, "decisions", "decision_id", decision_id, {
        "resolution_artifact_id": artifact.artifact_id,
    })
    return artifact


def get_or_create_prep_pack(conn, decision_id: str) -> PrepPack:
    """Build the safe escalation artifact, available for every triage tier."""
    existing = sqlite.query(
        conn,
        "SELECT * FROM prep_packs WHERE decision_id = ? ORDER BY created_at DESC, prep_pack_id DESC LIMIT 1",
        (decision_id,),
    )
    if existing:
        return prep_pack_from_row(existing[0])

    decision = load_decision(conn, decision_id)
    if decision is None:
        raise KeyError(f"Decision {decision_id!r} was not found")
    doc = load_document(conn, decision.document_id)
    clauses_by_id = {c.clause_id: c for c in load_clauses(conn, decision.document_id)}
    relevant = [clauses_by_id[cid] for cid in decision.triggering_clause_ids if cid in clauses_by_id]
    urgency = (
        f"The document states a deadline of {decision.deadline}."
        if decision.deadline else "No explicit deadline was extracted for this decision."
    )
    contents = {
        "document_summary": (
            f"{doc.original_filename or 'Uploaded document'} was classified as "
            f"{doc.document_type or 'an unclassified document'}. The decision identified is: {decision.title}."
        ) if doc else decision.title,
        "relevant_clause_excerpts": [clause.clause_id for clause in relevant],
        "timeline": ([{"date": decision.deadline, "event": "Document-stated decision deadline"}]
                     if decision.deadline else []),
        "questions_for_professional": [
            "What options are available in light of the document terms and my circumstances?",
            "What evidence or notices should I preserve before the stated deadline?",
        ],
        "what_has_been_tried": [],
        "urgency_note": urgency,
        "disclaimer": guardrails.DISCLAIMER,
    }
    pack = PrepPack(
        prep_pack_id=f"pack_{uuid.uuid4().hex[:12]}",
        decision_id=decision_id,
        contents=contents,
        export_formats=["pdf", "share_link"],
    )
    sqlite.insert(conn, "prep_packs", {
        "prep_pack_id": pack.prep_pack_id,
        "decision_id": pack.decision_id,
        "contents": pack.contents,
    })
    return pack


# An explicit alias makes the API and a future worker queue read naturally.
generate_prep_pack = get_or_create_prep_pack
