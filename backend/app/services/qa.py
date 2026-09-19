"""Retrieval-anchored Q&A service (spec §§9.2, 14.4, 15.5, 18.3)."""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from app.db import sqlite
from app.llm import guardrails
from app.llm.orchestrator import LLMOrchestrator
from app.services.repository import load_clauses, load_decisions, load_document

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
_STOP_WORDS = {
    "a", "an", "and", "are", "at", "can", "do", "does", "for", "from",
    "how", "i", "if", "in", "is", "it", "me", "my", "of", "on", "or",
    "the", "this", "to", "what", "when", "where", "which", "with", "you",
}
_DEADLINE_TERMS = {"deadline", "due", "when", "time", "respond", "response", "days", "date"}
_CONSEQUENCE_TERMS = {"happen", "happens", "consequence", "consequences", "miss", "nothing", "default", "lose"}


def _terms(text: str) -> set[str]:
    return {word.lower() for word in _WORD_RE.findall(text) if word.lower() not in _STOP_WORDS}


def _term_matches(term: str, text_terms: set[str]) -> bool:
    if term in text_terms:
        return True
    # Small stem-like fallback catches "respond" / "response" without a
    # heavyweight embedding dependency in the offline MVP.
    root = term[:5]
    return len(root) >= 4 and any(candidate.startswith(root) for candidate in text_terms)


def retrieve(conn, document_id: str, question: str, *, top_k: int = 3):
    """Return scored clause objects using only content stored for the document."""
    clauses = load_clauses(conn, document_id)
    question_terms = _terms(question)
    scores: list[tuple[float, object]] = []
    for clause in clauses:
        source = " ".join(filter(None, [clause.original_text, clause.plain_language, clause.clause_title]))
        source_terms = _terms(source)
        score = float(sum(_term_matches(term, source_terms) for term in question_terms))
        low_question = question.lower()
        if question_terms & _DEADLINE_TERMS and any(ob.deadline_absolute or ob.deadline_relative for ob in clause.obligations):
            score += 3.0
        if question_terms & _CONSEQUENCE_TERMS and clause.risks:
            score += 2.0
        if "deadline" in low_question and "deadline" in (clause.plain_language or "").lower():
            score += 1.0
        scores.append((score, clause))
    scores.sort(key=lambda pair: (-pair[0], pair[1].clause_id))
    # A zero-score result is deliberately treated as no retrieval.  The model
    # receives no excerpts and must say it cannot answer, rather than guessing.
    return [(score, clause) for score, clause in scores[:top_k] if score > 0]


def _validate_answer_output(raw: Any, valid_clause_ids: set[str], require_citation: bool) -> tuple[bool, list[str]]:
    if not isinstance(raw, dict):
        return False, ["Q&A output must be a JSON object"]
    errors: list[str] = []
    if not isinstance(raw.get("answer"), str) or not raw["answer"].strip():
        errors.append("answer must be a non-empty string")
    citations = raw.get("citations")
    if not isinstance(citations, list):
        errors.append("citations must be a list")
    else:
        if require_citation and not citations:
            errors.append("a grounded answer must cite at least one clause")
        for citation in citations:
            if not isinstance(citation, dict) or not citation.get("clause_id"):
                errors.append("each citation must include clause_id")
                continue
            if citation["clause_id"] not in valid_clause_ids:
                errors.append("citation references a clause outside the retrieved document")
    if raw.get("confidence") not in {"high", "medium", "low"}:
        errors.append("confidence must be high, medium, or low")
    return not errors, errors


def _deterministic_confidence(scored, document) -> str:
    if not scored:
        return "low"
    score, top_clause = scored[0]
    confidence = "high" if score >= 4 and top_clause.extraction_confidence >= 0.8 else "medium"
    # §10/§18.5: uncertainty only downgrades; it never boosts confidence.
    if document and document.jurisdiction.status == "unknown":
        return "medium" if confidence == "high" else "low"
    return confidence


def _append_disclaimer(answer: str) -> str:
    answer = answer.strip()
    return answer if guardrails.DISCLAIMER in answer else f"{answer}\n\n{guardrails.DISCLAIMER}"


def answer_question(
    conn,
    document_id: str,
    question: str,
    *,
    orchestrator: Optional[LLMOrchestrator] = None,
    top_k: int = 3,
) -> dict[str, Any]:
    """Answer from retrieved clauses only and persist an auditable Q&A row."""
    if not question or not question.strip():
        raise ValueError("question must not be empty")
    document = load_document(conn, document_id)
    if document is None:
        raise KeyError(f"Document {document_id!r} was not found")

    scored = retrieve(conn, document_id, question, top_k=top_k)
    clauses = [clause for _, clause in scored]
    decisions = load_decisions(conn, document_id)
    decision_ids = {decision.decision_id for decision in decisions}
    qa_id = f"qa_{uuid.uuid4().hex[:12]}"
    orchestrator = orchestrator or LLMOrchestrator()
    result = orchestrator.generate(
        prompt_name="qa_grounded_v1",
        prompt_version="qa_grounded_v1",
        inputs={
            "question": question.strip(),
            "retrieved_clauses": [clause.model_dump() for clause in clauses],
            # Provider receives IDs only; titles remain an API/UI lookup and
            # cannot be accidentally substituted for a citation.
            "linked_decisions": {decision_id: decision_id for decision_id in decision_ids},
        },
        validator=lambda raw: _validate_answer_output(
            raw, {clause.clause_id for clause in clauses}, bool(clauses)
        ),
        entity_type="qa_answer",
        entity_id=qa_id,
    )
    if not result.ok:
        raise RuntimeError("Q&A generation was blocked by validation or guardrails: " + "; ".join(result.errors))

    raw = result.output
    cited_clause_ids = [citation["clause_id"] for citation in raw.get("citations", [])]
    linked_decision_id = raw.get("linked_decision_id")
    if linked_decision_id not in decision_ids:
        linked_decision_id = None
    response = {
        "qa_id": qa_id,
        "document_id": document_id,
        "question": question.strip(),
        "answer": _append_disclaimer(raw["answer"]),
        "citations": raw.get("citations", []),
        "confidence": _deterministic_confidence(scored, document),
        "linked_decision_id": linked_decision_id,
        "disclaimer": guardrails.DISCLAIMER,
        "model_version": result.model_version,
        "prompt_version": result.prompt_version,
    }
    sqlite.insert(conn, "qa_log", {
        "qa_id": qa_id,
        "document_id": document_id,
        "question": question.strip(),
        "answer": response["answer"],
        "cited_clause_ids": cited_clause_ids,
        "confidence": response["confidence"],
        "linked_decision_id": linked_decision_id,
        "model_version": result.model_version,
        "prompt_version": result.prompt_version,
    })
    return response


# Short alias for route handlers and interactive callers.
ask = answer_question
