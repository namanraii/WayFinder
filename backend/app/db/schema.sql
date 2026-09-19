-- Wayfinder Postgres DDL (authoritative reference, spec §17 + §9.4).
-- The local demo runtime uses SQLite (see sqlite.py) because no Postgres
-- server is available in this environment; this file preserves the spec's
-- production schema verbatim for the real deployment target.

CREATE TABLE users (
  user_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now(),
  training_opt_in BOOLEAN DEFAULT false,
  preferred_language TEXT DEFAULT 'en'
);

CREATE TABLE documents (
  document_id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id),
  uploaded_at TIMESTAMPTZ DEFAULT now(),
  original_filename TEXT,
  storage_uri TEXT NOT NULL,
  mime_type TEXT,
  page_count INT,
  language_detected TEXT,
  document_type TEXT,
  document_type_confidence FLOAT,
  jurisdiction_status TEXT CHECK (jurisdiction_status IN ('confirmed','inferred','unknown')),
  jurisdiction_country TEXT,
  jurisdiction_region TEXT,
  jurisdiction_source TEXT,
  role_context TEXT,
  processing_status TEXT DEFAULT 'ingested',
  consented_at TIMESTAMPTZ
);

CREATE TABLE clauses (
  clause_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  clause_title TEXT,
  clause_type TEXT,
  page INT,
  char_start INT,
  char_end INT,
  original_text TEXT NOT NULL,
  plain_language TEXT,
  obligations JSONB DEFAULT '[]',
  rights JSONB DEFAULT '[]',
  risks JSONB DEFAULT '[]',
  missing_elements JSONB DEFAULT '[]',
  related_clause_ids TEXT[] DEFAULT '{}',
  feeds_decision_id TEXT,
  extraction_confidence FLOAT,
  embedding VECTOR(1536)
);

CREATE TABLE decisions (
  decision_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  title TEXT NOT NULL,
  triggering_clause_ids TEXT[] NOT NULL,
  deadline DATE,
  options JSONB NOT NULL,
  triage_tier TEXT CHECK (triage_tier IN
    ('self_serve','self_serve_with_escalation_path','legal_aid_recommended','lawyer_now')),
  triage_scores JSONB,
  triage_reasoning TEXT,
  resolution_artifact_id TEXT,
  confidence TEXT,
  jurisdiction_confidence_note TEXT,
  source_spans TEXT[],
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT inaction_option_required CHECK (
    deadline IS NULL OR
    options @> '[{"is_default_if_inaction": true}]'::jsonb
  )
);

CREATE TABLE resolution_artifacts (
  artifact_id TEXT PRIMARY KEY,
  decision_id TEXT REFERENCES decisions(decision_id),
  type TEXT NOT NULL,
  status TEXT DEFAULT 'draft',
  content TEXT,
  fields_to_fill TEXT[],
  generated_at TIMESTAMPTZ DEFAULT now(),
  model_version TEXT,
  prompt_version TEXT
);

CREATE TABLE prep_packs (
  prep_pack_id TEXT PRIMARY KEY,
  decision_id TEXT REFERENCES decisions(decision_id),
  contents JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE deadline_tracker (
  tracker_id TEXT PRIMARY KEY,
  decision_id TEXT REFERENCES decisions(decision_id),
  deadline DATE NOT NULL,
  resolving_action TEXT,
  inaction_consequence_short TEXT,
  status TEXT DEFAULT 'open' CHECK (status IN ('open','resolved','missed')),
  reminder_schedule TEXT[] DEFAULT '{"T-7d","T-3d","T-1d"}'
);

CREATE TABLE graph_nodes (
  node_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  node_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  properties JSONB
);

CREATE TABLE graph_edges (
  edge_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  from_node_id TEXT REFERENCES graph_nodes(node_id),
  to_node_id TEXT REFERENCES graph_nodes(node_id),
  edge_type TEXT NOT NULL
);

CREATE TABLE qa_log (
  qa_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  question TEXT,
  answer TEXT,
  cited_clause_ids TEXT[],
  confidence TEXT,
  linked_decision_id TEXT,
  model_version TEXT,
  prompt_version TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE generation_audit_log (
  audit_id TEXT PRIMARY KEY,
  entity_type TEXT,
  entity_id TEXT,
  model_version TEXT,
  prompt_version TEXT,
  guardrail_checks_passed JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
