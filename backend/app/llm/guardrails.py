"""Guardrails layer — spec §18. Pre-write gate, not a post-hoc display filter."""
from __future__ import annotations

import re
from typing import Optional

# §18.1 — verbatim disclaimer, appended at code level to every major output.
DISCLAIMER = (
    "Wayfinder provides legal information and preparation support to help you "
    "understand your documents and options. It does not provide legal advice. "
    "For advice specific to your situation, consult a qualified legal "
    "professional or legal aid organization."
)

# §18.4 — exact required text for jurisdiction-unknown statutory reliance.
JURISDICTION_UNKNOWN_NOTE = (
    "This document doesn't confirm your jurisdiction, so this shows only what "
    "the document itself says — not any additional legal defaults that might "
    "apply in your area. Confirming your location may change this."
)

# §12 / §9.2 — exact fallback when no triggers edge exists.
INACTION_UNSPECIFIED = (
    "This document does not specify what happens if you don't act by this date."
)

# §18.2 — banned phrasing (hard check, triggers regeneration).
BANNED_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"you should sue",
        r"you will win",
        r"this clause is illegal",
        r"you are entitled to",
        r"\bi recommend\b",
        r"my advice is",
    ]
]

# §18.2 — required style (soft check).
HEDGED_MARKERS = ["this may", "consider", "this appears", "you may want to ask", "might"]

# §7.4 — tiers for which drafted send-ready artifacts are permitted.
DRAFT_PERMITTED_TIERS = {"self_serve", "self_serve_with_escalation_path"}


def find_banned_phrases(text: str) -> list[str]:
    return [p.pattern for p in BANNED_PATTERNS if p.search(text or "")]


def has_hedged_phrasing(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in HEDGED_MARKERS)


def check_tier_gate(triage_tier: Optional[str]) -> bool:
    """§18.6 — True if drafted artifact generation is permitted for this tier."""
    return triage_tier in DRAFT_PERMITTED_TIERS


def check_jurisdiction_gate(document, decision_draft) -> Optional[str]:
    """§10 — single shared guard used by Decision Extraction and Triage.

    Returns the exact §18.4 note when jurisdiction is unknown and the decision
    involves a deadline/consequence (where statutory defaults would normally
    matter); otherwise None. Downgrade-only logic for tiers lives in triage.py.
    """
    status = getattr(getattr(document, "jurisdiction", None), "status", "unknown")
    if status == "unknown" and getattr(decision_draft, "deadline", None):
        return JURISDICTION_UNKNOWN_NOTE
    return None
