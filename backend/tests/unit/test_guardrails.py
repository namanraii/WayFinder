from app.llm.guardrails import (
    DISCLAIMER,
    JURISDICTION_UNKNOWN_NOTE,
    check_tier_gate,
    find_banned_phrases,
)


def test_banned_phrases_are_detected_before_persistence():
    violations = find_banned_phrases("I recommend that you should sue; you will win.")

    assert r"\bi recommend\b" in violations
    assert "you should sue" in violations
    assert "you will win" in violations


def test_tier_gate_permits_only_send_ready_safe_tiers():
    assert check_tier_gate("self_serve")
    assert check_tier_gate("self_serve_with_escalation_path")
    assert not check_tier_gate("legal_aid_recommended")
    assert not check_tier_gate("lawyer_now")


def test_required_disclosures_are_stable_product_text():
    assert "does not provide legal advice" in DISCLAIMER
    assert JURISDICTION_UNKNOWN_NOTE.startswith("This document doesn't confirm")
