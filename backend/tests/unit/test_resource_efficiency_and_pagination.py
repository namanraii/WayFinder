"""Tests specifically verifying resource efficiency (time & memory) optimizations."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import sqlite
from app.llm.orchestrator import LLMOrchestrator, _load_prompt_cached
from app.main import app
from app.services.resolution_artifacts import _read_template


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_perf.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)
    with TestClient(app) as test_client:
        yield test_client


def _seed_multiple_records(conn, doc_id="doc_perf", count=10):
    sqlite.insert(conn, "users", {"user_id": "usr_perf", "training_opt_in": 0})
    sqlite.insert(conn, "documents", {
        "document_id": doc_id,
        "user_id": "usr_perf",
        "storage_uri": "/tmp/test.txt",
        "original_filename": "agreement.txt",
        "document_type": "contract",
        "processing_status": "decisions_ready",
        "jurisdiction_status": "confirmed",
    })

    clause_rows = [
        {
            "clause_id": f"c_{i}",
            "document_id": doc_id,
            "clause_title": f"Clause {i}",
            "clause_type": "notice_period",
            "original_text": f"This is clause number {i} regarding notice.",
            "plain_language": f"Summary {i}",
            "obligations": [],
            "rights": [],
            "risks": [],
        }
        for i in range(count)
    ]
    sqlite.batch_insert(conn, "clauses", clause_rows)

    decision_rows = [
        {
            "decision_id": f"dec_{i}",
            "document_id": doc_id,
            "title": f"Decision {i}",
            "triggering_clause_ids": [f"c_{i}"],
            "deadline": f"2026-10-{i+1:02d}",
            "options": [
                {
                    "option_id": f"opt_{i}_act",
                    "action": "Take action",
                    "consequence": "None",
                    "is_default_if_inaction": False,
                },
                {
                    "option_id": f"opt_{i}_inaction",
                    "action": "Do nothing",
                    "consequence": f"Consequence {i}. [c_{i}]",
                    "is_default_if_inaction": True,
                    "source_spans": [f"c_{i}:0-10"],
                },
            ],
            "triage_tier": "self_serve",
            "triage_scores": {"reversibility": "high", "stakes": "low", "ambiguity": "low"},
            "triage_reasoning": "Standard decision.",
        }
        for i in range(count)
    ]
    sqlite.batch_insert(conn, "decisions", decision_rows)

    tracker_rows = [
        {
            "tracker_id": f"trk_{i}",
            "decision_id": f"dec_{i}",
            "deadline": f"2026-10-{i+1:02d}",
            "resolving_action": f"Action {i}",
            "inaction_consequence_short": f"Consequence {i}",
            "status": "open",
        }
        for i in range(count)
    ]
    sqlite.batch_insert(conn, "deadline_tracker", tracker_rows)


def test_thread_local_connection_pool():
    """Verify thread-local connection pool reuses connection on the same thread."""
    c1 = sqlite.connect()
    c2 = sqlite.connect()
    assert c1 is c2, "Connection pool should return the identical connection on the same thread"


def test_batch_insert_and_query_iter(tmp_path, monkeypatch):
    """Verify batch_insert inserts all rows efficiently and query_iter yields them."""
    test_db = tmp_path / "test_batch.db"
    sqlite.init_db(test_db)
    with sqlite.connect(test_db) as conn:
        rows = [{"user_id": f"usr_{i}", "training_opt_in": i % 2} for i in range(5)]
        sqlite.batch_insert(conn, "users", rows)

        fetched = list(sqlite.query_iter(conn, "SELECT user_id FROM users ORDER BY user_id"))
        assert len(fetched) == 5
        assert fetched[0]["user_id"] == "usr_0"


def test_clause_pagination_and_cache_control(client):
    """Verify limit and offset query parameters restrict returned clauses for memory efficiency."""
    with sqlite.connect() as conn:
        _seed_multiple_records(conn, "doc_page_clause", count=10)

    res1 = client.get("/documents/doc_page_clause/clauses?limit=3&offset=0")
    assert res1.status_code == 200
    assert "Cache-Control" in res1.headers
    data1 = res1.json()
    assert len(data1) == 3
    assert data1[0]["clause_id"] == "c_0"

    res2 = client.get("/documents/doc_page_clause/clauses?limit=3&offset=3")
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2) == 3
    assert data2[0]["clause_id"] == "c_3"


def test_decision_pagination_and_cache_control(client):
    """Verify pagination on decisions endpoint."""
    with sqlite.connect() as conn:
        _seed_multiple_records(conn, "doc_page_dec", count=10)

    res = client.get("/documents/doc_page_dec/decisions?limit=4&offset=2")
    assert res.status_code == 200
    assert "Cache-Control" in res.headers
    data = res.json()
    assert len(data["decisions"]) == 4


def test_tracker_pagination_and_cache_control(client):
    """Verify pagination on user tracker endpoint."""
    with sqlite.connect() as conn:
        _seed_multiple_records(conn, "doc_page_trk", count=10)

    res = client.get("/users/usr_perf/tracker?limit=5&offset=2")
    assert res.status_code == 200
    assert "Cache-Control" in res.headers
    data = res.json()
    assert len(data) == 5


def test_lru_caches_on_templates_and_prompts():
    """Verify in-memory caching avoids repeated disk reads."""
    p1 = _load_prompt_cached("clause_extraction_v1")
    p2 = _load_prompt_cached("clause_extraction_v1")
    assert p1 == p2
    info = _load_prompt_cached.cache_info()
    assert info.hits >= 1

    t1 = _read_template("objection_letter_v1")
    t2 = _read_template("objection_letter_v1")
    assert t1 == t2
    t_info = _read_template.cache_info()
    assert t_info.hits >= 1
