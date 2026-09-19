"""Unit tests for knowledge graph traversal, heuristics, and cost-of-inaction edge cases."""
from __future__ import annotations

import pytest
from app.db import sqlite
from app.services.document_graph import traverse_triggers, build as build_graph
from app.services import cost_of_inaction
from app.services import heuristics as hz


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    test_db = tmp_path / "graph_test.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)
    return test_db


def test_consequence_sentence_heuristic():
    """Verify regex heuristics detect penalty, termination, and fee triggers."""
    text = (
        "Tenant must pay rent on the 1st. Failure to pay will result in a $50 late penalty. "
        "Landlord may terminate lease if unpaid after 5 days. Tenant has right to quiet enjoyment."
    )
    consequences = hz.consequence_sentences(text)
    assert len(consequences) >= 2
    assert any("penalty" in s.lower() for s in consequences)
    assert any("terminate" in s.lower() for s in consequences)


def test_summarize_stakes_categorization():
    """Verify summarize stakes categorizes financial vs termination consequences."""
    term_node = [{"properties": {"text": "Landlord will terminate lease and evict tenant."}}]
    assert "loss of rights or termination" in cost_of_inaction._summarize_stakes(term_node)

    fee_node = [{"properties": {"text": "Tenant shall be charged a $100 late fee."}}]
    assert "financial consequence" in cost_of_inaction._summarize_stakes(fee_node)

    generic_node = [{"properties": {"text": "Notice will be archived."}}]
    assert "document-stated consequence" in cost_of_inaction._summarize_stakes(generic_node)


def test_graph_build_and_traverse_triggers(temp_db):
    """Verify deterministic graph construction and trigger traversal from deadline to penalties."""
    doc_id = "doc_graph_test"
    with sqlite.connect(temp_db) as conn:
        sqlite.insert(conn, "users", {"user_id": "usr_test", "training_opt_in": 0})
        sqlite.insert(conn, "documents", {
            "document_id": doc_id,
            "user_id": "usr_test",
            "storage_uri": "/tmp/test",
            "processing_status": "clauses_extracted",
        })

        clauses = [{
            "clause_id": "c100",
            "clause_type": "notice_period",
            "clause_title": "Default Notice",
            "original_text": "Tenant has 3 days to pay. Failure to pay will terminate the lease.",
            "obligations": [{
                "text": "Pay rent within 3 days",
                "deadline_relative": "3 days",
            }],
        }]

        # Build graph
        build_graph(conn, doc_id, clauses)
        conn.commit()

        # Query deadline node
        deadlines = sqlite.query(
            conn,
            "SELECT * FROM graph_nodes WHERE document_id = ? AND node_type = 'deadline'",
            (doc_id,),
        )
        assert len(deadlines) >= 1
        d_node_id = deadlines[0]["node_id"]

        # Traverse
        path = traverse_triggers(conn, doc_id, d_node_id)
        assert len(path) >= 2
        assert path[0]["node_id"] == d_node_id
        assert any(n["node_type"] == "penalty" for n in path)
