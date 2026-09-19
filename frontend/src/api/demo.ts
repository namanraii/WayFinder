import type {
  AskResponse,
  Clause,
  ComparisonResult,
  DecisionListResponse,
  DecisionPoint,
  DeadlineTrackerEntry,
  DocumentRecord,
  PrepPack,
  ResolutionArtifact,
} from "./types";

export const DISCLAIMER =
  "Wayfinder provides legal information and preparation support to help you understand your documents and options. It does not provide legal advice. For advice specific to your situation, consult a qualified legal professional or legal aid organization.";

export const JURISDICTION_UNKNOWN_NOTE =
  "This document doesn't confirm your jurisdiction, so this shows only what the document itself says — not any additional legal defaults that might apply in your area. Confirming your location may change this.";

export const DEMO_DOCUMENT_ID = "doc_demo_notice";
export const DEMO_USER_ID = "usr_demo";

export const demoDocument: DocumentRecord = {
  document_id: DEMO_DOCUMENT_ID,
  user_id: DEMO_USER_ID,
  uploaded_at: "2026-09-18T09:00:00Z",
  original_filename: "rental_notice.pdf",
  storage_uri: "demo://rental_notice.pdf",
  mime_type: "application/pdf",
  page_count: 2,
  language_detected: "en",
  document_type: "legal_notice",
  document_type_confidence: 0.94,
  jurisdiction: { status: "unknown", country: "IN", state_or_region: null, source: "none" },
  role_context: "tenant",
  processing_status: "decisions_ready",
  consent: { consented_at: "2026-09-18T09:00:00Z", training_opt_in: false },
};

export const demoDecisions: DecisionPoint[] = [
  {
    decision_id: "dec_demo_respond",
    document_id: DEMO_DOCUMENT_ID,
    title: "Reply in writing before the response window closes",
    triggering_clause_ids: ["clause_demo_02"],
    deadline: "2026-09-25",
    days_remaining: 7,
    options: [
      {
        option_id: "opt_demo_reply",
        action: "Send a written response that disputes or clarifies the notice",
        consequence: "Creates a written record before the response period ends.",
        effort: "low",
        cost: "none (template available)",
        is_default_if_inaction: false,
        source_spans: ["clause_demo_02:0-162"],
      },
      {
        option_id: "opt_demo_extension",
        action: "Ask in writing for more time to respond",
        consequence: "May create extra time, but the document does not say an extension is automatic.",
        effort: "low",
        cost: "none",
        is_default_if_inaction: false,
        source_spans: ["clause_demo_02:0-162"],
      },
      {
        option_id: "opt_demo_inaction",
        action: "Do nothing",
        consequence: "The notice says no response within seven days may be treated as acceptance of the stated grounds. [clause_demo_02]",
        effort: "none",
        cost: "loss of a chance to put your response on record",
        is_default_if_inaction: true,
        source_spans: ["clause_demo_02:0-162"],
      },
    ],
    triage_tier: "self_serve_with_escalation_path",
    triage_scores: { reversibility: "high", stakes: "medium", ambiguity: "low" },
    triage_reasoning:
      "The notice gives a clear written-response action. A template can help create a record; consider legal-aid support if the other party disputes your response.",
    resolution_artifact_id: "artifact_demo_response",
    confidence: "high",
    jurisdiction_confidence_note: JURISDICTION_UNKNOWN_NOTE,
    source_spans: ["clause_demo_02:0-162"],
  },
  {
    decision_id: "dec_demo_moveout",
    document_id: DEMO_DOCUMENT_ID,
    title: "Address the move-out demand and claimed balance",
    triggering_clause_ids: ["clause_demo_01", "clause_demo_03"],
    deadline: "2026-10-03",
    days_remaining: 15,
    options: [
      {
        option_id: "opt_demo_contact",
        action: "Bring the notice and payment records to a legal-aid organization",
        consequence: "Helps a professional assess the document, timeline, and claimed balance.",
        effort: "medium",
        cost: "varies",
        is_default_if_inaction: false,
        source_spans: ["clause_demo_01:0-181", "clause_demo_03:0-112"],
      },
      {
        option_id: "opt_demo_moveinaction",
        action: "Do nothing",
        consequence: "The document says the sender may take further action after the stated date. [clause_demo_01]",
        effort: "none",
        cost: "the matter may progress without your documents or response",
        is_default_if_inaction: true,
        source_spans: ["clause_demo_01:0-181"],
      },
    ],
    triage_tier: "lawyer_now",
    triage_scores: { reversibility: "low", stakes: "high", ambiguity: "high" },
    triage_reasoning:
      "This may affect housing and has a short deadline. A send-ready draft is intentionally unavailable; a Prep Pack can make a legal-aid or lawyer conversation faster.",
    confidence: "medium",
    jurisdiction_confidence_note: JURISDICTION_UNKNOWN_NOTE,
    source_spans: ["clause_demo_01:0-181", "clause_demo_03:0-112"],
  },
];

