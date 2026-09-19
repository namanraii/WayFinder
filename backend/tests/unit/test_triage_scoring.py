"""Unit tests for deterministic triage scoring (spec §13, §21.1)."""
from __future__ import annotations

import pytest

from app.models import Document, Jurisdiction
from app.services.triage import apply_jurisdiction_gate, compute_tier


@pytest.mark.parametrize(
    "stakes,reversibility,ambiguity,expected_tier",
    [
        ("low", "high", "low", "self_serve"),
        ("low", "high", "high", "self_serve_with_escalation_path"),
        ("medium", "high", "low", "self_serve_with_escalation_path"),
        ("medium", "low", "low", "legal_aid_recommended"),
        ("medium", "high", "high", "legal_aid_recommended"),
        ("medium", "low", "high", "legal_aid_recommended"),
        ("high", "high", "low", "lawyer_now"),
        ("high", "low", "low", "lawyer_now"),
        ("high", "high", "high", "lawyer_now"),
        ("high", "low", "high", "lawyer_now"),
    ],
)
def test_compute_tier_matrix(stakes: str, reversibility: str, ambiguity: str, expected_tier: str):
    """Every combination in spec §13.3 maps to its authoritative tier."""
    assert compute_tier(stakes, reversibility, ambiguity) == expected_tier


def test_jurisdiction_unknown_downgrade():
    """Spec §13.3: unconfirmed jurisdiction strictly downgrades or maintains caution, never upgrades."""
    # self_serve downgrades to self_serve_with_escalation_path
    assert apply_jurisdiction_gate("self_serve", "unknown") == "self_serve_with_escalation_path"

    # self_serve_with_escalation_path downgrades to legal_aid_recommended
    assert apply_jurisdiction_gate("self_serve_with_escalation_path", "unknown") == "legal_aid_recommended"

    # legal_aid_recommended stays legal_aid_recommended
    assert apply_jurisdiction_gate("legal_aid_recommended", "unknown") == "legal_aid_recommended"

    # lawyer_now stays lawyer_now (already most conservative tier)
    assert apply_jurisdiction_gate("lawyer_now", "unknown") == "lawyer_now"


def test_jurisdiction_confirmed_preserves_tier():
    """Confirmed jurisdiction leaves the computed tier untouched."""
    for tier in ["self_serve", "self_serve_with_escalation_path", "legal_aid_recommended", "lawyer_now"]:
        assert apply_jurisdiction_gate(tier, "confirmed") == tier
        assert apply_jurisdiction_gate(tier, "inferred") == tier
