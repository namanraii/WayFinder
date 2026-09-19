# Wayfinder — Full Build Specification

### "Don't Summarize the Document. Show Me My Move."

**Document purpose:** This is a complete, implementation-grade specification for Wayfinder — an AI-powered legal assistance product built for the "AI for Legal Assistance & Access" problem statement. It is written to be handed directly to an LLM coding agent (or a human engineer) to build from, with no additional design decisions required to start. Where a decision genuinely can't be made without real-world input (e.g., "which jurisdiction's rent-control corpus to license first"), that is flagged explicitly as an open input, not left ambiguous.

**How to use this document if you are an LLM building this project:**
1. Read §1–6 for the product concept and why it's shaped this way — don't skip this even if you only care about code, because several implementation choices (schema-enforced inaction branches, tier-gated generation) only make sense in light of the reasoning here.
2. Read §7 for the exact data schemas — these are the contracts every module below must produce and consume.
3. Build in the phase order given in §17 (Implementation Roadmap) — each phase is scoped to be independently demoable and testable before the next begins.
4. §16 gives the repository layout, §14–15 give API and prompt specifications, §11–13 give the core engine logic in pseudocode-to-near-code detail.
5. Do not skip §18 (Guardrails) when implementing any generation step — every generation point in §17 has a corresponding guardrail check that must be wired in at build time, not bolted on after.

---

## 1. Problem Statement (verbatim reference)

> AI for Legal Assistance & Access — Legal information can often be complex, difficult to understand, and challenging to navigate without professional assistance. Build a GenAI-powered solution that makes legal information and basic legal assistance more accessible by helping users understand, compare, and navigate legal documents and information.
>
> Potential use cases: simplifying complex legal documents; comparing contracts, agreements, or policies; highlighting important clauses, obligations, risks, or inconsistencies; answering questions based on provided legal documents; helping users understand their options and potential next steps; generating summaries, checklists, or other actionable outputs; helping users prepare information or questions for a legal professional.
>
> Note: solutions should provide information and assistance, rather than replace professional legal advice. Use cases are illustrative, not exhaustive — original approaches are encouraged.

Every design choice below traces back to one of these lines. Where it doesn't, it's been deliberately left out (see §22, Explicit Non-Goals).

---

## 2. Executive Summary

Wayfinder converts a legal document into a **Decision Record**: a short, ranked list of the real choices the document forces on the user, each with its options, the consequence of each option (including doing nothing — modeled explicitly, not omitted), a deadline, and a triage tier (self-serve / legal-aid recommended / lawyer now).

The insight driving this: non-lawyers rarely get stuck on "I don't understand this clause." They get stuck on "I understand it well enough and still don't know what to do, and I don't realize that not deciding is itself a decision with a default, usually bad, outcome." Every other tool in this space — including two alternative designs evaluated against this one — stops at description (a clearer summary, a risk-tagged clause list, a Q&A chat). Wayfinder's deliverable is the decision itself, with the inaction outcome made unavoidable to see.

Supporting layers (clause extraction, risk flagging, missing-clause detection, comparison, grounded Q&A) exist and are built to real rigor — they are the evidence base a Decision Record is grounded in — but they are not the landing page. The landing page is: *"You have 2 decisions. Here's the first one, here's what happens if you do nothing, here's the deadline."*

---

## 3. Product Pillars

1. **Extract** — parse the document into Decision Points, not just clauses.
2. **Triage** — score each decision on reversibility, stakes, and ambiguity; route to self-serve, legal-aid, or lawyer-now.
3. **Resolve** — for self-serve decisions, generate the actual usable artifact (a draft letter/email/form). For escalated decisions, generate a Prep Pack.
4. **Track** — every deadline becomes a standing countdown with its inaction consequence attached, exportable to calendar, with reminders.

---

## 4. What Makes This Different (competitive frame)

This spec was developed alongside two alternative designs for the same brief — one graph/access-first (codenamed LexLens: Semantic Legal Graph, Asymmetry Detector comparing clauses to fairness templates, WhatsApp/voice-first delivery) and one report/module-first (codenamed LexBridge: Legal Knowledge Graph, clause-schema extraction, Compare Studio, Lawyer Pack). Both are solid, complete designs. Wayfinder deliberately borrows their strongest mechanisms rather than re-inventing them:

- **From the graph-first design:** deterministic graph traversal for causal/consequence chains, with the LLM used only for phrasing, never for structural reasoning. This is the correct hallucination-control pattern and Wayfinder uses it for the Cost-of-Inaction Reasoner specifically (§12).
- **From the report-first design:** the clause-level JSON schema discipline, explainable risk scoring, and guardrail phrasing rules (banned/required phrase lists) — these are genuinely well-specified in that design and are adopted near-verbatim in §7.2 and §18.

What Wayfinder does *not* borrow: a standalone named "fairness score" or "nutrition label" artifact as the primary user-facing output. Fairness/asymmetry comparison is real and useful (§11.5) but is demoted to **evidence that feeds triage scoring**, not a number the user has to interpret unassisted — because neither alternative design (nor this one) has actually solved the jurisdiction-correct template-corpus problem (§10), and presenting a confident-looking score on top of an unsolved data problem is a trust risk, not a feature.

---

## 5. Target Users & Primary Scenarios

**Primary users:** tenants (notices, leases), gig/freelance workers (service contracts, payment disputes), employees (offer letters, termination/severance letters), consumers (Terms of Service, warranty/refund disputes, debt-collection letters), small vendors (supplier/client contracts).

