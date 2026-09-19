export type ProcessingStatus =
  | "ingested"
  | "segmented"
  | "extracted"
  | "graphed"
  | "decisions_ready"
  | "failed";

export type TriageTier =
  | "self_serve"
  | "self_serve_with_escalation_path"
  | "legal_aid_recommended"
  | "lawyer_now";

export interface Jurisdiction {
  status: "confirmed" | "inferred" | "unknown";
  country?: string | null;
  state_or_region?: string | null;
  source: "user_input" | "governing_law_clause" | "address_field" | "none";
}

export interface DocumentRecord {
  document_id: string;
  user_id: string;
  uploaded_at?: string | null;
  original_filename?: string | null;
  storage_uri: string;
  mime_type?: string | null;
  page_count?: number | null;
  language_detected?: string | null;
  document_type?: string | null;
  document_type_confidence?: number | null;
  jurisdiction: Jurisdiction;
  role_context?: string | null;
  processing_status: ProcessingStatus;
  consent?: { consented_at?: string | null; training_opt_in: boolean };
}

export interface Obligation {
  actor: string;
  action: string;
  deadline_relative?: string | null;
  deadline_absolute?: string | null;
  condition?: string | null;
}

export interface ClauseRisk {
  type: string;
  description: string;
  severity: "low" | "medium" | "high" | string;
}

export interface Clause {
  clause_id: string;
  document_id: string;
  clause_title?: string | null;
  clause_type: string;
  page?: number | null;
  char_span: [number, number];
  original_text: string;
  plain_language?: string | null;
  obligations: Obligation[];
  rights: Array<{ actor: string; right: string; condition?: string | null }>;
  risks: ClauseRisk[];
  missing_elements: string[];
  related_clause_ids: string[];
  feeds_decision_id?: string | null;
  extraction_confidence: number;
}

export interface DecisionOption {
  option_id: string;
  action: string;
  consequence: string;
  effort: string;
  cost: string;
  is_default_if_inaction: boolean;
  source_spans?: string[];
}

export interface TriageScores {
  reversibility: "low" | "high";
  stakes: "low" | "medium" | "high";
  ambiguity: "low" | "high";
}

export interface DecisionPoint {
  decision_id: string;
  document_id: string;
  title: string;
  triggering_clause_ids: string[];
  deadline?: string | null;
  days_remaining?: number | null;
  options: DecisionOption[];
  triage_tier?: TriageTier | null;
  triage_scores?: TriageScores | null;
  triage_reasoning?: string | null;
  resolution_artifact_id?: string | null;
  confidence: "high" | "medium" | "low";
  jurisdiction_confidence_note?: string | null;
  source_spans: string[];
}

export interface DecisionSummary {
  decision_id: string;
  title: string;
  deadline?: string | null;
  days_remaining?: number | null;
  triage_tier?: TriageTier | null;
  confidence?: "high" | "medium" | "low";
}

export interface DecisionListResponse {
  document_id: string;
  processing_status: ProcessingStatus;
  decisions: DecisionSummary[];
}

export interface ResolutionArtifact {
  artifact_id: string;
  decision_id: string;
  type: string;
  status: string;
  content: string;
  fields_to_fill: string[];
  generated_at?: string | null;
  disclaimer: string;
  model_version?: string | null;
  prompt_version?: string | null;
}

export interface PrepPack {
  prep_pack_id: string;
  decision_id: string;
  contents: {
    document_summary?: string;
    relevant_clause_excerpts?: string[];
    timeline?: Array<{ date: string; event: string }>;
    questions_for_professional?: string[];
    what_has_been_tried?: string[];
    urgency_note?: string;
    [key: string]: unknown;
  };
  export_formats: string[];
  export_url?: string;
  share_url?: string;
}

export interface ClauseDiff {
  clause_type: string;
  status: "same" | "similar" | "changed" | "added" | "removed" | string;
  before?: string | null;
  after?: string | null;
  affected_decision_ids: string[];
  risk_delta?: "increased" | "decreased" | "unchanged" | string | null;
}

export interface ComparisonResult {
  comparison_id: string;
  document_id_a: string;
  document_id_b: string;
  clause_diffs: ClauseDiff[];
  decision_impact_summary: string;
}

export interface DeadlineTrackerEntry {
  tracker_id: string;
  decision_id: string;
  deadline: string;
  resolving_action?: string | null;
  inaction_consequence_short?: string | null;
  reminder_schedule: string[];
  status: "open" | "resolved" | "missed" | string;
  calendar_export_ics_uri?: string | null;
}

export interface AskResponse {
  answer: string;
  citations?: string[];
  confidence?: "high" | "medium" | "low";
  disclaimer?: string;
}

export interface UploadDetails {
  userId: string;
  roleContext: string;
  country?: string;
  stateOrRegion?: string;
  trainingOptIn: boolean;
}