export const demoDecisionList: DecisionListResponse = {
  document_id: DEMO_DOCUMENT_ID,
  processing_status: "decisions_ready",
  decisions: demoDecisions.map((decision) => ({
    decision_id: decision.decision_id,
    title: decision.title,
    deadline: decision.deadline,
    days_remaining: decision.days_remaining,
    triage_tier: decision.triage_tier,
    confidence: decision.confidence,
  })),
};

export const demoClauses: Clause[] = [
  {
    clause_id: "clause_demo_01",
    document_id: DEMO_DOCUMENT_ID,
    clause_title: "Vacate date",
    clause_type: "notice_period",
    page: 1,
    char_span: [0, 181],
    original_text:
      "You are requested to vacate the premises by 03 October 2026. If the premises are not vacated, the sender may take further action to recover possession and any amounts claimed.",
    plain_language:
      "The notice asks you to leave by 03 October 2026 and says the sender may take further action if you do not.",
    obligations: [
      {
        actor: "tenant",
        action: "vacate the premises or address the notice",
        deadline_relative: "by the date in the notice",
        deadline_absolute: "2026-10-03",
        condition: "as described in the notice",
      },
    ],
    rights: [],
    risks: [
      { type: "deadline_pressure", description: "The notice names a date after which further action may be taken.", severity: "high" },
    ],
    missing_elements: ["basis and supporting records for the claimed amount"],
    related_clause_ids: ["clause_demo_03"],
    feeds_decision_id: "dec_demo_moveout",
    extraction_confidence: 0.92,
  },
  {
    clause_id: "clause_demo_02",
    document_id: DEMO_DOCUMENT_ID,
    clause_title: "Response period",
    clause_type: "notice_period",
    page: 1,
    char_span: [210, 372],
    original_text:
      "Any written response must be received within seven days of this notice. A failure to respond may be treated as acceptance of the grounds stated in this notice.",
    plain_language:
      "The notice asks for a written response within seven days and says silence may be treated as accepting its reasons.",
    obligations: [
      {
        actor: "tenant",
        action: "send a written response",
        deadline_relative: "within seven days of notice",
        deadline_absolute: "2026-09-25",
        condition: "to respond to the stated grounds",
      },
    ],
    rights: [],
    risks: [
      { type: "default_if_missed", description: "The notice describes a consequence for no written response.", severity: "high" },
    ],
    missing_elements: ["method and address for sending the written response"],
    related_clause_ids: [],
    feeds_decision_id: "dec_demo_respond",
    extraction_confidence: 0.96,
  },
  {
    clause_id: "clause_demo_03",
    document_id: DEMO_DOCUMENT_ID,
    clause_title: "Claimed balance",
    clause_type: "payment",
    page: 2,
    char_span: [388, 500],
    original_text:
      "The sender claims an outstanding balance of INR 38,500, together with charges described in the attached account statement.",
    plain_language: "The notice claims you owe INR 38,500 and refers to an attached account statement.",
    obligations: [],
    rights: [],
    risks: [
      { type: "payment_claim", description: "The notice states a financial claim that may need supporting records checked.", severity: "medium" },
    ],
    missing_elements: ["itemized charges in the body of the notice"],
    related_clause_ids: ["clause_demo_01"],
    feeds_decision_id: "dec_demo_moveout",
    extraction_confidence: 0.84,
  },
];

