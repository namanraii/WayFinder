"""Decision Extraction Service (spec §11).

This service turns extracted clauses and their deterministic document graph
into a small, ranked set of real user decisions.  The LLM receives grouped
clause context only for plain-language option phrasing; candidate detection,
grouping, deadlines, and the mandatory inaction fallback are application
logic.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Optional

from app.db import sqlite
from app.llm import guardrails
from app.llm.orchestrator import LLMOrchestrator
from app.llm.schema_validation import validate_decision
from app.models import Clause, DecisionPoint, Document
from app.services import heuristics as hz
from app.services.cost_of_inaction import build as build_inaction_option
from app.services.repository import load_clauses, load_decisions, load_document


@dataclass(frozen=True)
class DeadlineRef:
    """A deadline value pinned to its graph node, when one is available."""

    deadline: str
    node_id: Optional[str]
    clause_id: str


@dataclass(frozen=True)
class DecisionCandidate:
    clauses: tuple[Clause, ...]
    deadline: Optional[str]
    deadline_node_id: Optional[str]
    source_spans: tuple[str, ...]


def run(
    conn,
    document_id: str,
    orchestrator: Optional[LLMOrchestrator] = None,
) -> list[DecisionPoint]:
    """Extract, validate, persist, and rank decisions for one document.

    The operation is intentionally idempotent for the normal upload pipeline:
    a second call returns the already persisted Decision Record instead of
    silently creating duplicate decisions.  Reprocessing a document should be
    done through an explicit future replacement workflow, not by accidental
    duplicate invocation.
    """
    document = load_document(conn, document_id)
    if document is None:
        raise ValueError(f"Document not found: {document_id}")

    existing = load_decisions(conn, document_id)
    if existing:
        return rank_decisions(existing, load_clauses(conn, document_id))

    clauses = load_clauses(conn, document_id)
    deadline_index = _deadline_index(conn, document_id, clauses)
    candidates = _build_candidates(document, clauses, deadline_index)
    candidates = _merge_related_candidates(conn, document_id, candidates)

    extracted: list[DecisionPoint] = []
    for candidate in candidates:
        decision_id = _decision_id()
        draft = _generate_draft(
            document,
            candidate,
            decision_id,
            conn,
            orchestrator,
        )
        if draft is None:
            # §11.2: an output that remains invalid after its one repair pass
            # is not persisted as a user-facing decision.
            continue

        decision = _validate_or_repair(
            draft,
            document,
            candidate,
            decision_id,
            conn,
            orchestrator,
        )
        if decision is None:
            continue

        note = guardrails.check_jurisdiction_gate(document, decision)
        decision = decision.model_copy(
            update={
                "confidence": _confidence_for(candidate, document),
                "jurisdiction_confidence_note": note or decision.jurisdiction_confidence_note,
            }
        )
        _persist(conn, document_id, decision)
        extracted.append(decision)

    sqlite.update(conn, "documents", "document_id", document_id, {
        "processing_status": "decisions_ready",
    })
    return rank_decisions(extracted, clauses)


def ensure_inaction_option(
    draft: dict[str, Any],
    candidate: DecisionCandidate,
    conn,
    document_id: str,
    orchestrator: Optional[LLMOrchestrator] = None,
) -> dict[str, Any]:
    """Enforce §11.3's non-optional deadline branch.

    A model-supplied inaction option is allowed through and is subsequently
    checked by ``DecisionPoint`` validation.  When it is omitted, the
    deterministic graph reasoner supplies it; this is deliberately not a
    second request that hopes the model follows the prompt this time.
    """
    if candidate.deadline is None:
        return draft

    options = draft.get("options")
    if not isinstance(options, list):
        options = []
        draft["options"] = options
    if any(isinstance(option, dict) and option.get("is_default_if_inaction") for option in options):
        return draft

    inaction = build_inaction_option(
        conn,
        document_id,
        candidate.deadline_node_id,
        orchestrator,
        source_spans=candidate.source_spans,
    )
    options.append(inaction.model_dump())
    return draft


def rank_decisions(
    decisions: Iterable[DecisionPoint],
    clauses: Iterable[Clause] = (),
) -> list[DecisionPoint]:
    """Order by deadline proximity, then deterministic clause-risk stakes."""
    clause_by_id = {clause.clause_id: clause for clause in clauses}

    def key(decision: DecisionPoint) -> tuple[int, int, str]:
        # Overdue deadlines correctly appear before future deadlines.  Decisions
        # without a deadline follow all dated decisions.
        deadline_bucket = decision.days_remaining if decision.days_remaining is not None else 10**9
        stakes = _max_risk_severity(
            [clause_by_id[cid] for cid in decision.triggering_clause_ids if cid in clause_by_id]
        )
        return (deadline_bucket, -_severity_rank(stakes), decision.decision_id)

    return sorted(decisions, key=key)


def _build_candidates(
    document: Document,
    clauses: list[Clause],
    deadline_index: dict[str, list[DeadlineRef]],
) -> list[DecisionCandidate]:
    candidates: list[DecisionCandidate] = []
    for clause in clauses:
        clause_deadlines = deadline_index.get(clause.clause_id, [])
        qualifying_deadlines = [
            deadline
            for deadline in clause_deadlines
            if _deadline_belongs_to_user(clause, deadline, document.role_context)
        ]
        is_decision_bearing = clause.clause_type in hz.DECISION_BEARING_TYPES
        if not is_decision_bearing and not qualifying_deadlines:
            continue

        # A decision-bearing clause may carry a deadline even when its actor
        # extraction is uncertain; retain the closest document-stated deadline.
        relevant_deadlines = clause_deadlines if is_decision_bearing else qualifying_deadlines
        selected = _earliest_deadline(relevant_deadlines)
        candidates.append(DecisionCandidate(
            clauses=(clause,),
            deadline=selected.deadline if selected else None,
            deadline_node_id=selected.node_id if selected else None,
            source_spans=tuple(_span_for_clause(clause)),
        ))
    return candidates


def _deadline_index(
    conn,
    document_id: str,
    clauses: Iterable[Clause],
) -> dict[str, list[DeadlineRef]]:
    """Read graph-backed deadline nodes, with obligation-backed fallback."""
    output: dict[str, list[DeadlineRef]] = {}
    for row in sqlite.query(
        conn,
        "SELECT * FROM graph_nodes WHERE document_id = ? AND node_type = 'deadline'",
        (document_id,),
    ):
        props = _decode_properties(row.get("properties"))
        deadline = _normalise_deadline(props.get("deadline_absolute"), props.get("deadline_relative"))
        clause_id = str(row.get("ref_id") or "")
        if deadline and clause_id:
            output.setdefault(clause_id, []).append(DeadlineRef(
                deadline=deadline,
                node_id=row["node_id"],
                clause_id=clause_id,
            ))

    # Tests and import paths can construct clauses before graph-building; use
    # their extracted obligation data without losing a legitimate deadline.
    for clause in clauses:
        known_deadlines = {item.deadline for item in output.get(clause.clause_id, [])}
        for obligation in clause.obligations:
            deadline = _normalise_deadline(
                obligation.deadline_absolute,
                obligation.deadline_relative,
            )
            if deadline and deadline not in known_deadlines:
                output.setdefault(clause.clause_id, []).append(DeadlineRef(
                    deadline=deadline,
                    node_id=None,
                    clause_id=clause.clause_id,
                ))
                known_deadlines.add(deadline)
    return output



def _deadline_belongs_to_user(
    clause: Clause,
    deadline: DeadlineRef,
    role_context: Optional[str],
) -> bool:
    # An omitted role should not hide every clear deadline from the user.  Once
    # a role is supplied, however, the §11.1 actor check is applied strictly.
    if not role_context:
        return True
    role = role_context.strip().lower()
    for obligation in clause.obligations:
        value = _normalise_deadline(obligation.deadline_absolute, obligation.deadline_relative)
        if value != deadline.deadline:
            continue
        actor = (obligation.actor or "").lower()
        if role in actor or actor in role or actor in {"you", "user"}:
            return True
    return False


def _merge_related_candidates(
    conn,
    document_id: str,
    candidates: list[DecisionCandidate],
) -> list[DecisionCandidate]:
    """Merge one-hop ``references``/``conflicts_with`` connected clauses."""
    if len(candidates) < 2:
        return candidates

    candidate_by_clause = {candidate.clauses[0].clause_id: candidate for candidate in candidates}
    adjacency: dict[str, set[str]] = {clause_id: set() for clause_id in candidate_by_clause}
    node_to_clause = {
        row["node_id"]: row["ref_id"]
        for row in sqlite.query(
            conn,
            "SELECT node_id, ref_id FROM graph_nodes WHERE document_id = ? AND node_type = 'clause'",
            (document_id,),
        )
    }
    for edge in sqlite.query(
        conn,
        """SELECT from_node_id, to_node_id FROM graph_edges
           WHERE document_id = ? AND edge_type IN ('references', 'conflicts_with')""",
        (document_id,),
    ):
        left = node_to_clause.get(edge["from_node_id"])
        right = node_to_clause.get(edge["to_node_id"])
        if left in adjacency and right in adjacency and left != right:
            adjacency[left].add(right)
            adjacency[right].add(left)

    # ``related_clause_ids`` is extracted evidence that can be present before
    # graph references are available; treat it as the same one-hop relation.
    for clause_id, candidate in candidate_by_clause.items():
        for related in candidate.clauses[0].related_clause_ids:
            if related in adjacency:
                adjacency[clause_id].add(related)
                adjacency[related].add(clause_id)

    groups: list[list[str]] = []
    seen: set[str] = set()
    for root in candidate_by_clause:
        if root in seen:
            continue
        stack, group = [root], []
        seen.add(root)
        while stack:
            current = stack.pop()
            group.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        groups.append(group)

    merged: list[DecisionCandidate] = []
    for group in groups:
        items = [candidate_by_clause[clause_id] for clause_id in group]
        clauses = tuple(item.clauses[0] for item in items)
        all_deadlines = [
            DeadlineRef(item.deadline, item.deadline_node_id, item.clauses[0].clause_id)
            for item in items if item.deadline
        ]
        selected = _earliest_deadline(all_deadlines)
        spans = tuple(span for item in items for span in item.source_spans)
        merged.append(DecisionCandidate(
            clauses=clauses,
            deadline=selected.deadline if selected else None,
            deadline_node_id=selected.node_id if selected else None,
            source_spans=spans,
        ))
    return merged


def _generate_draft(
    document: Document,
    candidate: DecisionCandidate,
    decision_id: str,
    conn,
    orchestrator: Optional[LLMOrchestrator],
) -> Optional[dict[str, Any]]:
    orchestrator = orchestrator or LLMOrchestrator()
    result = orchestrator.generate(
        prompt_name="decision_extraction_v1",
        prompt_version="decision_extraction_v1",
        inputs={
            "decision_id": decision_id,
            "document_id": document.document_id,
            "triggering_clauses": [clause.model_dump() for clause in candidate.clauses],
            "graph_context": _graph_context(conn, document.document_id, candidate),
            "deadline": candidate.deadline,
            "days_remaining": _days_remaining(candidate.deadline),
            "document_type": document.document_type,
            "role_context": document.role_context,
            "jurisdiction_status": document.jurisdiction.status,
        },
        validator=_has_decision_shape,
        entity_type="decision",
        entity_id=decision_id,
    )
    if not getattr(result, "ok", False):
        return None
    return _prepare_draft(
        getattr(result, "output", None),
        document,
        candidate,
        decision_id,
        conn,
        orchestrator,
    )


def _validate_or_repair(
    draft: dict[str, Any],
    document: Document,
    candidate: DecisionCandidate,
    decision_id: str,
    conn,
    orchestrator: Optional[LLMOrchestrator],
) -> Optional[DecisionPoint]:
    validated = validate_decision(draft)
    if validated.ok:
        return validated.value  # type: ignore[return-value]

    orchestrator = orchestrator or LLMOrchestrator()
    repaired = orchestrator.generate(
        prompt_name="decision_extraction_repair_v1",
        prompt_version="decision_extraction_repair_v1",
        inputs={
            "draft": draft,
            "validation_errors": validated.errors,
            "triggering_clauses": [clause.model_dump() for clause in candidate.clauses],
            "deadline": candidate.deadline,
        },
        validator=_has_decision_shape,
        entity_type="decision",
        entity_id=decision_id,
    )
    if not getattr(repaired, "ok", False):
        return None
    repaired_draft = _prepare_draft(
        getattr(repaired, "output", None),
        document,
        candidate,
        decision_id,
        conn,
        orchestrator,
    )
    final = validate_decision(repaired_draft)
    return final.value if final.ok else None  # type: ignore[return-value]


def _prepare_draft(
    raw: Any,
    document: Document,
    candidate: DecisionCandidate,
    decision_id: str,
    conn,
    orchestrator: Optional[LLMOrchestrator],
) -> dict[str, Any]:
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    draft = dict(raw) if isinstance(raw, dict) else {}
    # Identity, source evidence, and deadline are derived from deterministic
    # candidate construction—not left to model output.
    draft.update({
        "decision_id": decision_id,
        "document_id": document.document_id,
        "triggering_clause_ids": [clause.clause_id for clause in candidate.clauses],
        "deadline": candidate.deadline,
        "days_remaining": _days_remaining(candidate.deadline),
        "source_spans": list(candidate.source_spans),
    })
    if not isinstance(draft.get("options"), list):
        draft["options"] = []
    return ensure_inaction_option(draft, candidate, conn, document.document_id, orchestrator)


def _has_decision_shape(raw: Any) -> tuple[bool, list[str]]:
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return False, ["Expected a JSON object for a decision"]
    errors: list[str] = []
    if not isinstance(raw.get("title"), str) or not raw["title"].strip():
        errors.append("Decision title must be a non-empty string")
    if not isinstance(raw.get("options"), list):
        errors.append("Decision options must be a list")
    return not errors, errors


def _graph_context(conn, document_id: str, candidate: DecisionCandidate) -> dict[str, list[dict[str, Any]]]:
    """Return only nearby graph structure for grounding a phrasing request."""
    all_nodes = sqlite.query(
        conn,
        "SELECT * FROM graph_nodes WHERE document_id = ?",
        (document_id,),
    )
    by_id = {node["node_id"]: node for node in all_nodes}
    selected = {
        node["node_id"]
        for node in all_nodes
        if node.get("ref_id") in {clause.clause_id for clause in candidate.clauses}
    }
    if candidate.deadline_node_id:
        selected.add(candidate.deadline_node_id)

    all_edges = sqlite.query(
        conn,
        "SELECT * FROM graph_edges WHERE document_id = ?",
        (document_id,),
    )
    relevant_edges: list[dict[str, Any]] = []
    # A short deterministic expansion includes the deadline's triggered
    # penalties but does not flood the decision prompt with unrelated clauses.
    for _ in range(2):
        added = False
        for edge in all_edges:
            if edge["from_node_id"] in selected or edge["to_node_id"] in selected:
                if edge not in relevant_edges:
                    relevant_edges.append(edge)
                before = len(selected)
                selected.update({edge["from_node_id"], edge["to_node_id"]})
                added = added or len(selected) != before
        if not added:
            break
    nodes = [_graph_node_for_prompt(by_id[node_id]) for node_id in selected if node_id in by_id]
    return {
        "nodes": nodes,
        "edges": [dict(edge) for edge in relevant_edges],
    }


def _graph_node_for_prompt(node: dict[str, Any]) -> dict[str, Any]:
    result = dict(node)
    result["properties"] = _decode_properties(result.get("properties"))
    return result


def _persist(conn, document_id: str, decision: DecisionPoint) -> None:
    sqlite.insert(conn, "decisions", {
        "decision_id": decision.decision_id,
        "document_id": document_id,
        "title": decision.title,
        "triggering_clause_ids": decision.triggering_clause_ids,
        "deadline": decision.deadline,
        "options": [option.model_dump() for option in decision.options],
        "triage_tier": decision.triage_tier,
        "triage_scores": decision.triage_scores.model_dump() if decision.triage_scores else None,
        "triage_reasoning": decision.triage_reasoning,
        "resolution_artifact_id": decision.resolution_artifact_id,
        "confidence": decision.confidence,
        "jurisdiction_confidence_note": decision.jurisdiction_confidence_note,
        "source_spans": decision.source_spans,
    })
    for clause_id in decision.triggering_clause_ids:
        sqlite.update(conn, "clauses", "clause_id", clause_id, {
            "feeds_decision_id": decision.decision_id,
        })

    decision_node_id = f"dpnode_{uuid.uuid4().hex[:10]}"
    sqlite.insert(conn, "graph_nodes", {
        "node_id": decision_node_id,
        "document_id": document_id,
        "node_type": "decision_point",
        "ref_id": decision.decision_id,
        "properties": {"title": decision.title},
    })
    for clause_id in decision.triggering_clause_ids:
        for row in sqlite.query(
            conn,
            """SELECT node_id FROM graph_nodes
               WHERE document_id = ? AND node_type = 'clause' AND ref_id = ?""",
            (document_id, clause_id),
        ):
            sqlite.insert(conn, "graph_edges", {
                "edge_id": f"edge_{uuid.uuid4().hex[:10]}",
                "document_id": document_id,
                "from_node_id": row["node_id"],
                "to_node_id": decision_node_id,
                "edge_type": "feeds",
            })


def _confidence_for(candidate: DecisionCandidate, document: Document) -> str:
    """Blend extraction quality, missing data, and jurisdiction conservatively."""
    if not candidate.clauses:
        return "low"
    score = sum(clause.extraction_confidence for clause in candidate.clauses) / len(candidate.clauses)
    if any(clause.missing_elements for clause in candidate.clauses):
        score -= 0.15
    if document.jurisdiction.status == "unknown":
        score -= 0.20
    elif document.jurisdiction.status == "inferred":
        score -= 0.08
    if score >= 0.80:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def _max_risk_severity(clauses: Iterable[Clause]) -> str:
    severity = "low"
    for clause in clauses:
        for risk in clause.risks:
            if _severity_rank(risk.severity) > _severity_rank(severity):
                severity = risk.severity
    return severity if severity in {"low", "medium", "high"} else "low"


def _severity_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(value, 0)


def _earliest_deadline(values: Iterable[DeadlineRef]) -> Optional[DeadlineRef]:
    values = list(values)
    if not values:
        return None
    return min(values, key=lambda value: (value.deadline, 0 if value.node_id else 1, value.node_id or ""))



def _span_for_clause(clause: Clause) -> list[str]:
    return [f"{clause.clause_id}:{clause.char_span[0]}-{clause.char_span[1]}"]


def _normalise_deadline(absolute: Any, relative: Any = None) -> Optional[str]:
    if absolute:
        text = str(absolute).strip()
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            pass
    if relative:
        match = re.search(r"\b(\d+)\s*(?:calendar\s+|business\s+)?days?\b", str(relative), re.I)
        if match:
            return (date.today() + timedelta(days=int(match.group(1)))).isoformat()
    return None


def _days_remaining(deadline: Optional[str]) -> Optional[int]:
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline) - date.today()).days
    except ValueError:
        return None


def _decode_properties(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _decision_id() -> str:
    return f"dec_{uuid.uuid4().hex[:10]}"

