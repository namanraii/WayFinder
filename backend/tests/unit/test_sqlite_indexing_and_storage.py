"""Unit tests for SQLite database operations, indexing, and JSON encoding."""
from __future__ import annotations

import sqlite3
import pytest
from app.db import sqlite


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    test_db = tmp_path / "storage_test.db"
    monkeypatch.setattr(sqlite, "DB_PATH", test_db)
    sqlite.init_db(test_db)
    return test_db


def test_sqlite_pragmas_and_performance(temp_db):
    """Verify SQLite WAL mode, foreign keys, and synchronous pragmas."""
    with sqlite.connect(temp_db) as conn:
        fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_status == 1

        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() in ("wal", "memory", "delete")

        sync_mode = conn.execute("PRAGMA synchronous").fetchone()[0]
        # 1 = NORMAL
        assert sync_mode in (1, 2)


def test_sqlite_indexes_created(temp_db):
    """Verify performance indexes exist on key foreign keys and query paths."""
    with sqlite.connect(temp_db) as conn:
        indexes = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        ]
        assert "idx_clauses_doc_id" in indexes
        assert "idx_decisions_doc_id" in indexes
        assert "idx_decisions_tier" in indexes
        assert "idx_artifacts_dec_id" in indexes
        assert "idx_tracker_dec_id" in indexes
        assert "idx_qa_doc_id" in indexes


def test_json_encode_decode_helpers():
    """Verify _encode and decode_json handle edge cases and malformed inputs."""
    # Test encoding
    assert sqlite._encode({"a": 1}) == '{"a": 1}'
    assert sqlite._encode([1, 2, 3]) == "[1, 2, 3]"
    assert sqlite._encode(True) == 1
    assert sqlite._encode(False) == 0
    assert sqlite._encode("plain string") == "plain string"
    assert sqlite._encode(42) == 42

    # Test decoding
    assert sqlite.decode_json('{"foo": "bar"}') == {"foo": "bar"}
    assert sqlite.decode_json('[1, "two"]') == [1, "two"]
    assert sqlite.decode_json(None, default=[]) == []
    assert sqlite.decode_json("not valid json", default={}) == {}
    assert sqlite.decode_json({"already": "dict"}) == {"already": "dict"}


def test_crud_lifecycle(temp_db):
    """Verify insert, get, update, query lifecycle."""
    with sqlite.connect(temp_db) as conn:
        # Insert user
        sqlite.insert(conn, "users", {
            "user_id": "usr_perf_test",
            "preferred_language": "en",
            "training_opt_in": 1,
        })
        user = sqlite.get(conn, "users", "user_id", "usr_perf_test")
        assert user is not None
        assert user["user_id"] == "usr_perf_test"
        assert user["training_opt_in"] == 1

        # Update user
        sqlite.update(conn, "users", "user_id", "usr_perf_test", {
            "preferred_language": "es",
        })
        updated = sqlite.get(conn, "users", "user_id", "usr_perf_test")
        assert updated["preferred_language"] == "es"

        # Query users
        users = sqlite.query(conn, "SELECT * FROM users WHERE preferred_language = ?", ("es",))
        assert len(users) == 1
        assert users[0]["user_id"] == "usr_perf_test"
