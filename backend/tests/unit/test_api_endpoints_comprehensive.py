"""Comprehensive API endpoint testing for Wayfinder."""
from __future__ import annotations

import io
import pytest
from fastapi.testclient import TestClient

from app.db import sqlite
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_wayfinder.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)
    with TestClient(app) as test_client:
        yield test_client


def _seed_sample_doc(conn):
    sqlite.insert(conn, "users", {"user_id": "usr_demo", "training_opt_in": 0})
    sqlite.insert(conn, "documents", {
        "document_id": "doc_comprehensive",
        "user_id": "usr_demo",
        "storage_uri": "/tmp/test.txt",
        "original_filename": "lease.txt",
        "document_type": "lease",
        "processing_status": "decisions_ready",
        "jurisdiction_status": "confirmed",
        "jurisdiction_country": "US",
        "jurisdiction_region": "CA",
    })
    sqlite.insert(conn, "clauses", {
        "clause_id": "c1",
        "document_id": "doc_comprehensive",
        "clause_title": "Rent Payment",
        "clause_type": "notice_period",
        "original_text": "Rent is due on the 1st of each month. Failure to pay will result in a late fee.",
        "plain_language": "Pay rent on the 1st.",
        "obligations": [{"actor": "tenant", "action": "Pay rent by the 1st"}],
        "rights": [{"actor": "tenant", "right": "Quiet enjoyment"}],
        "risks": [{"type": "late_fee", "description": "Late fee of $50", "severity": "medium"}],
    })
    sqlite.insert(conn, "decisions", {
        "decision_id": "dec_c1",
        "document_id": "doc_comprehensive",
        "title": "Pay Monthly Rent",
        "triggering_clause_ids": ["c1"],
        "deadline": "2026-10-01",
        "options": [
            {
                "option_id": "opt_pay",
                "action": "Pay rent",
                "consequence": "No late fees",
                "is_default_if_inaction": False,
            },
            {
                "option_id": "opt_inaction",
                "action": "Do not pay",
                "consequence": "$50 late fee and potential notice. [c1]",
                "is_default_if_inaction": True,
                "source_spans": ["c1:0-35"],
            },
        ],
        "triage_tier": "self_serve",
        "triage_scores": {"reversibility": "high", "stakes": "low", "ambiguity": "low"},
        "triage_reasoning": "Standard rent obligation.",
    })
    sqlite.insert(conn, "deadline_tracker", {
        "tracker_id": "trk_c1",
        "decision_id": "dec_c1",
        "deadline": "2026-10-01",
        "resolving_action": "Pay rent",
        "inaction_consequence_short": "$50 late fee",
        "status": "open",
    })


def test_get_document_success(client):
    """Retrieving an existing document returns 200 with metadata."""
    with sqlite.connect() as conn:
        _seed_sample_doc(conn)

    res = client.get("/documents/doc_comprehensive")
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == "doc_comprehensive"
    assert data["original_filename"] == "lease.txt"


def test_get_document_not_found(client):
    """Retrieving a non-existent document returns 404."""
    res = client.get("/documents/non_existent_doc_123")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_list_clauses_for_document(client):
    """Listing clauses for a document returns parsed structured clauses."""
    with sqlite.connect() as conn:
        _seed_sample_doc(conn)

    res = client.get("/documents/doc_comprehensive/clauses")
    assert res.status_code == 200
    clauses = res.json()
    assert len(clauses) >= 1
    assert clauses[0]["clause_id"] == "c1"
    assert clauses[0]["obligations"][0]["action"] == "Pay rent by the 1st"


def test_get_or_create_prep_pack_endpoint(client):
    """Retrieving prep pack returns checklist and guidance."""
    with sqlite.connect() as conn:
        _seed_sample_doc(conn)

    res = client.post("/decisions/dec_c1/prep-pack")
    assert res.status_code == 200
    pack = res.json()
    assert pack["decision_id"] == "dec_c1"
    assert "questions_for_professional" in pack["contents"]


def test_deadline_tracker_list_and_ics(client):
    """Test getting tracker entries and exporting ICS."""
    with sqlite.connect() as conn:
        _seed_sample_doc(conn)

    # Get entries
    res = client.get("/users/usr_demo/tracker")
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) >= 1

    # Export ICS
    ics_res = client.get("/tracker/trk_c1/export.ics")
    assert ics_res.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_res.text


def test_whatsapp_webhook_event_receiver(client):
    """WhatsApp webhook receiver accepts mock incoming messages."""
    with sqlite.connect() as conn:
        _seed_sample_doc(conn)

    payload = {
        "From": "+1234567890",
        "Body": "What is my next deadline?",
        "document_id": "doc_comprehensive",
    }
    res = client.post("/webhooks/whatsapp", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "Pay Monthly Rent" in data["reply_text"]