**Secondary users:** legal aid clinics/NGOs (a Decision Record is a better *intake* artifact than a raw summary — it's pre-triaged by urgency), HR teams, paralegals.

**Sharpest-fit scenario:** any document with a clock attached — eviction notice, demand letter, termination notice, cure period, limitation period, arbitration opt-out window. This is where "what happens if I do nothing" stops being a nice framing and becomes the entire point of the product.

**Three scenarios used throughout this spec as running examples** (referenced in schemas, prompts, and tests below):
- **Scenario A — Eviction/Notice-to-Vacate:** tenant photographs a notice; 21-day statutory response window; failure to respond = deemed acceptance, loses dispute right.
- **Scenario B — Freelance Contract Redraft:** freelancer uploads original + revised service agreement; payment-dispute window shortened, revision-limit clause removed.
- **Scenario C — Consumer ToS Arbitration Opt-Out:** user uploads platform Terms of Service; buried 30-day arbitration opt-out window with no obvious "risk," but a real, easily-missed deadline.

---

## 6. Non-Functional Requirements

- **Correctness over fluency:** every stated consequence must trace to a cited clause span or be explicitly flagged as jurisdiction-unconfirmed (§10, §18). A confident-sounding wrong answer is a worse outcome than a correctly-hedged "I don't know."
- **Availability of a low-bandwidth path:** the core "you have N decisions" output must be renderable as plain text/voice, not just a rich UI — this is a functional requirement of the access-to-justice goal, not a stretch feature (§19.7).
- **Auditability:** every generated decision, triage tier, and artifact must be traceable — model version, prompt version, source spans, confidence — for later human review (legal-aid partner, internal QA, or the user themselves).
- **Data minimization:** documents may contain highly sensitive personal, financial, or medical information (e.g., in a severance agreement or medical-legal notice). Default to the shortest reasonable retention, encrypt at rest, and never use uploaded documents for model training without explicit, separate opt-in.

---

## 7. Data Schemas (authoritative contracts)

Every module in this spec reads and/or writes these shapes. Treat this section as the source of truth — if code and this section disagree, this section wins and the code is the bug.

### 7.1 Document

```json
{
  "document_id": "doc_a1b2c3",
  "user_id": "usr_001",
  "uploaded_at": "2026-09-10T14:22:00Z",
  "original_filename": "eviction_notice.pdf",
  "storage_uri": "s3://wayfinder-docs/usr_001/doc_a1b2c3.pdf",
  "mime_type": "application/pdf",
  "page_count": 2,
  "language_detected": "en",
  "document_type": "legal_notice",
  "document_type_confidence": 0.91,
  "jurisdiction": {
    "status": "confirmed | inferred | unknown",
    "country": "IN",
    "state_or_region": "Tamil Nadu",
    "source": "user_input | governing_law_clause | address_field | none"
  },
  "role_context": "tenant",
  "processing_status": "ingested | segmented | extracted | graphed | decisions_ready | failed",
  "consent": {
    "consented_at": "2026-09-10T14:21:30Z",
    "training_opt_in": false
  }
}
```

`jurisdiction.status` is load-bearing — see §10. It is never silently defaulted to "confirmed."

### 7.2 Clause (adapted from clause-schema pattern referenced in §4)

```json
{
  "clause_id": "clause_09",
  "document_id": "doc_a1b2c3",
  "clause_title": "Response Period",
  "clause_type": "notice_period",
  "page": 1,
  "char_span": [340, 512],
  "original_text": "Tenant must respond in writing within 21 days of this notice or the grounds herein shall be deemed accepted.",
  "plain_language": "You have 21 days from the date of this notice to respond in writing. If you don't, the reasons given for eviction are treated as if you agreed to them.",
  "obligations": [
    {
      "actor": "tenant",
      "action": "respond in writing",
      "deadline_relative": "21 days from notice date",
      "deadline_absolute": "2026-10-03",
      "condition": "to preserve dispute rights"
    }
  ],
  "rights": [],
  "risks": [
    {
      "type": "deadline_pressure",
      "description": "Short, hard deadline with a severe default-if-missed consequence.",
      "severity": "high"
    }
  ],
  "missing_elements": ["accepted method of written response (mail vs. email vs. in-person)"],
  "related_clause_ids": ["clause_04"],
  "feeds_decision_id": "dec_01",
  "extraction_confidence": 0.94
}
```

`feeds_decision_id` is the field that makes decision-first UI possible: every clause always knows which decision it's evidence for. A clause with no `feeds_decision_id` is still shown (in the supporting Clause Explorer view) but never surfaces on the primary Decision Record screen.

### 7.3 Decision Point (the centerpiece schema — see full worked example in §11.1)

```json
{
  "decision_id": "dec_01",
  "document_id": "doc_a1b2c3",
  "title": "Respond to the notice or lose your dispute right",
  "triggering_clause_ids": ["clause_04", "clause_09"],
  "deadline": "2026-10-03",
  "days_remaining": 20,
  "options": [
    {
      "option_id": "opt_a",
      "action": "File a written objection with the housing authority",
      "consequence": "Preserves your right to contest the eviction grounds in a hearing.",
      "effort": "low",
      "cost": "none (self-serve template available)",
      "is_default_if_inaction": false
    },
    {
      "option_id": "opt_b",
      "action": "Negotiate directly with landlord for extended move-out date",
      "consequence": "May avoid formal proceedings but creates no binding record if landlord reneges.",
      "effort": "medium",
      "cost": "none",
      "is_default_if_inaction": false
    },
    {
      "option_id": "opt_c",
      "action": "Do nothing",
      "consequence": "Under Clause 9, failure to respond within 21 days is treated as acceptance of the notice. You lose the right to contest grounds for eviction.",
      "effort": "none",
      "cost": "loss of dispute right",
      "is_default_if_inaction": true
    }
  ],
  "triage_tier": "self_serve_with_escalation_path",
  "triage_scores": { "reversibility": "low", "stakes": "high", "ambiguity": "low" },
  "triage_reasoning": "Clear statutory notice period with a standard template response available. Escalate immediately if the landlord disputes the response — flagged as follow-up decision dec_02.",
  "resolution_artifact_id": "artifact_001",
  "confidence": "high",
  "jurisdiction_confidence_note": null,
  "source_spans": ["clause_04:0-118", "clause_09:340-512"]
}
```

**Schema-level invariant (enforced by validation, not convention):** any Decision Point with a non-null `deadline` MUST contain at least one option with `is_default_if_inaction: true`, and that option's `consequence` field must be non-empty and must reference at least one entry in `source_spans`. A Decision Point that fails this validation is rejected and regenerated — it is never shown to the user in an incomplete state. This is the mechanism (not just the design intent) that guarantees cost-of-inaction is never silently dropped.

### 7.4 Triage Tier (enum, with generation permissions)

| Tier | Meaning | Permitted resolution_artifact type |
|---|---|---|
| `self_serve` | Low stakes, low ambiguity, reversible | Drafted letter/email/form, ready to send |
| `self_serve_with_escalation_path` | Low/medium now, but flagged to re-triage if counterparty disputes | Drafted letter/email/form + explicit follow-up trigger |
| `legal_aid_recommended` | Medium stakes or ambiguity | Prep Pack only |
| `lawyer_now` | High stakes and/or low reversibility | Prep Pack only — drafted artifact generation is blocked at the API layer, not just discouraged in UI |

### 7.5 Resolution Artifact

```json
{
  "artifact_id": "artifact_001",
  "decision_id": "dec_01",
  "type": "objection_letter",
  "status": "draft",
  "content": "To: [Housing Authority]\nFrom: [Tenant Name]\nRe: Objection to Notice dated ...",
  "fields_to_fill": ["tenant_name", "authority_name", "notice_date"],
  "generated_at": "2026-09-10T14:25:00Z",
  "disclaimer": "This is a template letter, not a filed legal instrument. Sending it does not constitute legal representation. Review before sending.",
  "model_version": "wayfinder-gen-v1",
  "prompt_version": "objection_letter_v3"
}
```

### 7.6 Prep Pack

```json
{
  "prep_pack_id": "pack_001",
  "decision_id": "dec_02",
  "contents": {
    "document_summary": "...",
    "relevant_clause_excerpts": ["clause_04", "clause_09"],
    "timeline": [{"date": "2026-09-10", "event": "Notice received"}],
    "questions_for_professional": ["Does a verbal extension from the landlord count as valid notice?"],
    "what_has_been_tried": [],
    "urgency_note": "Response deadline in 20 days."
  },
  "export_formats": ["pdf", "share_link"]
}
```

### 7.7 Comparison Result

```json
{
  "comparison_id": "cmp_001",
  "document_id_a": "doc_a1b2c3",
  "document_id_b": "doc_d4e5f6",
  "clause_diffs": [
    {
      "clause_type": "payment_dispute_window",
      "status": "changed",
      "before": "30 days",
      "after": "10 days",
      "affected_decision_ids": ["dec_03"],
      "risk_delta": "increased"
    }
  ],
  "decision_impact_summary": "2 of your decisions changed as a result of this redraft."
}
```

### 7.8 Deadline Tracker Entry

```json
{
  "tracker_id": "trk_001",
  "decision_id": "dec_01",
  "deadline": "2026-10-03",
  "resolving_action": "Send objection letter (artifact_001)",
  "inaction_consequence_short": "You lose your right to contest the eviction grounds.",
  "reminder_schedule": ["T-7d", "T-3d", "T-1d"],
  "status": "open | resolved | missed",
  "calendar_export_ics_uri": "s3://.../trk_001.ics"
}
```

---

## 8. Document Graph Model

Parties, obligations, deadlines, penalties, and cross-references are stored as a graph — deterministic traversal over this graph, not LLM free-text reasoning, is what powers the Cost-of-Inaction Reasoner (§12) and the Decision Extraction Engine's consequence chains (§11).

**Node types:** `Document`, `Party`, `Clause`, `Obligation`, `Right`, `Deadline`, `PaymentTerm`, `Penalty`, `DecisionPoint`.

**Edge types:** `imposes` (Clause → Obligation), `grants` (Clause → Right), `triggers` (Deadline → Penalty, on miss), `resolves` (Obligation → Deadline, on completion), `references` (Clause → Clause), `conflicts_with` (Clause → Clause), `feeds` (Clause → DecisionPoint).

**Storage:** Neo4j (or any labeled-property graph store) for production; for MVP, a simplified adjacency structure in Postgres (§9.4) is sufficient and avoids standing up a second database before it's needed — migrate to a dedicated graph store only once traversal queries (§12) become a measured bottleneck, not preemptively.

**Why a graph and not just embeddings/RAG:** consequence chains ("miss this deadline → triggers this penalty clause → triggers this termination right") are structurally causal, not semantically similar. A vector search for "what happens if I miss the deadline" can retrieve a relevant-sounding but wrong clause; a graph traversal from the specific `Deadline` node along `triggers` edges cannot silently substitute the wrong penalty. Reserve the LLM for turning a traversed path into plain language, never for finding the path.

---

## 9. System Architecture

```
┌───────────────┐   ┌───────────────┐   ┌──────────────────┐
│ Web PWA        │   │ WhatsApp/SMS  │   │ Voice (STT/TTS,  │
│ React + TS     │   │ bridge        │   │ Indic languages) │
└──────┬────────┘   └──────┬────────┘   └────────┬─────────┘
       └───────────────────┼─────────────────────┘
                           ▼
              ┌─────────────────────────┐
              │ API Gateway (FastAPI)    │ auth, rate-limit, PII redaction
              └────────────┬────────────┘
                           ▼
     ┌─────────────────────────────────────────────────┐
     │  Wayfinder Core Services (§9.2)                   │
     │  ① Ingestion Service                               │
     │  ② Clause Segmentation & Classification Service    │
     │  ③ Document Graph Service          ────────────────┼──► Neo4j / Postgres adjacency (MVP)
     │  ④ Decision Extraction Service                      │  <- core differentiator
     │  ⑤ Cost-of-Inaction Reasoner                        │
     │  ⑥ Triage Service                                   │
     │  ⑦ Resolution Artifact Service                      │
     │  ⑧ Comparison Service                                │
     │  ⑨ Deadline Tracker Service                          │
     │  ⑩ Q&A Service                                       │
     └───────────┬───────────────────────────────────────┘
                 ▼
     LLM Orchestrator (tool-calling, retrieval-anchored, schema-validated output)
     Vector DB (clause embeddings, pgvector for MVP) + Template/Precedent Corpus (jurisdiction-tagged) + Guardrails layer
                 ▼
     Postgres (primary datastore) · S3-compatible object storage (documents, exports) · Redis (queue/cache)
```

### 9.1 Request flow (upload to Decision Record — the critical path)

1. Client uploads file → API Gateway → stored to object storage → `Document` row created (`processing_status: ingested`).
2. Async job enqueued (Redis + a worker queue) for ingestion pipeline.
3. Ingestion Service: OCR (if needed) → text extraction → language + jurisdiction-signal detection → document classification. Updates `Document.processing_status: segmented`.
4. Clause Segmentation Service: splits into clauses, classifies each, runs structured extraction (§7.2 schema) per clause. Writes `Clause` rows. Updates `processing_status: extracted`.
5. Document Graph Service: builds graph nodes/edges from clauses. Updates `processing_status: graphed`.
6. Decision Extraction Service: identifies Decision Points from the graph + clauses (§11). Writes `DecisionPoint` rows, schema-validated (§7.3 invariant). Updates `processing_status: decisions_ready`.
7. Triage Service: scores each Decision Point (§13). Updates `triage_tier` on each.
8. Client polls or receives a push notification when `processing_status: decisions_ready` — renders the Decision Record screen.
9. On-demand thereafter: Resolution Artifact generation, Q&A, Comparison, Deadline Tracker export.

Steps 3–7 should complete in well under a minute for a typical 2–10 page document.

### 9.2 Service responsibilities

**Ingestion Service.** Accepts PDF/image/DOCX/plain text. Runs OCR (Tesseract for MVP). Detects language. Attempts jurisdiction signal extraction from a governing-law clause pattern match or address-field heuristic — does not guess if no clear signal exists (writes `jurisdiction.status: unknown`, never `confirmed`, without an explicit signal or user input).

**Clause Segmentation & Classification Service.** Splits raw text into clause-level units (numbered/lettered section boundaries, paragraph breaks, common legal section headers). For each clause, calls the LLM orchestrator with the Clause Extraction prompt (§15.1) to populate the §7.2 schema. Validates output against schema before writing; malformed responses are retried once with an error-correction follow-up prompt, then flagged for manual review if still invalid.

**Document Graph Service.** Consumes `Clause` rows to construct graph nodes/edges (§8). Deterministic, rule-based — no LLM call in this service.

**Decision Extraction Service.** The core differentiator — see §11. Consumes the graph + clauses, identifies Decision Points, calls the LLM orchestrator with the Decision Extraction prompt (§15.2), validates against the §7.3 schema invariant, retries/rejects malformed output.

**Cost-of-Inaction Reasoner.** Invoked for every Decision Point with a deadline. Deterministic graph traversal from the `Deadline` node along `triggers` edges to find the consequence chain; LLM call only to phrase the traversed chain into the `consequence` text of the `is_default_if_inaction` option (§15.3). If traversal finds no `triggers` edge, the reasoner writes: `"This document does not specify what happens if you don't respond by this date."` and lowers confidence — it never fabricates a consequence not present in the graph.

**Triage Service.** Deterministic scoring function (§13) over associated clause risk levels, document-type category, and jurisdiction confidence — not an LLM judgment call.

**Resolution Artifact Service.** For `self_serve` / `self_serve_with_escalation_path` tiers: fills a jurisdiction-tagged template (§14.3) with extracted facts via the Artifact Generation prompt (§15.4). For `legal_aid_recommended` / `lawyer_now` tiers: generates a Prep Pack (§7.6) only — the API layer rejects any request to generate a send-ready draft for a `lawyer_now` decision (§18.6); this is enforced server-side, not just hidden in the UI.

**Comparison Service.** Aligns clauses across two documents by type + semantic similarity (embedding cosine similarity, LLM confirmation for near-threshold matches), classifies each as same/similar/changed/added/removed, cross-references `feeds_decision_id` to produce the decision-impact-filtered summary (§7.7).

**Deadline Tracker Service.** Reads open Decision Points with deadlines, generates `.ics` exports, schedules reminders at the intervals in §7.8.

**Q&A Service.** Retrieval-anchored: embed the question, retrieve top-k clause chunks via pgvector, call the LLM orchestrator with the Q&A prompt (§15.5), require citation to `clause_id` + `char_span` in every answer, attach confidence and a decision-link where relevant.

### 9.3 LLM Orchestrator

A thin, vendor-agnostic wrapper responsible for: prompt templating and versioning (every prompt has a version string, logged with every generation), schema-validated structured output (reject-and-retry on validation failure), and centralized guardrail enforcement (banned-phrase check, citation-presence check, tier-gating check) run on every generation *before* it's written to the database — guardrails are a pre-write gate, not a post-hoc filter on display.

### 9.4 MVP Graph Simplification (Postgres adjacency, no Neo4j required to start)

```sql
CREATE TABLE graph_nodes (
  node_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  node_type TEXT NOT NULL, -- 'party' | 'clause' | 'obligation' | 'right' | 'deadline' | 'penalty' | 'decision_point'
  ref_id TEXT NOT NULL,
  properties JSONB
);

CREATE TABLE graph_edges (
  edge_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  from_node_id TEXT REFERENCES graph_nodes(node_id),
  to_node_id TEXT REFERENCES graph_nodes(node_id),
  edge_type TEXT NOT NULL -- 'imposes' | 'grants' | 'triggers' | 'resolves' | 'references' | 'conflicts_with' | 'feeds'
);
```

A `triggers`-edge traversal for the Cost-of-Inaction Reasoner is a recursive CTE from a `deadline`-type node to connected `penalty`-type nodes — no separate graph database needed until traversal complexity or query volume genuinely demands it.

---

## 10. Jurisdiction Honesty (design constraint that touches every generation step)

Fairness/consequence templates are jurisdiction-specific (rent control varies by state, labor law by sector and region, consumer protection by country). No single template corpus can be complete or always current, and no design in this space — including this one — solves that data-acquisition problem outright. What Wayfinder does instead is make jurisdiction confidence a **propagating input**, not a cosmetic label:

- `Document.jurisdiction.status` is `confirmed` only when set by explicit user input or an unambiguous governing-law clause match. Address-field inference alone sets `inferred`, which is treated as lower-confidence throughout.
- Any Decision Point whose consequence text depends on a statutory default (not just the document's own terms) must check `jurisdiction.status` before generation. If `unknown`, the Cost-of-Inaction Reasoner (§9.2, §12) restricts itself to consequences that are stated in the document's own text and explicitly declines to state a statutory backstop, with the exact phrasing specified in §18.4.
- Triage confidence is **downgraded, never upgraded**, by jurisdiction uncertainty — a decision that would score `self_serve` under a confirmed jurisdiction automatically drops at least one tier under `unknown` jurisdiction (§13.3).

This is implemented as a single shared guard function (`check_jurisdiction_gate(document, decision_draft)`) called by both the Decision Extraction Service and the Triage Service — not duplicated logic in each.

---

## 11. Decision Extraction Engine — Full Logic

This is the module that doesn't exist in a comparable form in typical legal-AI designs, so it gets the most detailed treatment.

### 11.1 What counts as a Decision Point

A Decision Point is created when the graph (§8) contains **either**:
- (a) A `Deadline` node connected by an `imposes` edge to an `Obligation` where the `actor` includes the user's stated `role_context` (e.g., "tenant," "employee"), **or**
- (b) A `Clause` node tagged with `clause_type` in a fixed set of decision-bearing types: `termination`, `notice_period`, `dispute_resolution`, `renewal` (especially auto-renewal), `arbitration_optout`, `payment_dispute`, `cure_period`, `right_of_first_refusal`, `indemnity_trigger`.

Clauses that don't meet either condition (e.g., a standard confidentiality clause with no near-term action implied) are extracted and stored (§7.2) but do **not** generate a Decision Point — they remain reachable through the supporting Clause Explorer (§Module 5 in the earlier design, retained here as a secondary UI surface, not removed).

### 11.2 Extraction algorithm (per document)

```
for each clause in document.clauses:
    if clause.clause_type in DECISION_BEARING_TYPES or clause.obligations[].deadline_relative is not None:
        candidate = build_decision_candidate(clause, graph)
        if candidate is not None:
            candidates.append(candidate)

merged_candidates = merge_related_candidates(candidates, graph)
# merges candidates whose triggering clauses are connected by `references` or
# `conflicts_with` edges into a single Decision Point, so e.g. a notice-period
# clause and its related termination-fee clause become ONE decision, not two

for candidate in merged_candidates:
    decision_draft = call_llm(DECISION_EXTRACTION_PROMPT, candidate, graph_context)
    decision_draft.options = ensure_inaction_option(decision_draft, candidate, graph)
    # ensure_inaction_option is NOT optional — see 11.3

    validated = validate_against_schema(decision_draft, DECISION_SCHEMA)
    if not validated.ok:
        decision_draft = call_llm(DECISION_EXTRACTION_REPAIR_PROMPT, decision_draft, validated.errors)
        validated = validate_against_schema(decision_draft, DECISION_SCHEMA)
        if not validated.ok:
            flag_for_manual_review(decision_draft, validated.errors)
            continue

    decision_draft.jurisdiction_confidence_note = check_jurisdiction_gate(document, decision_draft)
    persist(decision_draft)

decisions = rank_by(deadline_proximity, then=stakes_score)  # nearest + highest-stakes surfaces first
```

### 11.3 `ensure_inaction_option` — the schema-invariant enforcement, in detail

```
function ensure_inaction_option(decision_draft, candidate, graph):
    if candidate.deadline is None:
        return decision_draft  # no deadline, no inaction branch required

    if any(opt.is_default_if_inaction for opt in decision_draft.options):
        return decision_draft  # LLM already produced one — still validate it below

    # LLM omitted the inaction branch — this is a hard failure, not a soft one.
    # Invoke the Cost-of-Inaction Reasoner directly (deterministic path) rather
    # than re-prompting and hoping — this guarantees the branch exists even if
    # the generation step is unreliable.
    inaction_option = cost_of_inaction_reasoner.build(candidate.deadline_node, graph)
    decision_draft.options.append(inaction_option)
    return decision_draft
```

This two-layer approach (prompt the LLM to include it, then deterministically backfill if it didn't) is why the invariant in §7.3 can be described as *guaranteed* rather than *usually present* — there is a non-LLM fallback path, not just an instruction.

### 11.4 Merging related clauses into one decision

Two clauses that are graph-connected via `references` or that both feed the same underlying real-world choice (e.g., a notice-period clause and the termination-fee clause it triggers) should surface as **one** Decision Point with multiple `triggering_clause_ids`, not two separate ones — presenting them separately would fragment a single real choice into confusing duplicates. `merge_related_candidates` groups clause-candidates connected by `references`/`conflicts_with` edges within a configurable graph-distance (default: 1 hop) before the LLM extraction call, so the LLM sees the full context and produces one coherent decision, rather than merging two independently-generated decisions after the fact (which risks inconsistent phrasing between them).

---

## 12. Cost-of-Inaction Reasoner — Full Logic

```
function build(deadline_node, graph):
    consequence_path = graph.traverse(
        start=deadline_node,
        edge_types=["triggers"],
        max_hops=3  # penalty -> secondary penalty -> termination, typically enough
    )

    if consequence_path.is_empty():
        return {
            "option_id": generate_id(),
            "action": "Do nothing",
            "consequence": "This document does not specify what happens if you don't act by this date.",
            "effort": "none",
            "cost": "unknown — not specified in document",
            "is_default_if_inaction": true
        }

    plain_language_chain = call_llm(
        INACTION_PHRASING_PROMPT,
        consequence_path,          # the traversed nodes/edges, structured
        instruction="Phrase this exact causal chain in plain language. Do not add
                      any consequence not present in the provided chain."
    )

    return {
        "option_id": generate_id(),
        "action": "Do nothing",
        "consequence": plain_language_chain,
        "effort": "none",
        "cost": summarize_stakes(consequence_path),
        "is_default_if_inaction": true,
        "source_spans": extract_source_spans(consequence_path)
    }
```

The critical property: the LLM call here receives the already-traversed graph path as structured input and is instructed only to phrase it — it is never asked to determine *whether* a consequence exists or *what* it is from free text. That determination is 100% deterministic graph traversal. This is the single most important hallucination-control decision in the whole system, because a fabricated consequence here (telling a user a false, either falsely severe or falsely lenient, outcome of inaction) is the highest-harm failure mode the product can produce.

---

## 13. Triage Service — Full Scoring Logic

### 13.1 Inputs per Decision Point

- Max `risk.severity` across `triggering_clause_ids`' associated clause risks (from §7.2).
- Whether `document_type` falls in a fixed high-stakes category list: `eviction_notice`, `termination_letter`, `custody_related`, `debt_collection`, `criminal_matter`, `immigration_related`, `domestic_violence_related` (this list intentionally mirrors the high-risk-escalation categories used elsewhere in this problem space, since it reflects real-world consensus on what warrants caution, not a novel judgment call).
- Whether resolving this decision requires an action that is hard to reverse (signing something, missing a filing deadline, admitting something in writing) — a fixed keyword/clause-type heuristic (`termination`, `release_of_claims`, `waiver`, `admission`) flags `reversibility: low`.
- `document.jurisdiction.status`.

### 13.2 Scoring function (deterministic, not LLM-judged)

```
function score_triage(decision, clauses, document):
    stakes = "high" if (max_clause_risk(decision, clauses) == "high"
                         or document.document_type in HIGH_STAKES_CATEGORIES) else \
             "medium" if max_clause_risk(decision, clauses) == "medium" else "low"

    reversibility = "low" if any(irreversible_keyword_match(c) for c in decision.triggering_clauses) else "high"

    ambiguity = "high" if (has_missing_elements(decision, clauses)
                            or has_conflicting_clauses(decision, clauses)) else "low"

    tier = compute_tier(stakes, reversibility, ambiguity)
    tier = apply_jurisdiction_gate(tier, document.jurisdiction.status)  # can only downgrade, never upgrade

    return { "triage_tier": tier,
             "triage_scores": {"stakes": stakes, "reversibility": reversibility, "ambiguity": ambiguity},
             "triage_reasoning": render_reasoning_text(stakes, reversibility, ambiguity, document.jurisdiction.status) }
```

### 13.3 Tier computation table

| Stakes | Reversibility | Ambiguity | Base Tier |
|---|---|---|---|
| low | high | low | `self_serve` |
| low | high | high | `self_serve_with_escalation_path` |
| medium | high | low | `self_serve_with_escalation_path` |
| medium | any | high | `legal_aid_recommended` |
| medium | low | any | `legal_aid_recommended` |
| high | any | any | `lawyer_now` |

`apply_jurisdiction_gate`: if `jurisdiction.status == "unknown"`, downgrade `self_serve` → `self_serve_with_escalation_path`, and `self_serve_with_escalation_path` → `legal_aid_recommended`. `lawyer_now` is never downgraded further (it's already the most conservative tier) and is also never upgraded away from — jurisdiction confidence can only make the system more cautious, never less.

`render_reasoning_text` produces the human-readable string shown in `triage_reasoning` (§7.3 example) — this is templated from the score inputs, not a separate free-form LLM explanation, so the stated reasoning always matches the actual score that was computed (no risk of the displayed explanation drifting from the real logic).

---

## 14. Supporting Layers (built to standard rigor, not the differentiator, but required for grounding)

### 14.1 Clause Extraction, Risk Flags, Missing-Clause & Inconsistency Detection

Standard structured extraction per clause (§7.2 schema): plain-language rewrite, obligations, rights, risks (type + severity + explanation), missing common protections for the detected `document_type` (notice period, liability cap, dispute resolution, governing law, refund terms, data deletion, force majeure, severability — checked against a fixed per-document-type checklist), and inconsistency detection (conflicting deadlines/payment terms/defined-term usage across clauses, detected via graph `conflicts_with` edges created when two clauses' extracted obligations contradict on the same subject). This layer feeds the Decision Extraction Engine (§11) and the Triage Service (§13) — it is not a separate user-facing report by default, though it remains available via the Clause Explorer secondary UI (§19.3).

### 14.2 Comparison Engine

See §9.2 (Comparison Service) and §7.7 schema. Clause alignment: embed both documents' clauses, match by `clause_type` first, then cosine similarity within type for the specific pairing, LLM confirmation only for near-threshold ambiguous pairs. Output filtered through `feeds_decision_id` so the user-facing result leads with "N of your decisions changed," with the raw clause-diff still available underneath for anyone who wants it.

### 14.3 Resolution Artifact Templates

A fixed, versioned set of templates, each jurisdiction-taggable and fact-fillable:

| Template ID | Use case | Fields required |
|---|---|---|
| `objection_letter_v1` | Respond to a notice, contest stated grounds | tenant/recipient name, authority/counterparty name, notice date, objection grounds |
| `clarification_email_v1` | Ask a counterparty to clarify an ambiguous clause | recipient, clause reference, specific question |
| `formal_notice_v1` | Give required-format notice (e.g., 30-day termination) | sender, recipient, effective date, reason (optional) |
| `deposit_itemization_request_v1` | Request itemized deduction accounting | landlord name, move-out date, deposit amount |
| `arbitration_optout_v1` | Exercise a time-boxed arbitration opt-out | account/user identifier, service name, opt-out deadline |
| `data_deletion_request_v1` | Consumer data-deletion/opt-out request | service name, account identifier, applicable regulation reference if known |

Each template's fillable fields map directly to fields extractable from the triggering clause(s) (`§7.2.obligations`, party names from `Document`/graph `Party` nodes) — the Resolution Artifact Service auto-fills what it can and marks the rest `fields_to_fill` for the user to complete (§7.5).

### 14.4 Q&A

Retrieval-anchored, cited, confidence-labeled — see §9.2 and §15.5. No differentiation claimed here; built to the same rigor any serious entrant in this space should have.

---

## 15. Prompt Specifications

All prompts are versioned strings (tracked in `prompt_version`, §7 schemas) and should live in a dedicated `prompts/` directory (§16), not inline in service code, so they can be iterated and evaluated independently of application logic.

### 15.1 Clause Extraction Prompt (`clause_extraction_v1`)

```
SYSTEM:
You are extracting structured information from ONE clause of a legal document.
You must output ONLY valid JSON matching the provided schema. Do not add
commentary outside the JSON.

Rules:
- plain_language must be a faithful, non-editorializing rewrite — do not add
  legal conclusions not present in the original text.
- Every entry in `risks` must include a `description` that is directly
  traceable to the clause text.
- `missing_elements` should only list protections that are STANDARD for this
  clause_type and genuinely absent from this specific clause — do not invent
  a missing element that doesn't apply to this clause type.
- If you are uncertain about clause_type, choose the closest match from the
  provided taxonomy and set extraction_confidence below 0.7.

INPUT:
- clause_text: <raw clause text>
- clause_taxonomy: <fixed list of clause_type values>
- document_type: <detected document type, for context>

OUTPUT SCHEMA: <§7.2 JSON schema>
```

### 15.2 Decision Extraction Prompt (`decision_extraction_v1`)

```
SYSTEM:
You are identifying a REAL DECISION a user faces because of one or more
related clauses in a legal document. A "decision" is a genuine choice with
consequences — not just a fact about the document.

Rules:
- title must describe the decision from the USER's perspective, in plain
  language (e.g. "Respond to the notice or lose your dispute right" — NOT
  "Notice period clause").
- You MUST include an option with is_default_if_inaction: true if a deadline
  is present. Its consequence must be grounded ONLY in the provided clause
  text and graph context — do not state a consequence not present there.
- Every option's consequence must be traceable to specific clause text.
- Never state a legal conclusion ("you will win," "this is illegal"). Use
  hedged, informational phrasing ("this may," "consider," "this appears").
- If jurisdiction_status is "unknown" and a consequence would normally rely
  on a statutory default rather than the document's own text, state that
  explicitly instead of assuming the default applies.

INPUT:
- triggering_clauses: <full §7.2 objects for each merged clause>
- graph_context: <relevant nodes/edges from Document Graph>
- document_type, role_context, jurisdiction_status

OUTPUT SCHEMA: <§7.3 JSON schema, minus resolution_artifact_id/triage fields
  which are populated by later stages>
```

### 15.3 Inaction Consequence Phrasing Prompt (`inaction_phrasing_v1`)

```
SYSTEM:
You will be given an already-determined causal chain of clauses/penalties
(NOT raw text — a structured path). Your ONLY job is to phrase this exact
chain in plain, non-alarmist, non-legal-conclusion language. Do not add,
remove, or reorder any step in the chain. Do not speculate about consequences
not present in the provided path.

INPUT:
- consequence_path: <structured list of traversed graph nodes/edges>

OUTPUT:
- A single plain-language paragraph describing the chain, ending with the
  concrete outcome (e.g., "...which means you lose the right to contest the
  eviction grounds.")
```

### 15.4 Resolution Artifact Generation Prompt (`artifact_generation_v1`)

```
SYSTEM:
You are filling a legal correspondence TEMPLATE with facts extracted from a
document. You are not drafting free-form legal argument.

Rules:
- Use ONLY the template structure provided — do not invent new sections.
- Fill fields from provided extracted_facts where available; leave
  placeholders (in [brackets]) for anything not extractable.
- Include the disclaimer text verbatim at the end (see §18.1).
- Do NOT include this generation step at all if triage_tier is "lawyer_now"
  — this should be blocked before the prompt is ever called (§9.2, §18.6),
  this rule exists as defense-in-depth only.

INPUT:
- template_id, template_structure
- extracted_facts: <from Decision Point's triggering clauses + Document parties>

OUTPUT:
- Filled template text + list of remaining fields_to_fill
```

### 15.5 Q&A Prompt (`qa_grounded_v1`)

```
SYSTEM:
Answer the user's question using ONLY the retrieved clause excerpts provided.

Format your answer as:
1. Direct answer
2. Source clause citation(s) — clause_id and a short quoted reference
3. Confidence: high | medium | low
4. Related decision (if the retrieved clauses feed an existing Decision
   Point, name it; otherwise omit this line)
5. Disclaimer (verbatim, see §18.1)

If the retrieved excerpts do not contain enough information to answer,
say so explicitly instead of guessing. Never state a legal conclusion.

INPUT:
- question: <user text>
- retrieved_clauses: <top-k clause objects from vector search>
- linked_decisions: <any Decision Points these clauses feed>
```

---

## 16. API Specification (REST, MVP surface)

All endpoints return JSON matching the §7 schemas. Auth via bearer token (session or API key), omitted below for brevity.

```
POST   /documents                          Upload a document. Returns Document (processing_status: ingested).
GET    /documents/{document_id}             Fetch document metadata + processing_status.
GET    /documents/{document_id}/clauses     List extracted Clause objects.
GET    /documents/{document_id}/decisions   List Decision Points (only when processing_status: decisions_ready+), ranked.
GET    /decisions/{decision_id}             Fetch a single Decision Point.
POST   /decisions/{decision_id}/resolve     Request a resolution artifact.
                                             Body: { "option_id": "opt_a" }
                                             Server checks triage_tier; if
                                             "lawyer_now", returns 403 with a
                                             Prep Pack link instead (§18.6) —
                                             never a draft artifact.
GET    /artifacts/{artifact_id}             Fetch a generated Resolution Artifact.
POST   /decisions/{decision_id}/prep-pack   Generate/fetch a Prep Pack (always allowed regardless of tier).
POST   /documents/compare                   Body: { "document_id_a", "document_id_b" }. Returns ComparisonResult.
POST   /documents/{document_id}/ask         Body: { "question": "..." }. Returns grounded Q&A response.
GET    /users/{user_id}/tracker             List all open Deadline Tracker entries across the user's documents.
GET    /tracker/{tracker_id}/export.ics     Download calendar export for a single deadline.
POST   /webhooks/whatsapp                   Inbound WhatsApp message handler (image → ingestion, text → Q&A/decision flow).
```

### 16.1 Example: `GET /documents/{document_id}/decisions` response

```json
{
  "document_id": "doc_a1b2c3",
  "processing_status": "decisions_ready",
  "decisions": [
    { "decision_id": "dec_01", "title": "Respond to the notice or lose your dispute right",
      "deadline": "2026-10-03", "days_remaining": 20, "triage_tier": "self_serve_with_escalation_path" }
  ]
}
```
(Full Decision Point detail, including options and reasoning, is fetched via `GET /decisions/{decision_id}` to keep the list view light — this matters for the WhatsApp/voice rendering path in particular, §19.7.)

### 16.2 Error handling conventions

- `422` for schema validation failures the client should show as "we couldn't fully process this document — try re-uploading a clearer scan," not a raw stack trace.
- `403` specifically (not `400`) for the tier-gating block on `POST /decisions/{decision_id}/resolve` when `triage_tier == "lawyer_now"` — this status code is chosen deliberately so client code can distinguish "you're not allowed to do this by design" from "something went wrong," and render the Prep Pack redirect rather than a generic error.

---

## 17. Database Schema (Postgres DDL, MVP)

```sql
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
  embedding VECTOR(1536)  -- pgvector; dimension depends on embedding model chosen
);

CREATE TABLE decisions (
  decision_id TEXT PRIMARY KEY,
  document_id TEXT REFERENCES documents(document_id),
  title TEXT NOT NULL,
  triggering_clause_ids TEXT[] NOT NULL,
  deadline DATE,
  options JSONB NOT NULL,  -- array of option objects, §7.3
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
    -- Note: full enforcement of "consequence is non-empty AND cites a source
    -- span" is done at the application layer (§11.3), not expressible as a
    -- pure SQL CHECK — this constraint is a coarse backstop, not the primary
    -- enforcement mechanism.
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

-- graph_nodes / graph_edges as defined in §9.4

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
  entity_type TEXT,  -- 'decision' | 'artifact' | 'qa_answer' | 'clause'
  entity_id TEXT,
  model_version TEXT,
  prompt_version TEXT,
  guardrail_checks_passed JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

`generation_audit_log` is written by the LLM Orchestrator (§9.3) on every single generation call, regardless of entity type — this is what makes the auditability non-functional requirement (§6) concretely testable rather than aspirational.

---

## 18. Guardrails — Implementation-Level Detail

Each guardrail below states not just the rule but where in the pipeline it is enforced.

### 18.1 Disclaimer text (verbatim, required on every major output)

> "Wayfinder provides legal information and preparation support to help you understand your documents and options. It does not provide legal advice. For advice specific to your situation, consult a qualified legal professional or legal aid organization."

Enforced by: a template-injection step in the Output Layer that appends this string to every Decision Record view, every Resolution Artifact, every Prep Pack, and every Q&A answer — not left to individual prompts to remember to include, since a prompt-level instruction can be dropped under output-length pressure; this is a post-generation, code-level append that cannot be skipped.

### 18.2 Banned / required phrasing

**Banned (regex/keyword check on all LLM output before it's persisted):** "you should sue," "you will win," "this clause is illegal," "you are entitled to," "I recommend," "my advice is." Any match triggers automatic regeneration with an error-correction prompt; if still present after one retry, the generation is blocked and flagged for manual review rather than shown to the user with the violation intact.

**Required style (soft, checked via a lightweight classifier or keyword presence, not hard-blocking):** hedged phrasing — "this may," "consider," "this appears," "you may want to ask."

### 18.3 Citation requirement

Every `consequence`, `risk.description`, and Q&A answer must reference at least one `clause_id` (via `source_spans` or explicit citation field). Enforced at the schema-validation layer (§9.3) — a generation with an empty citation field on a claim-bearing field fails validation and is retried/rejected, same path as any other schema violation.

### 18.4 Jurisdiction-unknown phrasing (exact required text when `jurisdiction.status == "unknown"` and a consequence would otherwise rely on statutory default)

> "This document doesn't confirm your jurisdiction, so this shows only what the document itself says — not any additional legal defaults that might apply in your area. Confirming your location may change this."

Enforced by: `check_jurisdiction_gate` (§10) injecting this exact string into `jurisdiction_confidence_note` — not generated fresh by the LLM each time, to avoid phrasing drift on a safety-critical disclosure.

### 18.5 Confidence indicators

Every Decision Point, Q&A answer, and clause extraction carries a `confidence` field (`high`/`medium`/`low`), computed from: extraction confidence scores, presence/absence of missing elements, and jurisdiction status — never omitted, never left to the LLM's own self-reported confidence alone (self-reported LLM confidence is a weak signal; this is blended with the deterministic factors above).

### 18.6 High-risk escalation & tier-gated generation (the strongest guardrail in this design)

If `triage_tier == "lawyer_now"`: the `POST /decisions/{decision_id}/resolve` endpoint returns `403` and redirects to Prep Pack generation, **at the API layer**, before any LLM call is made for artifact drafting. This is not a prompt instruction the model could fail to follow — it's a routing decision made in application code based on the already-computed, deterministic triage tier (§13). A user cannot talk their way past this by rephrasing the request, because the request never reaches a generation step capable of producing a draft artifact for that tier.

Document types in the fixed high-stakes list (§13.1) — eviction, custody, domestic violence, criminal, immigration detention, debt collection, disputed termination — automatically contribute to `stakes: high` in every Decision Point they touch, which (per §13.3) always resolves to at minimum `legal_aid_recommended`, regardless of how simple any individual clause looks in isolation.

### 18.7 Hallucination control summary (cross-reference)

- Consequence chains: deterministic graph traversal, LLM phrases only (§12).
- Triage: deterministic scoring function, not LLM judgment (§13.2).
- Missing-element / inconsistency detection: rule-based checklist + graph `conflicts_with` edges, LLM assists in describing but doesn't decide what counts as missing (§14.1).
- Every claim-bearing generation: schema-enforced citation requirement (§18.3).

### 18.8 Privacy & consent

Explicit consent required before upload processing begins (`Document.consented_at` must be non-null before the ingestion job is enqueued). Encryption at rest (S3 server-side encryption or equivalent) and in transit (TLS). `training_opt_in` defaults to `false` at the user level and is never inferred from document upload alone. User-initiated deletion removes the document, its derived clauses/decisions/artifacts, and its vector embeddings — a hard delete, not a soft-delete flag, given the sensitivity of the underlying documents.

### 18.9 Auditability

Every row in `generation_audit_log` (§17) is the mechanism for this — any decision, artifact, or answer can be traced back to the exact prompt version and model version that produced it, which matters both for internal QA and for any legal-aid partner who wants to sanity-check the system's output before relying on it operationally.

---

## 19. Technology Stack (concrete choices, not options — pick one path to avoid decision paralysis for an agent building this)

### 19.1 Backend
- **Language/framework:** Python 3.11+ / FastAPI (async, good fit for the I/O-bound OCR/LLM-call-heavy workload; strong typing via Pydantic maps directly onto the §7 JSON schemas).
- **Task queue:** Celery + Redis (broker) for the async ingestion pipeline (§9.1 steps 2–7).
- **Validation:** Pydantic models mirroring every §7 schema exactly — these models ARE the schema validation layer referenced throughout §9, §11, §18.

### 19.2 Datastores
- **Primary:** PostgreSQL (schema in §17), with the `pgvector` extension for clause embeddings — avoids standing up a separate vector database for MVP.
- **Object storage:** any S3-compatible store (AWS S3, or a local MinIO instance for development) for uploaded documents and generated PDF exports.
- **Graph:** Postgres adjacency tables (§9.4) for MVP; migrate to Neo4j only if/when traversal query complexity genuinely demands it (§8).

### 19.3 Frontend
- **Web:** React + TypeScript, Tailwind CSS. Primary screens (§19.5) are: Upload/Intake, Decision Record (the landing screen post-processing — NOT a document report), Decision Detail (options + reasoning + resolve action), Clause Explorer (secondary/supporting view), Compare view, Prep Pack export view, Deadline Tracker/calendar view.
- **PWA:** service worker for offline-capable shell (upload queueing when offline, cached Decision Record viewing) — supports the access-first non-functional requirement (§6).

### 19.4 AI/LLM layer
- **LLM provider:** any provider supporting structured/tool-calling output (the orchestrator in §9.3 is designed to be provider-agnostic — do not hardcode a specific vendor's SDK into service logic; wrap it behind the orchestrator interface).
- **Embeddings:** any standard embedding model for clause similarity (Comparison Service, §9.2) and Q&A retrieval — dimension choice determines the `VECTOR(n)` size in §17's `clauses` table.
- **OCR:** Tesseract for MVP (open-source, no external dependency); swap to a cloud Document AI provider later only if scanned-document accuracy is measured to be insufficient.
- **STT/TTS (for voice/WhatsApp channel, §19.7):** any provider with Indic language support if targeting the Indian market specifically per the access-first design goal.

### 19.5 Screen-to-module mapping (for frontend build order)

| Screen | Primary data source | Notes |
|---|---|---|
| Upload/Intake | `POST /documents` | Role + jurisdiction input collected here |
| Processing/Loading | `GET /documents/{id}` polling `processing_status` | Show pipeline stage, not a spinner |
| **Decision Record (landing)** | `GET /documents/{id}/decisions` | THE primary screen — ranked list, deadline-first |
| Decision Detail | `GET /decisions/{id}` | Options, inaction consequence prominent, triage reasoning shown |
| Resolution Workspace | `POST /decisions/{id}/resolve`, `GET /artifacts/{id}` | Editable draft, disclaimer visible |
| Prep Pack view | `POST /decisions/{id}/prep-pack` | PDF export, share link |
| Clause Explorer (secondary) | `GET /documents/{id}/clauses` | Reachable FROM a decision, not the entry point |
| Compare | `POST /documents/compare` | Leads with decision-impact summary, full diff below |
| Ask Your Document | `POST /documents/{id}/ask` | Chat UI, citations inline |
| Deadline Tracker | `GET /users/{id}/tracker` | Calendar view + `.ics` export button per entry |

### 19.6 Security
- OAuth/SSO or standard session auth; role-based access control if multi-tenant (legal aid org accounts, §Business considerations below); encryption at rest and in transit; signed URLs with short expiry for document/export access; standard OWASP Top-10 hardening on the API gateway.

### 19.7 WhatsApp/Voice channel (Phase 3, but architected for from the start — §9.1's request flow is channel-agnostic by design)

The `/webhooks/whatsapp` endpoint (§16) receives an inbound message (image = new document upload, text = Q&A or decision-flow interaction), routes through the same Ingestion/Decision Extraction pipeline as the web path, and renders the Decision Record as a short text/voice-note summary: *"You have 1 urgent decision: [title]. Deadline [date]. If you don't act: [inaction consequence, one sentence]. Reply 1 to see your options, or 2 to talk to a legal aid volunteer."* This compact rendering is only possible because the core output unit is a small number of ranked decisions, not a document-length report — a direct payoff of the decision-first architecture, and a concrete reason to build the Decision Record schema (§7.3) exactly as specified rather than simplifying it away under early-implementation pressure.

---

## 20. Repository Layout

```
wayfinder/
├── backend/
│   ├── app/
│   │   ├── main.py                        # FastAPI app entrypoint
│   │   ├── api/
│   │   │   ├── documents.py                # /documents routes
│   │   │   ├── decisions.py                # /decisions routes
│   │   │   ├── artifacts.py
│   │   │   ├── compare.py
│   │   │   ├── qa.py
│   │   │   ├── tracker.py
│   │   │   └── webhooks_whatsapp.py
│   │   ├── models/                         # Pydantic models mirroring §7 schemas exactly
│   │   │   ├── document.py
│   │   │   ├── clause.py
│   │   │   ├── decision.py
│   │   │   ├── artifact.py
│   │   │   ├── prep_pack.py
│   │   │   └── tracker.py
│   │   ├── services/
│   │   │   ├── ingestion.py                # §9.2 Ingestion Service
│   │   │   ├── clause_extraction.py        # §9.2 Clause Segmentation & Classification
│   │   │   ├── document_graph.py           # §8, §9.4
│   │   │   ├── decision_extraction.py      # §11 — the core differentiator
│   │   │   ├── cost_of_inaction.py         # §12
│   │   │   ├── triage.py                   # §13
│   │   │   ├── resolution_artifacts.py     # §14.3, §9.2
│   │   │   ├── comparison.py               # §14.2
│   │   │   ├── qa.py                       # §14.4
│   │   │   └── deadline_tracker.py
│   │   ├── llm/
│   │   │   ├── orchestrator.py             # §9.3 — provider-agnostic wrapper
│   │   │   ├── guardrails.py               # §18 — banned phrase check, citation check, tier gate
│   │   │   └── schema_validation.py
│   │   ├── prompts/                        # §15 — versioned prompt template files
│   │   │   ├── clause_extraction_v1.txt
│   │   │   ├── decision_extraction_v1.txt
│   │   │   ├── decision_extraction_repair_v1.txt
│   │   │   ├── inaction_phrasing_v1.txt
│   │   │   ├── artifact_generation_v1.txt
│   │   │   └── qa_grounded_v1.txt
│   │   ├── templates/                      # §14.3 resolution artifact templates
│   │   │   ├── objection_letter_v1.txt
│   │   │   ├── clarification_email_v1.txt
│   │   │   ├── formal_notice_v1.txt
│   │   │   ├── deposit_itemization_request_v1.txt
│   │   │   ├── arbitration_optout_v1.txt
│   │   │   └── data_deletion_request_v1.txt
│   │   ├── db/
│   │   │   ├── schema.sql                  # §17
│   │   │   └── migrations/
│   │   └── workers/
│   │       └── ingestion_pipeline.py       # Celery task chain, §9.1
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_decision_extraction.py # incl. inaction-option invariant tests, §21.1
│   │   │   ├── test_cost_of_inaction.py
│   │   │   ├── test_triage_scoring.py
│   │   │   └── test_guardrails.py
│   │   ├── integration/
│   │   │   └── test_ingestion_to_decisions_e2e.py
│   │   └── golden_set/                     # §21.2 — annotated test documents
│   │       ├── scenario_a_eviction_notice.pdf
│   │       ├── scenario_a_expected_decisions.json
│   │       ├── scenario_b_freelance_contract_v1.pdf
│   │       ├── scenario_b_freelance_contract_v2.pdf
│   │       ├── scenario_c_tos_arbitration.pdf
│   │       └── ...
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── screens/                        # §19.5 mapping
│   │   │   ├── Upload.tsx
│   │   │   ├── DecisionRecord.tsx           # THE primary screen
│   │   │   ├── DecisionDetail.tsx
│   │   │   ├── ResolutionWorkspace.tsx
│   │   │   ├── PrepPackView.tsx
│   │   │   ├── ClauseExplorer.tsx
│   │   │   ├── Compare.tsx
│   │   │   ├── AskDocument.tsx
│   │   │   └── DeadlineTracker.tsx
│   │   ├── api/                            # typed client matching §16 endpoints
│   │   └── components/
│   └── package.json
├── docs/
│   └── wayfinder_full.md                   # this document
└── README.md
```

---

## 21. Testing Strategy

### 21.1 Unit tests that directly enforce the design's core guarantees

- **`test_decision_extraction.py`:** assert that for any Decision Point with a non-null `deadline`, at least one option has `is_default_if_inaction: true` with a non-empty `consequence` and non-empty `source_spans` — this is the §7.3 schema invariant, and it should be tested as a hard assertion against every extraction run in CI, not just documented as intent.
- **`test_cost_of_inaction.py`:** assert that when graph traversal (§12) finds no `triggers` edge from a deadline node, the reasoner returns the exact fallback string ("This document does not specify...") and never calls the LLM to invent a consequence.
- **`test_triage_scoring.py`:** table-driven tests against the §13.3 tier computation table — every stakes/reversibility/ambiguity combination should map to the documented tier, and jurisdiction-unknown downgrade should be tested explicitly (confirm it never upgrades).
- **`test_guardrails.py`:** banned-phrase list triggers regeneration; a `lawyer_now` decision's `/resolve` call returns `403` and never reaches the artifact-generation LLM call (assert the LLM orchestrator mock was never invoked, not just that the response looks right) — this tests the tier-gating is enforced in code, not just in the happy-path response shape.

### 21.2 Golden test set

A small (~15–30 document) annotated set covering the three running scenarios (§5) plus common variants (lease, employment offer, freelance contract, ToS/privacy policy, debt collection letter), each with hand-annotated expected Decision Points, triage tiers, and inaction consequences. Used for: extraction precision/recall, triage-tier agreement rate against expert labeling, and regression testing on every prompt-version change (a prompt update that changes `decision_extraction_v1` to `v2` should be run against the full golden set before deployment, with any tier or consequence changes reviewed, not just diffed for "did it still return valid JSON").

### 21.3 Integration/E2E

`test_ingestion_to_decisions_e2e.py`: full pipeline from raw PDF upload through `processing_status: decisions_ready`, asserting the final Decision Record matches expected shape and count for each golden-set document. Frontend E2E (Playwright) for the critical path: upload → view Decision Record → resolve a self-serve decision → download artifact; and separately, upload a `lawyer_now`-triggering document → confirm resolve is blocked and Prep Pack is offered instead.

---

## 22. Implementation Roadmap (phased, each phase independently demoable)

### Phase 0 — Foundations (before any user-facing feature)
- Repo scaffold (§20), Postgres schema (§17) migrated, S3/MinIO bucket configured, LLM orchestrator skeleton (§9.3) with a stub provider for early testing.
- Golden test set (§21.2) assembled — at minimum Scenario A (eviction notice) fully annotated, since it's the flagship demo case.

### Phase 1 — Ingestion + Clause Layer (no decisions yet)
- Ingestion Service (§9.2): upload, OCR, language/jurisdiction detection, document classification.
- Clause Segmentation & Classification Service + `clause_extraction_v1` prompt.
- Clause Explorer frontend screen (functions as the MVP's first visible output, even before Decision Extraction exists — useful for validating extraction quality against the golden set before building on top of it).
- **Demo at end of phase:** upload a document, see extracted clauses with plain-language rewrites and risk flags.

### Phase 2 — Document Graph + Decision Extraction (the core differentiator)
- Document Graph Service (§8, §9.4 Postgres adjacency version).
- Decision Extraction Service (§11) + `decision_extraction_v1` / repair prompt.
- Cost-of-Inaction Reasoner (§12) + `inaction_phrasing_v1` prompt.
- Schema-invariant enforcement (§7.3, §11.3, §17 constraint) wired in and unit-tested (§21.1).
- Decision Record frontend screen (the primary landing screen).
- **Demo at end of phase:** upload Scenario A, see the ranked Decision Record with the inaction consequence correctly surfaced and cited.

### Phase 3 — Triage + Resolution
- Triage Service (§13) — deterministic scoring, no LLM.
- Resolution Artifact Service (§14.3, §9.2) with at minimum `objection_letter_v1` and `clarification_email_v1` templates working end-to-end.
- Tier-gating enforcement (§18.6) — including the negative-path test (blocked generation for `lawyer_now`).
- Prep Pack generation (§7.6) for escalated tiers.
- Resolution Workspace + Prep Pack View frontend screens.
- **Demo at end of phase:** resolve a self-serve decision into a downloadable draft letter; trigger a high-stakes document and confirm it correctly routes to Prep Pack instead.

### Phase 4 — Deadline Tracking + Q&A
- Deadline Tracker Service, `.ics` export, reminder scheduling.
- Q&A Service (§14.4, §15.5) with citation enforcement.
- Deadline Tracker + Ask Your Document frontend screens.
- **Demo at end of phase:** full single-document journey from upload to tracked, exportable deadline with a working Q&A chat grounded in the document.

### Phase 5 — Comparison
- Comparison Service (§14.2, §7.7) — clause alignment + decision-impact filtering.
- Compare frontend screen.
- **Demo at end of phase:** Scenario B (contract redraft) — upload both versions, see the decision-impact-filtered diff.

### Phase 6 — Access Channel (WhatsApp/Voice)
- `/webhooks/whatsapp` endpoint (§19.7), routed through the existing pipeline (no new extraction logic needed — this phase is channel/rendering work, not core-engine work, which is why it's safely deferred to last).
- Compact text/voice rendering of the Decision Record.
- **Demo at end of phase:** photograph a notice via WhatsApp, receive a Decision Record summary as a reply.

### Phase 7 — Hardening for ongoing operation (not a hackathon-scope phase, included since this is being built as an ongoing product per the stated goal)
- Full audit logging review (§18.9), golden-set expansion beyond the initial ~15–30 documents, jurisdiction corpus expansion (§10 — an explicit, ongoing content/data-partnership effort, not a one-time engineering task), legal aid directory integration for the `legal_aid_recommended`/`lawyer_now` referral step, multilingual output beyond the initial language, migration to Neo4j if Postgres-adjacency traversal (§9.4) is measured to be a bottleneck.

---

## 23. Explicit Non-Goals (things this spec deliberately does not attempt, and why)

- **Not attempting to solve jurisdiction-correct statutory defaults at launch.** §10 makes this an honest, propagating uncertainty rather than a solved problem — building a comprehensive, current, multi-jurisdiction statutory corpus is a genuine ongoing content/legal-partnership effort (§22 Phase 7), not something to fake with a v1 template set presented as authoritative.
- **Not filing anything on the user's behalf.** Resolution artifacts are drafts for the user to review and send themselves — Wayfinder does not submit court filings, send emails automatically, or take any binding action without explicit user action outside the system.
- **Not representing users in any proceeding or claiming to be a substitute for legal representation at any tier**, including `self_serve` — the disclaimer (§18.1) and the tier-gating (§18.6) exist precisely so this line is never blurred, matching the problem statement's explicit requirement that solutions "provide information and assistance, rather than replace professional legal advice."
- **Not building a fairness/asymmetry "score" as a standalone flagship feature** — included as supporting evidence for triage (§14.1) but deliberately not presented as an authoritative number, for the reasons given in §4 and §10.

---

## 24. Summary for a Building Agent

If you are an LLM asked to build this from scratch, the fastest path to something demoable that captures the actual differentiator is: **Phase 0 → Phase 1 → Phase 2**, stopping to demo after Phase 2 even before Triage/Resolution exist. The Decision Record with a correctly-populated, correctly-cited inaction consequence (§7.3, §11.3, §12) *is* the core idea — everything in Phase 3 onward is real, necessary product completeness, but Phase 2's output is the artifact that proves the concept and is what should be validated against the golden set (§21.2) before investing further. Do not simplify away the schema invariant in §7.3 for expedience — it is the single mechanism that makes this design's core claim ("cost of inaction is guaranteed, not just usually included") true rather than aspirational, and losing it collapses Wayfinder back into being a description-only tool like the alternatives it's meant to improve on.