export const demoArtifact: ResolutionArtifact = {
  artifact_id: "artifact_demo_response",
  decision_id: "dec_demo_respond",
  type: "clarification_letter",
  status: "draft",
  content: `To: [Recipient name]\nFrom: [Your name]\nDate: [Date]\nRe: Written response to notice\n\nI am writing in response to the notice dated [Notice date]. I do not accept that silence should be treated as agreement with the grounds stated in the notice. Please confirm the address and accepted method for sending a full written response, and provide the records supporting the claimed balance.\n\nThis message is intended to create a written record of my response.\n\nSincerely,\n[Your name]`,
  fields_to_fill: ["Recipient name", "Your name", "Date", "Notice date"],
  generated_at: "2026-09-18T09:05:00Z",
  disclaimer: "This is a template letter, not a filed legal instrument. Sending it does not constitute legal representation. Review before sending.",
  model_version: "wayfinder-demo-v1",
  prompt_version: "clarification_email_v1",
};

export const demoPrepPack: PrepPack = {
  prep_pack_id: "pack_demo_moveout",
  decision_id: "dec_demo_moveout",
  contents: {
    document_summary:
      "A two-page rental notice asks the tenant to vacate by 03 October 2026, claims an outstanding INR 38,500, and asks for a written response within seven days.",
    relevant_clause_excerpts: ["clause_demo_01", "clause_demo_02", "clause_demo_03"],
    timeline: [
      { date: "2026-09-18", event: "Notice received" },
      { date: "2026-09-25", event: "Written response date stated in notice" },
      { date: "2026-10-03", event: "Vacate date stated in notice" },
    ],
    questions_for_professional: [
      "What does the notice itself require before the stated move-out date?",
      "What records support the claimed INR 38,500 balance?",
      "What is the safest way to preserve a written response while jurisdiction is unconfirmed?",
    ],
    what_has_been_tried: [],
    urgency_note: "The next stated date is 25 September 2026. Bring the notice, any attachments, payment records, and copies of messages.",
  },
  export_formats: ["pdf", "share_link"],
};

export const demoComparison: ComparisonResult = {
  comparison_id: "cmp_demo_001",
  document_id_a: DEMO_DOCUMENT_ID,
  document_id_b: "doc_demo_redline",
  decision_impact_summary: "2 of your decisions changed as a result of this redraft. The response window is shorter and a payment claim was added.",
  clause_diffs: [
    {
      clause_type: "notice_period",
      status: "changed",
      before: "Any written response must be received within 14 days.",
      after: "Any written response must be received within seven days.",
      affected_decision_ids: ["dec_demo_respond"],
      risk_delta: "increased",
    },
    {
      clause_type: "payment",
      status: "added",
      before: null,
      after: "The sender claims an outstanding balance of INR 38,500.",
      affected_decision_ids: ["dec_demo_moveout"],
      risk_delta: "increased",
    },
    {
      clause_type: "notice_period",
      status: "similar",
      before: "Vacate by 03 October 2026.",
      after: "Vacate by 03 October 2026.",
      affected_decision_ids: ["dec_demo_moveout"],
      risk_delta: "unchanged",
    },
  ],
};

export const demoTrackerEntries: DeadlineTrackerEntry[] = [
  {
    tracker_id: "trk_demo_response",
    decision_id: "dec_demo_respond",
    deadline: "2026-09-25",
    resolving_action: "Send a written response",
    inaction_consequence_short: "The notice says silence may be treated as acceptance of its stated grounds.",
    reminder_schedule: ["T-7d", "T-3d", "T-1d"],
    status: "open",
  },
  {
    tracker_id: "trk_demo_moveout",
    decision_id: "dec_demo_moveout",
    deadline: "2026-10-03",
    resolving_action: "Bring a Prep Pack and records to legal aid or a lawyer",
    inaction_consequence_short: "The notice says the sender may take further action after the stated date.",
    reminder_schedule: ["T-7d", "T-3d", "T-1d"],
    status: "open",
  },
];

export const demoAnswer = (question: string): AskResponse => ({
  answer: question.toLowerCase().includes("deadline")
    ? "The document names two dates: a written response within seven days and a move-out date of 03 October 2026. The response-period language is in Clause 2. [clause_demo_02]"
    : "This document says a written response is due within seven days and describes a claimed balance of INR 38,500. It does not state the legal effect outside the document itself because jurisdiction is not confirmed. [clause_demo_02] [clause_demo_03]",
  citations: ["clause_demo_02", "clause_demo_03"],
  confidence: "high",
  disclaimer: DISCLAIMER,
});

export function isDemoDocument(documentId: string | undefined): boolean {
  return documentId === DEMO_DOCUMENT_ID;
}

export function findDemoDecision(decisionId: string | undefined): DecisionPoint | undefined {
  return demoDecisions.find((decision) => decision.decision_id === decisionId);
}
