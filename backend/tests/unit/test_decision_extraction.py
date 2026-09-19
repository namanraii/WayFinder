"""Unit tests for decision extraction service and schema invariants (spec §11, §21.1)."""
from __future__ import annotations

from app.models import DecisionPoint, Option, Clause
from app.services.decision_extraction import rank_decisions


def test_decision_with_deadline_requires_inaction_guarantee():
    """Spec §7.3 & §21.1 schema invariant: any decision with a deadline must
    have an inaction option with consequence and source citation."""
    # Valid decision with deadline
    valid = DecisionPoint(
        decision_id="dec_01",
        document_id="doc_01",
        title="Contest Notice",
        triggering_clause_ids=["clause_01"],
        deadline="2026-10-01",
        options=[
            Option(
                option_id="opt_1",
                action="Respond in writing",
                consequence="Preserves dispute rights.",
                is_default_if_inaction=False,
            ),
            Option(
                option_id="opt_inaction",
                action="Do nothing",
                consequence="Grounds deemed accepted. [clause_01]",
                is_default_if_inaction=True,
                source_spans=["clause_01:0-100"],
            ),
        ],
        source_spans=["clause_01:0-100"],
    )
    assert valid.deadline == "2026-10-01"
    inaction = next(opt for opt in valid.options if opt.is_default_if_inaction)
    assert inaction.consequence
    assert inaction.source_spans


def test_rank_decisions_orders_by_deadline_and_urgency():
    """Spec §11.3: decisions are ranked by urgency (soonest deadline first, followed by decisions without deadlines)."""
    d_soon = DecisionPoint(
        decision_id="dec_soon",
        document_id="doc_01",
        title="Immediate response",
        triggering_clause_ids=["c1"],
        deadline="2026-09-20",
        days_remaining=2,
        options=[
            Option(option_id="opt1", action="Act", consequence="Avoid default", is_default_if_inaction=False),
            Option(option_id="opt2", action="Wait", consequence="Default judgment entered", is_default_if_inaction=True, source_spans=["c1:0-10"]),
        ],
        source_spans=["c1:0-10"],
    )
    d_later = DecisionPoint(
        decision_id="dec_later",
        document_id="doc_01",
        title="Later response",
        triggering_clause_ids=["c2"],
        deadline="2026-10-20",
        days_remaining=32,
        options=[
            Option(option_id="opt1", action="Act", consequence="Avoid default", is_default_if_inaction=False),
            Option(option_id="opt2", action="Wait", consequence="Late fee", is_default_if_inaction=True, source_spans=["c2:0-10"]),
        ],
        source_spans=["c2:0-10"],
    )
    d_no_deadline = DecisionPoint(
        decision_id="dec_none",
        document_id="doc_01",
        title="Optional review",
        triggering_clause_ids=["c3"],
        deadline=None,
        options=[
            Option(option_id="opt1", action="Act", consequence="Review", is_default_if_inaction=False),
        ],
        source_spans=["c3:0-10"],
    )

    dummy_clauses = [
        Clause(clause_id="c1", document_id="doc_01", clause_type="notice_period", char_span=(0, 10), original_text="...", extraction_confidence=0.9),
        Clause(clause_id="c2", document_id="doc_01", clause_type="notice_period", char_span=(0, 10), original_text="...", extraction_confidence=0.9),
        Clause(clause_id="c3", document_id="doc_01", clause_type="general", char_span=(0, 10), original_text="...", extraction_confidence=0.9),
    ]

    ranked = rank_decisions([d_no_deadline, d_later, d_soon], dummy_clauses)
    assert [d.decision_id for d in ranked] == ["dec_soon", "dec_later", "dec_none"]
