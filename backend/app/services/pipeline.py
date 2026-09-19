"""Synchronous local implementation of the §9.1 ingestion job chain."""
from __future__ import annotations

from app.db import sqlite
from app.services import clause_extraction, deadline_tracker, decision_extraction, document_graph, ingestion, triage
from app.llm.orchestrator import LLMOrchestrator


def run(conn, document_id: str, orchestrator: LLMOrchestrator | None = None):
    orchestrator = orchestrator or LLMOrchestrator()
    try:
        text = ingestion.run(conn, document_id)
        clauses = clause_extraction.run(conn, document_id, text, orchestrator)
        document_graph.build(conn, document_id, clauses)
        decisions = decision_extraction.run(conn, document_id, orchestrator)
        decisions = triage.run(conn, document_id)
        deadline_tracker.sync_for_document(conn, document_id)
        sqlite.update(conn, "documents", "document_id", document_id, {"processing_status": "decisions_ready"})
        return decisions
    except Exception:
        sqlite.update(conn, "documents", "document_id", document_id, {"processing_status": "failed"})
        raise

