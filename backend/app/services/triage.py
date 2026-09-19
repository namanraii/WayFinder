"""Deterministic decision triage (spec §13).

No model judges stakes, reversibility, or ambiguity here.  The explanation is
rendered from the same inputs used for the tier, preventing display logic from
drifting from the actual routing decision.
"""
from __future__ import annotations

from app.db import sqlite
from app.models import DecisionPoint, TriageScores
from app.services import heuristics as hz
from app.services.repository import load_clauses, load_decision, load_document

_SEVERITY = {"low": 1, "medium": 2, "high": 3}


def compute_tier(stakes: str, reversibility: str, ambiguity: str) -> str:
    if stakes == "high":
        return "lawyer_now"
    if stakes == "medium" and (reversibility == "low" or ambiguity == "high"):
        return "legal_aid_recommended"
    if stakes == "medium":
        return "self_serve_with_escalation_path"
    if reversibility == "low":
        return "legal_aid_recommended"
    if ambiguity == "high":
        return "self_serve_with_escalation_path"
    return "self_serve"


def apply_jurisdiction_gate(tier: str, jurisdiction_status: str) -> str:
    """Unknown jurisdiction can only make an outcome more conservative."""
    if jurisdiction_status != "unknown":
        return tier
    return {
        "self_serve": "self_serve_with_escalation_path",
        "self_serve_with_escalation_path": "legal_aid_recommended",
    }.get(tier, tier)


def score(decision: DecisionPoint, clauses, document) -> DecisionPoint:
    related = [clause for clause in clauses if clause.clause_id in decision.triggering_clause_ids]
    max_risk = max((_SEVERITY.get(risk.severity, 0) for clause in related for risk in clause.risks), default=0)
    stakes = "high" if (max_risk >= 3 or document.document_type in hz.HIGH_STAKES_CATEGORIES) else "medium" if max_risk >= 2 else "low"
    source_text = " ".join(clause.original_text.lower() for clause in related)
    types = {clause.clause_type for clause in related}
    reversibility = "low" if any(word in source_text for word in hz.IRREVERSIBLE_KEYWORDS) or types & {"termination"} else "high"
    ambiguity = "high" if any(clause.missing_elements for clause in related) or _has_conflict(related) else "low"
    tier = apply_jurisdiction_gate(compute_tier(stakes, reversibility, ambiguity), document.jurisdiction.status)
    scores = TriageScores(stakes=stakes, reversibility=reversibility, ambiguity=ambiguity)
    reasoning = _reasoning(scores, document.jurisdiction.status, tier)
    return decision.model_copy(update={"triage_tier": tier, "triage_scores": scores, "triage_reasoning": reasoning})


def _has_conflict(clauses) -> bool:
    # The graph service may later add explicit conflict edges. Before that,
    # incompatible duplicate absolute deadlines are a transparent conflict.
    deadlines = {ob.deadline_absolute for clause in clauses for ob in clause.obligations if ob.deadline_absolute}
    return len(deadlines) > 1


def _reasoning(scores: TriageScores, jurisdiction_status: str, tier: str) -> str:
    parts = [f"Stakes are {scores.stakes} based on the document category and clause risk flags."]
    parts.append("The action is hard to reverse." if scores.reversibility == "low" else "The action appears more reversible based on the document text.")
    parts.append("Some key terms are missing or conflict, so ambiguity is high." if scores.ambiguity == "high" else "No extracted conflict or missing-element flag raised ambiguity.")
    if jurisdiction_status == "unknown":
        parts.append("Because jurisdiction is unconfirmed, the routing is kept more cautious.")
    parts.append(f"This routes to {tier.replace('_', ' ')}.")
    return " ".join(parts)


def run(conn, document_id: str) -> list[DecisionPoint]:
    document = load_document(conn, document_id)
    if document is None:
        raise KeyError(f"Document {document_id!r} was not found")
    clauses = load_clauses(conn, document_id)
    rows = sqlite.query(conn, "SELECT decision_id FROM decisions WHERE document_id = ?", (document_id,))
    updated: list[DecisionPoint] = []
    for row in rows:
        decision = load_decision(conn, row["decision_id"])
        if decision is None:
            continue
        scored = score(decision, clauses, document)
        sqlite.update(conn, "decisions", "decision_id", scored.decision_id, {
            "triage_tier": scored.triage_tier,
            "triage_scores": scored.triage_scores.model_dump() if scored.triage_scores else None,
            "triage_reasoning": scored.triage_reasoning,
        })
        updated.append(scored)
    return updated
