"""Unit test for server-side tier gate on /resolve endpoint (spec §18.6, §21.1)."""
from __future__ import annotations

from unittest.mock import patch

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


def _seed_decision(conn, decision_id: str, tier: str):
    sqlite.insert(conn, "users", {"user_id": "usr_test", "training_opt_in": 0})
    sqlite.insert(conn, "documents", {
        "document_id": f"doc_{decision_id}",
        "user_id": "usr_test",
        "storage_uri": "/tmp/dummy",
        "processing_status": "decisions_ready",
        "jurisdiction_status": "confirmed",
    })
    sqlite.insert(conn, "clauses", {
        "clause_id": f"clause_{decision_id}",
        "document_id": f"doc_{decision_id}",
        "clause_type": "notice_period",
        "original_text": "Tenant must respond within 14 days.",
        "plain_language": "Respond within 14 days or forfeit lease.",
    })
    sqlite.insert(conn, "decisions", {
        "decision_id": decision_id,
        "document_id": f"doc_{decision_id}",
        "title": "Respond to Notice",
        "triggering_clause_ids": [f"clause_{decision_id}"],
        "deadline": "2026-10-15",
        "options": [
            {
                "option_id": "opt_1",
                "action": "Send notice",
                "consequence": "Protects rights",
                "is_default_if_inaction": False,
            },
            {
                "option_id": "opt_inaction",
                "action": "Do nothing",
                "consequence": "Default loss of lease. [clause_1]",
                "is_default_if_inaction": True,
                "source_spans": [f"clause_{decision_id}:0-50"],
            },
        ],
        "triage_tier": tier,
        "source_spans": [f"clause_{decision_id}:0-50"],
    })


def test_resolve_blocked_for_lawyer_now_and_never_invokes_llm(client):
    """Spec §18.6 & §21.1: A lawyer_now decision returns 403 and never invokes the LLM."""
    with sqlite.connect() as conn:
        _seed_decision(conn, "dec_lawyer", "lawyer_now")

    with patch("app.llm.orchestrator.LLMOrchestrator.generate") as mock_generate:
        response = client.post("/decisions/dec_lawyer/resolve", json={"option_id": "opt_1"})
        assert response.status_code == 403
        assert "blocked" in response.json()["detail"].lower()
        mock_generate.assert_not_called()


def test_resolve_blocked_for_legal_aid_and_never_invokes_llm(client):
    """Spec §18.6: A legal_aid_recommended decision returns 403 and never invokes the LLM."""
    with sqlite.connect() as conn:
        _seed_decision(conn, "dec_legal_aid", "legal_aid_recommended")

    with patch("app.llm.orchestrator.LLMOrchestrator.generate") as mock_generate:
        response = client.post("/decisions/dec_legal_aid/resolve", json={"option_id": "opt_1"})
        assert response.status_code == 403
        assert "blocked" in response.json()["detail"].lower()
        mock_generate.assert_not_called()


def test_resolve_permitted_for_self_serve(client):
    """Spec §18.6: A self_serve decision allows draft generation and includes disclaimer."""
    with sqlite.connect() as conn:
        _seed_decision(conn, "dec_self_serve", "self_serve")

    response = client.post("/decisions/dec_self_serve/resolve", json={"option_id": "opt_1"})
    assert response.status_code == 200
    data = response.json()
    assert data["artifact_id"]
    assert "Wayfinder provides legal information" in data["disclaimer"]
    assert "disclaimer" in data["content"].lower() or "wayfinder" in data["content"].lower()
