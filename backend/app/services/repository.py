"""Small repository helpers for the SQLite MVP store.

The SQL schema intentionally mirrors the production Postgres columns, while
SQLite stores JSON/arrays as text.  Keeping that conversion in one place makes
the service and API layers work with the authoritative Pydantic schemas rather
than with database-shaped dictionaries.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from app.db import sqlite
from app.llm.guardrails import DISCLAIMER
from app.models import (
    Clause,
    ComparisonResult,
    Consent,
    DeadlineTrackerEntry,
    DecisionPoint,
    Document,
    Jurisdiction,
    PrepPack,
    ResolutionArtifact,
)


def utcnow() -> datetime:
    """Return a timezone-aware timestamp suitable for model/API output."""
    return datetime.now(timezone.utc)


def document_from_row(conn, row: dict[str, Any]) -> Document:
    user = sqlite.get(conn, "users", "user_id", row["user_id"]) or {}
    jurisdiction_status = row.get("jurisdiction_status") or "unknown"
    jurisdiction_source = row.get("jurisdiction_source") or "none"
    return Document(
        document_id=row["document_id"],
        user_id=row["user_id"],
        uploaded_at=row.get("uploaded_at"),
        original_filename=row.get("original_filename"),
        storage_uri=row["storage_uri"],
        mime_type=row.get("mime_type"),
        page_count=row.get("page_count"),
        language_detected=row.get("language_detected"),
        document_type=row.get("document_type"),
        document_type_confidence=row.get("document_type_confidence"),
        jurisdiction=Jurisdiction(
            status=jurisdiction_status,
            country=row.get("jurisdiction_country"),
            state_or_region=row.get("jurisdiction_region"),
            source=jurisdiction_source,
        ),
        role_context=row.get("role_context"),
        processing_status=row.get("processing_status") or "ingested",
        consent=Consent(
            consented_at=row.get("consented_at"),
            training_opt_in=bool(user.get("training_opt_in", False)),
        ),
    )


def clause_from_row(row: dict[str, Any]) -> Clause:
    return Clause(
        clause_id=row["clause_id"],
        document_id=row["document_id"],
        clause_title=row.get("clause_title"),
        clause_type=row.get("clause_type") or "general",
        page=row.get("page"),
        char_span=(int(row.get("char_start") or 0), int(row.get("char_end") or 0)),
        original_text=row.get("original_text") or "",
        plain_language=row.get("plain_language"),
        obligations=sqlite.decode_json(row.get("obligations"), []),
        rights=sqlite.decode_json(row.get("rights"), []),
        risks=sqlite.decode_json(row.get("risks"), []),
        missing_elements=sqlite.decode_json(row.get("missing_elements"), []),
        related_clause_ids=sqlite.decode_json(row.get("related_clause_ids"), []),
        feeds_decision_id=row.get("feeds_decision_id"),
        extraction_confidence=float(row.get("extraction_confidence") or 0.0),
    )


def days_remaining(deadline: Optional[str]) -> Optional[int]:
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline) - date.today()).days
    except (TypeError, ValueError):
        return None


def decision_from_row(row: dict[str, Any]) -> DecisionPoint:
    return DecisionPoint(
        decision_id=row["decision_id"],
        document_id=row["document_id"],
        title=row["title"],
        triggering_clause_ids=sqlite.decode_json(row.get("triggering_clause_ids"), []),
        deadline=row.get("deadline"),
        days_remaining=days_remaining(row.get("deadline")),
        options=sqlite.decode_json(row.get("options"), []),
        triage_tier=row.get("triage_tier"),
        triage_scores=sqlite.decode_json(row.get("triage_scores"), None),
        triage_reasoning=row.get("triage_reasoning"),
        resolution_artifact_id=row.get("resolution_artifact_id"),
        confidence=row.get("confidence") or "medium",
        jurisdiction_confidence_note=row.get("jurisdiction_confidence_note"),
        source_spans=sqlite.decode_json(row.get("source_spans"), []),
    )


def artifact_from_row(row: dict[str, Any]) -> ResolutionArtifact:
    return ResolutionArtifact(
        artifact_id=row["artifact_id"],
        decision_id=row["decision_id"],
        type=row.get("type") or "draft",
        status=row.get("status") or "draft",
        content=row.get("content") or "",
        fields_to_fill=sqlite.decode_json(row.get("fields_to_fill"), []),
        generated_at=row.get("generated_at"),
        disclaimer=DISCLAIMER,
        model_version=row.get("model_version"),
        prompt_version=row.get("prompt_version"),
    )


def prep_pack_from_row(row: dict[str, Any]) -> PrepPack:
    return PrepPack(
        prep_pack_id=row["prep_pack_id"],
        decision_id=row["decision_id"],
        contents=sqlite.decode_json(row.get("contents"), {}),
        export_formats=["pdf", "share_link"],
    )


def tracker_from_row(row: dict[str, Any]) -> DeadlineTrackerEntry:
    return DeadlineTrackerEntry(
        tracker_id=row["tracker_id"],
        decision_id=row["decision_id"],
        deadline=row["deadline"],
        resolving_action=row.get("resolving_action"),
        inaction_consequence_short=row.get("inaction_consequence_short"),
        reminder_schedule=sqlite.decode_json(row.get("reminder_schedule"), ["T-7d", "T-3d", "T-1d"]),
        status=row.get("status") or "open",
        # Local exports are generated on demand; this stable API path is the
        # equivalent of the production object-storage URI.
        calendar_export_ics_uri=f"/tracker/{row['tracker_id']}/export.ics",
    )


def load_document(conn, document_id: str) -> Optional[Document]:
    row = sqlite.get(conn, "documents", "document_id", document_id)
    return document_from_row(conn, row) if row else None


def load_clauses(conn, document_id: str) -> list[Clause]:
    rows = sqlite.query(
        conn,
        "SELECT * FROM clauses WHERE document_id = ? ORDER BY page, char_start, clause_id",
        (document_id,),
    )
    return [clause_from_row(row) for row in rows]


def load_decision(conn, decision_id: str) -> Optional[DecisionPoint]:
    row = sqlite.get(conn, "decisions", "decision_id", decision_id)
    return decision_from_row(row) if row else None


def load_decisions(conn, document_id: str) -> list[DecisionPoint]:
    rows = sqlite.query(
        conn,
        "SELECT * FROM decisions WHERE document_id = ? ORDER BY deadline IS NULL, deadline, created_at, decision_id",
        (document_id,),
    )
    return [decision_from_row(row) for row in rows]
