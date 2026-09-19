import pytest
from pydantic import ValidationError

from app.models import DecisionPoint


def _base_decision(**overrides):
    payload = {
        "decision_id": "dec_test",
        "document_id": "doc_test",
        "title": "Respond before the deadline",
        "triggering_clause_ids": ["clause_test"],
        "deadline": "2026-10-01",
        "options": [],
    }
    payload.update(overrides)
    return payload


def test_deadline_decision_rejects_missing_inaction_option():
    with pytest.raises(ValidationError, match="is_default_if_inaction"):
        DecisionPoint(**_base_decision())


@pytest.mark.parametrize("option", [
    {"option_id": "o", "action": "Do nothing", "consequence": "", "is_default_if_inaction": True,
     "source_spans": ["clause_test:0-1"]},
    {"option_id": "o", "action": "Do nothing", "consequence": "A cited result", "is_default_if_inaction": True,
     "source_spans": []},
])
def test_deadline_inaction_option_requires_consequence_and_citation(option):
    with pytest.raises(ValidationError):
        DecisionPoint(**_base_decision(options=[option]))


def test_deadline_decision_accepts_cited_inaction_option():
    decision = DecisionPoint(**_base_decision(options=[{
        "option_id": "o", "action": "Do nothing", "consequence": "The document describes a default.",
        "is_default_if_inaction": True, "source_spans": ["clause_test:0-23"],
    }]))

    assert decision.options[0].is_default_if_inaction
