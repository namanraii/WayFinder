"""SQLite runtime store — local adaptation of the spec §17 Postgres schema.

Differences from schema.sql (Postgres): JSONB -> TEXT (JSON-serialized),
TEXT[] -> TEXT (JSON-serialized), VECTOR/TIMESTAMPTZ dropped. Table and
column names are identical so the application layer is storage-agnostic.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "wayfinder.db"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"

DDL = """
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  created_at TEXT DEFAULT (datetime('now')),
  training_opt_in INTEGER DEFAULT 0,
  preferred_language TEXT DEFAULT 'en'
);
CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id),
  uploaded_at TEXT DEFAULT (datetime('now')),
  original_filename TEXT,
  storage_uri TEXT NOT NULL,
  mime_type TEXT,
  page_count INTEGER,
  language_detected TEXT,
  document_type TEXT,
  document_type_confidence REAL,
  jurisdiction_status TEXT CHECK (jurisdiction_status IN ('confirmed','inferred','unknown')),
  jurisdiction_country TEXT,
  jurisdiction_region TEXT,
  jurisdiction_source TEXT,
  role_context TEXT,
  processing_status TEXT DEFAULT 'ingested',
  consented_at TEXT
);
CREATE TABLE IF NOT EXISTS clauses (
  clause_id TEXT NOT NULL,
  document_id TEXT REFERENCES documents(document_id),
  clause_title TEXT,
  clause_type TEXT,
  page INTEGER,
  char_start INTEGER,
  char_end INTEGER,
  original_text TEXT NOT NULL,
  plain_language TEXT,
  obligations TEXT DEFAULT '[]',
  rights TEXT DEFAULT '[]',
  risks TEXT DEFAULT '[]',
  missing_elements TEXT DEFAULT '[]',
  related_clause_ids TEXT DEFAULT '[]',
  feeds_decision_id TEXT,
  extraction_confidence REAL,
  PRIMARY KEY (document_id, clause_id)
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  title TEXT NOT NULL,
  triggering_clause_ids TEXT NOT NULL,
  deadline TEXT,
  options TEXT NOT NULL,
  triage_tier TEXT CHECK (triage_tier IN
    ('self_serve','self_serve_with_escalation_path','legal_aid_recommended','lawyer_now')),
  triage_scores TEXT,
  triage_reasoning TEXT,
  resolution_artifact_id TEXT,
  confidence TEXT,
  jurisdiction_confidence_note TEXT,
  source_spans TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS resolution_artifacts (
  artifact_id TEXT PRIMARY KEY,
  decision_id TEXT REFERENCES decisions(decision_id),
  type TEXT NOT NULL,
  status TEXT DEFAULT 'draft',
  content TEXT,
  fields_to_fill TEXT,
  generated_at TEXT DEFAULT (datetime('now')),
  model_version TEXT,
  prompt_version TEXT
);
CREATE TABLE IF NOT EXISTS prep_packs (
  prep_pack_id TEXT PRIMARY KEY,
  decision_id TEXT REFERENCES decisions(decision_id),
  contents TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS deadline_tracker (
  tracker_id TEXT PRIMARY KEY,
  decision_id TEXT REFERENCES decisions(decision_id),
  deadline TEXT NOT NULL,
  resolving_action TEXT,
  inaction_consequence_short TEXT,
  status TEXT DEFAULT 'open' CHECK (status IN ('open','resolved','missed')),
  reminder_schedule TEXT DEFAULT '["T-7d","T-3d","T-1d"]'
);
CREATE TABLE IF NOT EXISTS graph_nodes (
  node_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  node_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  properties TEXT
);
CREATE TABLE IF NOT EXISTS graph_edges (
  edge_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  from_node_id TEXT REFERENCES graph_nodes(node_id),
  to_node_id TEXT REFERENCES graph_nodes(node_id),
  edge_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qa_log (
  qa_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  question TEXT,
  answer TEXT,
  cited_clause_ids TEXT,
  confidence TEXT,
  linked_decision_id TEXT,
  model_version TEXT,
  prompt_version TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS generation_audit_log (
  audit_id TEXT PRIMARY KEY,
  entity_type TEXT,
  entity_id TEXT,
  model_version TEXT,
  prompt_version TEXT,
  guardrail_checks_passed TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_clauses_doc_id ON clauses(document_id);
CREATE INDEX IF NOT EXISTS idx_decisions_doc_id ON decisions(document_id);
CREATE INDEX IF NOT EXISTS idx_decisions_tier ON decisions(triage_tier);
CREATE INDEX IF NOT EXISTS idx_artifacts_dec_id ON resolution_artifacts(decision_id);
CREATE INDEX IF NOT EXISTS idx_preppacks_dec_id ON prep_packs(decision_id);
CREATE INDEX IF NOT EXISTS idx_tracker_dec_id ON deadline_tracker(decision_id);
CREATE INDEX IF NOT EXISTS idx_tracker_status ON deadline_tracker(status);
CREATE INDEX IF NOT EXISTS idx_qa_doc_id ON qa_log(document_id);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_doc ON graph_nodes(document_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_doc ON graph_edges(document_id);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(DDL)


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or DB_PATH), timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def insert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    values = [_encode(v) for v in row.values()]
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", values)


def update(conn: sqlite3.Connection, table: str, key_col: str, key_val: str, fields: dict[str, Any]) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE {table} SET {sets} WHERE {key_col} = ?",
        [_encode(v) for v in fields.values()] + [key_val],
    )


def get(conn: sqlite3.Connection, table: str, key_col: str, key_val: str) -> Optional[dict]:
    row = conn.execute(f"SELECT * FROM {table} WHERE {key_col} = ?", (key_val,)).fetchone()
    return dict(row) if row else None


def query(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def _encode(v: Any) -> Any:
    if isinstance(v, (dict, list, tuple)):
        return json.dumps(v)
    if isinstance(v, bool):
        return int(v)
    return v


def decode_json(v: Any, default: Any = None) -> Any:
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return default
