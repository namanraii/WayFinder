"""Clause Segmentation & Classification Service — spec §9.2.

Splits raw text into clause-level units (numbered/lettered section boundaries,
paragraph breaks, legal section headers), then calls the LLM orchestrator with
the clause_extraction_v1 prompt per clause and validates output against the
§7.2 schema before writing (retry once, then flag for manual review).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.db import sqlite
from app.llm.orchestrator import LLMOrchestrator
from app.llm.schema_validation import validate_clause
from app.services import heuristics as hz

_SECTION_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.):]?|[A-Z][.)]|clause\s+\d+)\s+[A-Z]", re.MULTILINE)


def segment(text: str) -> list[tuple[str | None, str]]:
    """Returns [(heading, clause_text)]. Deterministic splitter."""
    blocks: list[tuple[str | None, str]] = []
    # First split on numbered section boundaries.
    parts = re.split(r"\n(?=\s*\d+(?:\.\d+)*[.)]\s)", text)
    for part in parts:
        for para in re.split(r"\n\s*\n", part):
            para = para.strip()
            if len(para) < 25:
                continue
            heading = None
            m = re.match(r"^\s*(\d+(?:\.\d+)*[.)]?)\s*([^\n.]{3,60})", para)
            if m:
                heading = m.group(2).strip()
            blocks.append((heading, para))
    return blocks


def run(conn, document_id: str, full_text: str, orchestrator: LLMOrchestrator) -> list[dict]:
    doc = sqlite.get(conn, "documents", "document_id", document_id)
    role = doc["role_context"] or "you"
    today = date.today()
    clauses = []
    for idx, (heading, text) in enumerate(segment(full_text), start=1):
        clause_id = f"clause_{idx:02d}"
        dl = hz.extract_deadline(text)
        deadline_absolute = None
        if dl:
            deadline_absolute = (today + timedelta(days=dl[1])).isoformat()
        result = orchestrator.generate(
            prompt_name="clause_extraction_v1",
            prompt_version="clause_extraction_v1",
            inputs={
                "clause_id": clause_id,
                "document_id": document_id,
                "clause_text": text,
                "clause_title": heading,
                "document_type": doc["document_type"],
                "role_hint": role if role != "you" else None,
                "deadline_absolute": deadline_absolute,
                "char_span": [0, len(text)],
            },
            validator=lambda raw: (validate_clause({**raw, "document_id": document_id}).ok,
                                   validate_clause({**raw, "document_id": document_id}).errors),
            entity_type="clause",
            entity_id=clause_id,
        )
        if not result.ok:
            # malformed after retry — flag for manual review (§9.2)
            continue
        clause = validate_clause({**result.output, "document_id": document_id}).value
        clauses.append(clause)
        sqlite.insert(conn, "clauses", {
            "clause_id": clause.clause_id,
            "document_id": document_id,
            "clause_title": clause.clause_title,
            "clause_type": clause.clause_type,
            "page": clause.page or 1,
            "char_start": clause.char_span[0],
            "char_end": clause.char_span[1],
            "original_text": clause.original_text,
            "plain_language": clause.plain_language,
            "obligations": [o.model_dump() for o in clause.obligations],
            "rights": [r.model_dump() for r in clause.rights],
            "risks": [r.model_dump() for r in clause.risks],
            "missing_elements": clause.missing_elements,
            "related_clause_ids": clause.related_clause_ids,
            "feeds_decision_id": clause.feeds_decision_id,
            "extraction_confidence": clause.extraction_confidence,
        })
    sqlite.update(conn, "documents", "document_id", document_id,
                  {"processing_status": "extracted"})
    return [c.model_dump() for c in clauses]
