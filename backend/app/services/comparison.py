"""Deterministic document comparison service (spec §§7.7, 14.2).

Production can replace ``_similarity`` with embeddings and use an LLM only for
near-threshold confirmations.  The MVP uses clause type first and a transparent
lexical score, which keeps comparison available offline and avoids presenting
an ungrounded semantic judgment as fact.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from difflib import SequenceMatcher

from app.models import ClauseDiff, ComparisonResult
from app.services import heuristics as hz
from app.services.repository import load_clauses

_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?:₹|\$|usd\s?|inr\s?)?[\d,]+(?:\.\d+)?(?:\s*(?:calendar|business)?\s*days?)?", re.IGNORECASE)
_SEVERITY = {"low": 1, "medium": 2, "high": 3}


def _display(clause) -> str:
    return (clause.plain_language or clause.original_text or "").strip()


def _normalise(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _tokens(text: str) -> set[str]:
    # Small legal/English stop list prevents boilerplate from dominating pairs.
    stop = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "by", "this", "that", "will", "shall", "be", "is"}
    return {word for word in _WORD_RE.findall(text.lower()) if word not in stop}


def _similarity(a, b) -> float:
    left, right = _display(a), _display(b)
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    jaccard = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence = SequenceMatcher(None, _normalise(left), _normalise(right)).ratio()
    return max(jaccard, sequence)


def _values(text: str) -> set[str]:
    return {" ".join(match.lower().split()) for match in _NUMBER_RE.findall(text)}


def _risk_score(clause) -> tuple[int, int | None, int]:
    severity = max((_SEVERITY.get(risk.severity, 0) for risk in clause.risks), default=0)
    deadline = hz.extract_deadline(clause.original_text)
    days = deadline[1] if deadline else None
    consequence_count = len(hz.consequence_sentences(clause.original_text))
    return severity, days, consequence_count


def _risk_delta(before, after, status: str) -> str:
    if status == "added":
        return "increased"
    if status == "removed":
        return "decreased"
    if status in {"same", "similar"}:
        return "unchanged"
    before_severity, before_days, before_consequences = _risk_score(before)
    after_severity, after_days, after_consequences = _risk_score(after)
    if after_severity > before_severity:
        return "increased"
    if after_severity < before_severity:
        return "decreased"
    if before_days and after_days and after_days < before_days:
        return "increased"
    if before_days and after_days and after_days > before_days:
        return "decreased"
    if after_consequences > before_consequences:
        return "increased"
    if after_consequences < before_consequences:
        return "decreased"
    return "unchanged"


def _pair_by_type(clauses_a, clauses_b):
    """Yield deterministic same-type pairs, plus additions/removals.

    Type is intentionally the first alignment key (§14.2).  Within a type,
    greedy highest-score pairing is predictable and enough for the local MVP.
    """
    grouped_a: dict[str, list] = defaultdict(list)
    grouped_b: dict[str, list] = defaultdict(list)
    for clause in clauses_a:
        grouped_a[clause.clause_type].append(clause)
    for clause in clauses_b:
        grouped_b[clause.clause_type].append(clause)

    for clause_type in sorted(set(grouped_a) | set(grouped_b)):
        remaining_a = sorted(grouped_a[clause_type], key=lambda c: c.clause_id)
        remaining_b = sorted(grouped_b[clause_type], key=lambda c: c.clause_id)
        while remaining_a and remaining_b:
            # Tie breakers make output stable across runs and databases.
            candidates = [
                (_similarity(a, b), a.clause_id, b.clause_id, a, b)
                for a in remaining_a for b in remaining_b
            ]
            _, _, _, best_a, best_b = max(candidates, key=lambda item: (item[0], item[1], item[2]))
            yield clause_type, best_a, best_b
            remaining_a.remove(best_a)
            remaining_b.remove(best_b)
        for clause in remaining_a:
            yield clause_type, clause, None
        for clause in remaining_b:
            yield clause_type, None, clause


def _status(before, after) -> str:
    if before is None:
        return "added"
    if after is None:
        return "removed"
    before_text, after_text = _display(before), _display(after)
    if _normalise(before_text) == _normalise(after_text):
        return "same"
    # A number/date amount change is material even when boilerplate makes the
    # surrounding language look extremely similar (e.g. 30 days → 10 days).
    if _values(before.original_text) != _values(after.original_text):
        return "changed"
    return "similar" if _similarity(before, after) >= 0.88 else "changed"


def compare(conn, document_id_a: str, document_id_b: str) -> ComparisonResult:
    """Align two documents and lead with changed decisions, not raw diff noise."""
    clauses_a = load_clauses(conn, document_id_a)
    clauses_b = load_clauses(conn, document_id_b)
    diffs: list[ClauseDiff] = []
    changed_decisions: set[str] = set()

    for clause_type, before, after in _pair_by_type(clauses_a, clauses_b):
        status = _status(before, after)
        affected = sorted({
            clause.feeds_decision_id
            for clause in (before, after)
            if clause is not None and clause.feeds_decision_id
        })
        diff = ClauseDiff(
            clause_type=clause_type,
            status=status,
            before=_display(before) if before else None,
            after=_display(after) if after else None,
            affected_decision_ids=affected,
            risk_delta=_risk_delta(before, after, status),
        )
        diffs.append(diff)
        if status in {"changed", "added", "removed"}:
            changed_decisions.update(affected)

    count = len(changed_decisions)
    summary = f"{count} of your decision{'s' if count != 1 else ''} changed as a result of this redraft."
    return ComparisonResult(
        comparison_id=f"cmp_{uuid.uuid4().hex[:12]}",
        document_id_a=document_id_a,
        document_id_b=document_id_b,
        clause_diffs=diffs,
        decision_impact_summary=summary,
    )


# More descriptive alias for callers outside the service package.
compare_documents = compare
