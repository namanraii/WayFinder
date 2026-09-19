"""Unit tests for Comparison, Q&A, and Deadline Tracker services (spec §14, §15, §16)."""
from __future__ import annotations

from app.db import sqlite
from app.services import comparison, deadline_tracker, qa


def test_deadline_tracker_sync_and_ics_export(tmp_path, monkeypatch):
    test_db = tmp_path / "test_tracker.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    monkeypatch.setattr(sqlite, "EXPORT_DIR", tmp_path / "exports")
    sqlite.init_db(test_db)

    with sqlite.connect() as conn:
        sqlite.insert(conn, "users", {"user_id": "usr_test", "training_opt_in": 0})
        sqlite.insert(conn, "documents", {
            "document_id": "doc_trk",
            "user_id": "usr_test",
            "storage_uri": "/tmp/test",
            "processing_status": "decisions_ready",
        })
        sqlite.insert(conn, "decisions", {
            "decision_id": "dec_trk_1",
            "document_id": "doc_trk",
            "title": "Respond to Landlord Demand",
            "triggering_clause_ids": ["c1"],
            "deadline": "2026-11-15",
            "options": [
                {"option_id": "opt1", "action": "Pay or dispute", "consequence": "Stay", "is_default_if_inaction": False},
                {"option_id": "opt2", "action": "Do nothing", "consequence": "Eviction proceedings commence", "is_default_if_inaction": True, "source_spans": ["c1:0-10"]},
            ],
            "source_spans": ["c1:0-10"],
        })

        # Sync tracker
        entries = deadline_tracker.sync_for_document(conn, "doc_trk")
        assert len(entries) == 1
        entry = entries[0]
        assert entry.deadline == "2026-11-15"
        assert entry.status == "open"
        assert "Eviction proceedings commence" in (entry.inaction_consequence_short or "")

        # Export ICS
        path_str, content = deadline_tracker.export_ics(conn, entry.tracker_id)
        assert "BEGIN:VCALENDAR" in content
        assert "DTSTART;VALUE=DATE:20261115" in content
        assert "Respond to Landlord Demand" in content
        assert "Eviction proceedings commence" in content
        assert "END:VCALENDAR" in content


def test_grounded_qa_with_citations_and_disclaimer(tmp_path, monkeypatch):
    test_db = tmp_path / "test_qa.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)

    with sqlite.connect() as conn:
        sqlite.insert(conn, "users", {"user_id": "usr_qa", "training_opt_in": 0})
        sqlite.insert(conn, "documents", {
            "document_id": "doc_qa",
            "user_id": "usr_qa",
            "storage_uri": "/tmp/test",
            "jurisdiction_status": "confirmed",
        })
        sqlite.insert(conn, "clauses", {
            "clause_id": "clause_qa_1",
            "document_id": "doc_qa",
            "clause_title": "Arbitration Notice",
            "clause_type": "arbitration_optout",
            "original_text": "You may opt out of binding arbitration within 30 days of opening your account.",
            "plain_language": "You have 30 days to opt out of arbitration.",
            "obligations": [{"actor": "you", "action": "opt out", "deadline_relative": "30 days"}],
            "extraction_confidence": 0.95,
        })

        res = qa.answer_question(conn, "doc_qa", "What is the deadline to opt out of arbitration?")
        assert res["answer"]
        assert "clause_qa_1" in [c["clause_id"] for c in res.get("citations", [])]
        assert "Wayfinder provides legal information" in res["disclaimer"]


def test_comparison_aligns_clauses_and_computes_impact(tmp_path, monkeypatch):
    test_db = tmp_path / "test_cmp.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)

    with sqlite.connect() as conn:
        sqlite.insert(conn, "users", {"user_id": "usr_cmp", "training_opt_in": 0})
        sqlite.insert(conn, "documents", {
            "document_id": "doc_v1", "user_id": "usr_cmp", "storage_uri": "/tmp/v1",
        })
        sqlite.insert(conn, "documents", {
            "document_id": "doc_v2", "user_id": "usr_cmp", "storage_uri": "/tmp/v2",
        })

        sqlite.insert(conn, "clauses", {
            "clause_id": "c_v1",
            "document_id": "doc_v1",
            "clause_type": "payment_dispute",
            "original_text": "Invoices must be disputed within 30 days.",
            "feeds_decision_id": "dec_invoice",
        })
        sqlite.insert(conn, "clauses", {
            "clause_id": "c_v2",
            "document_id": "doc_v2",
            "clause_type": "payment_dispute",
            "original_text": "Invoices must be disputed within 5 days.",
            "feeds_decision_id": "dec_invoice",
        })

        cmp_result = comparison.compare_documents(conn, "doc_v1", "doc_v2")
        assert "decision" in cmp_result.decision_impact_summary.lower()
        diffs = cmp_result.clause_diffs
        assert len(diffs) >= 1
        changed_diff = next(d for d in diffs if d.clause_type == "payment_dispute")
        assert changed_diff.status == "changed"
        assert changed_diff.risk_delta == "increased"  # 30 days -> 5 days increases urgency/risk
