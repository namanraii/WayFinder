"""End-to-end integration tests on golden-set documents (spec §21.2, §21.3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db import sqlite
from app.services import pipeline
from app.services.repository import load_clauses, load_decisions, load_document

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden_set"


def _run_pipeline_for_file(conn, file_path: Path, doc_id: str, user_id: str = "usr_e2e") -> str:
    sqlite.insert(conn, "users", {"user_id": user_id, "training_opt_in": 0})
    sqlite.insert(conn, "documents", {
        "document_id": doc_id,
        "user_id": user_id,
        "storage_uri": str(file_path),
        "original_filename": file_path.name,
        "mime_type": "text/plain",
        "role_context": "tenant" if "eviction" in file_path.name else "general",
        "processing_status": "ingested",
        "jurisdiction_status": "unknown",
        "jurisdiction_source": "none",
    })
    pipeline.run(conn, doc_id)
    return doc_id


def test_scenario_a_eviction_notice_e2e(tmp_path, monkeypatch):
    """Scenario A (Eviction Notice):
    Verify extraction finds response deadline, deemed accepted consequence,
    and classifies triage as lawyer_now or legal_aid_recommended."""
    test_db = tmp_path / "test_e2e_a.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)

    eviction_file = GOLDEN_DIR / "scenario_a_eviction_notice.txt"
    expected_spec = json.loads((GOLDEN_DIR / "scenario_a_expected_decisions.json").read_text())

    with sqlite.connect() as conn:
        doc_id = _run_pipeline_for_file(conn, eviction_file, "doc_scenario_a")

        doc = load_document(conn, doc_id)
        assert doc is not None
        assert doc.processing_status == "decisions_ready"

        clauses = load_clauses(conn, doc_id)
        assert len(clauses) >= 1
        clause_types = {c.clause_type for c in clauses}
        assert any(t in clause_types for t in expected_spec["expected_clause_types"])

        decisions = load_decisions(conn, doc_id)
        assert len(decisions) >= expected_spec["minimum_decision_count"]

        top_decision = decisions[0]
        # Inaction option invariant verification
        inaction = next((opt for opt in top_decision.options if opt.is_default_if_inaction), None)
        assert inaction is not None, "A decision with a deadline must have an inaction option"
        assert inaction.consequence, "Inaction consequence must be non-empty"
        assert inaction.source_spans or top_decision.source_spans, "Inaction option must reference source spans"

        # Check required phrasing from golden spec
        all_text = (inaction.consequence + " " + top_decision.title).lower()
        assert expected_spec["required_inaction_phrase"] in all_text

        # Triage check: eviction is high stakes
        assert top_decision.triage_tier in ("lawyer_now", "legal_aid_recommended")

        # Deadline tracker entry check
        tracker_rows = sqlite.query(conn, "SELECT * FROM deadline_tracker WHERE decision_id = ?", (top_decision.decision_id,))
        assert len(tracker_rows) == 1


def test_scenario_c_tos_arbitration_e2e(tmp_path, monkeypatch):
    """Scenario C (Terms of Service Arbitration Opt-out):
    Verify extraction detects the 30-day arbitration opt-out decision."""
    test_db = tmp_path / "test_e2e_c.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)

    tos_file = GOLDEN_DIR / "scenario_c_tos_arbitration.txt"
    expected_spec = json.loads((GOLDEN_DIR / "scenario_c_expected_decisions.json").read_text())

    with sqlite.connect() as conn:
        doc_id = _run_pipeline_for_file(conn, tos_file, "doc_scenario_c")

        doc = load_document(conn, doc_id)
        assert doc is not None
        assert doc.processing_status == "decisions_ready"

        decisions = load_decisions(conn, doc_id)
        assert len(decisions) >= expected_spec["minimum_decision_count"]

        top_decision = decisions[0]
        inaction = next((opt for opt in top_decision.options if opt.is_default_if_inaction), None)
        assert inaction is not None
        assert expected_spec["required_inaction_phrase"] in inaction.consequence.lower()
