from pathlib import Path

from app.db import sqlite
from app.llm.guardrails import INACTION_UNSPECIFIED
from app.services.cost_of_inaction import build


class NeverCallOrchestrator:
    def generate(self, **_kwargs):  # pragma: no cover - failure branch
        raise AssertionError("The LLM must not be called when no trigger exists")


def _seed_deadline_without_trigger(db_path: Path):
    sqlite.init_db(db_path)
    with sqlite.connect(db_path) as conn:
        sqlite.insert(conn, "users", {"user_id": "user_test"})
        sqlite.insert(conn, "documents", {
            "document_id": "doc_test", "user_id": "user_test", "storage_uri": "fixture.txt",
        })
        sqlite.insert(conn, "clauses", {
            "clause_id": "clause_test", "document_id": "doc_test",
            "original_text": "Respond within 10 days.", "char_start": 0, "char_end": 23,
        })
        sqlite.insert(conn, "graph_nodes", {
            "node_id": "deadline_test", "document_id": "doc_test", "node_type": "deadline",
            "ref_id": "clause_test", "properties": {},
        })


def test_missing_trigger_uses_exact_fallback_without_llm(tmp_path):
    db_path = tmp_path / "wayfinder.db"
    _seed_deadline_without_trigger(db_path)

    with sqlite.connect(db_path) as conn:
        option = build(conn, "doc_test", "deadline_test", NeverCallOrchestrator())

    assert option.is_default_if_inaction is True
    assert option.consequence == INACTION_UNSPECIFIED
    assert option.source_spans == ["clause_test:0-23"]
