"""Deterministic text heuristics shared by the stub LLM provider and services.

These implement the rule-based parts of the spec (segmentation, classification,
deadline/consequence detection) so the whole pipeline runs offline and tests
are deterministic. A real LLM provider replaces the phrasing steps only.
"""
from __future__ import annotations

import re
from typing import Optional

# §11.1(b) — fixed set of decision-bearing clause types.
DECISION_BEARING_TYPES = {
    "termination", "notice_period", "dispute_resolution", "renewal",
    "arbitration_optout", "payment_dispute", "cure_period",
    "right_of_first_refusal", "indemnity_trigger",
}

CLAUSE_TAXONOMY = sorted(DECISION_BEARING_TYPES | {
    "payment_terms", "confidentiality", "liability", "governing_law",
    "definitions", "general",
})

# §13.1 — fixed high-stakes document categories.
HIGH_STAKES_CATEGORIES = {
    "eviction_notice", "termination_letter", "custody_related",
    "debt_collection", "criminal_matter", "immigration_related",
    "domestic_violence_related",
}

# §13.1 — irreversibility keyword/clause-type heuristic.
IRREVERSIBLE_KEYWORDS = ["termination", "release_of_claims", "waiver", "admission",
                         "release of claims", "waive", "irrevocable"]

# §14.1 — standard protections checked per document type.
MISSING_ELEMENT_CHECKLIST = {
    "default": ["governing law", "dispute resolution"],
    "lease": ["notice period", "liability cap", "dispute resolution", "governing law"],
    "contract": ["notice period", "liability cap", "dispute resolution", "governing law",
                 "force majeure", "severability"],
    "terms_of_service": ["refund terms", "data deletion", "dispute resolution", "governing law"],
}

_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("arbitration_optout", ["arbitration", "opt out", "opt-out"]),
    ("notice_period", ["notice", "within", "days of this notice", "respond in writing"]),
    ("cure_period", ["cure", "remedy the breach"]),
    ("payment_dispute", ["payment dispute", "dispute.*payment", "invoice.*dispute"]),
    ("payment_terms", ["payment", "invoice", "fee", "compensation", "deposit"]),
    ("termination", ["terminate", "termination"]),
    ("renewal", ["renew", "auto-renew", "automatic renewal"]),
    ("dispute_resolution", ["dispute", "mediation", "arbitration", "jurisdiction of"]),
    ("right_of_first_refusal", ["right of first refusal"]),
    ("indemnity_trigger", ["indemnif", "hold harmless"]),
    ("confidentiality", ["confidential"]),
    ("liability", ["liability", "liable"]),
    ("governing_law", ["governed by the laws", "governing law"]),
    ("definitions", ["definitions", "means:"]),
]

_DOCTYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("eviction_notice", ["eviction", "notice to vacate", "vacate the premises"]),
    ("debt_collection", ["debt", "amount due", "collection"]),
    ("termination_letter", ["termination of employment", "severance"]),
    ("terms_of_service", ["terms of service", "terms of use", "privacy policy"]),
    ("employment_offer", ["offer of employment", "employment agreement"]),
    ("freelance_contract", ["services agreement", "contractor", "freelance", "statement of work"]),
    ("lease", ["lease", "tenancy agreement", "landlord", "tenant"]),
    ("legal_notice", ["notice", "hereby"]),
]

CONSEQUENCE_MARKERS = [
    "deemed", "shall be treated as", "will be treated as", "acceptance",
    "forfeit", "lose the right", "loses the right", "waive", "terminate",
    "late fee", "penalty", "liquidated damages", "no longer be able",
    "automatically", "binding arbitration",
]

_DEADLINE_RE = re.compile(
    r"within\s+(\d+)\s*(calendar\s+|business\s+)?days([^.\n]*)", re.IGNORECASE)
_GOVERNING_LAW_RE = re.compile(
    r"governed by the laws of\s+([A-Z][A-Za-z ,]+)", re.IGNORECASE)


from functools import lru_cache

_TYPE_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (ctype, [re.compile(k) for k in keywords])
    for ctype, keywords in _TYPE_KEYWORDS
]

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@lru_cache(maxsize=512)
def classify_clause(text: str) -> tuple[str, float]:
    low = text.lower()
    best, best_hits = "general", 0
    for ctype, patterns in _TYPE_COMPILED:
        hits = sum(1 for pat in patterns if pat.search(low))
        if hits > best_hits:
            best, best_hits = ctype, hits
    if best == "arbitration_optout" and ("opt out" in low or "opt-out" in low):
        return best, 0.9
    if best_hits == 0:
        return "general", 0.4
    return best, min(0.6 + 0.15 * best_hits, 0.95)


def classify_document(text: str, filename: str = "") -> tuple[str, float]:
    low = (text[:4000] + " " + filename).lower()
    best, best_hits = "legal_notice", 0
    for dtype, keywords in _DOCTYPE_KEYWORDS:
        hits = sum(1 for k in keywords if k in low)
        if hits > best_hits:
            best, best_hits = dtype, hits
    return best, (min(0.6 + 0.12 * best_hits, 0.95) if best_hits else 0.4)


def extract_deadline(text: str) -> Optional[tuple[str, int]]:
    """Returns (deadline_relative, days) e.g. ('21 days from notice date', 21)."""
    m = _DEADLINE_RE.search(text)
    if not m:
        return None
    days = int(m.group(1))
    tail = (m.group(3) or "").strip().strip(",")
    rel = f"{days} days"
    if m.group(2):
        rel = f"{days} {m.group(2).strip()} days"
    if tail:
        rel += f" {tail}"
    return rel, days


def consequence_sentences(text: str) -> list[str]:
    sents = _SENT_SPLIT_RE.split(text.strip())
    return [s.strip() for s in sents
            if any(mk in s.lower() for mk in CONSEQUENCE_MARKERS)]


def detect_obligation_action(text: str) -> Optional[str]:
    low = text.lower()
    for action in ["respond in writing", "respond", "object", "file", "pay",
                   "notify", "opt out", "opt-out", "vacate", "cure", "return"]:
        if action in low:
            return action.replace("-", " ")
    return None


def detect_governing_law(text: str) -> Optional[str]:
    m = _GOVERNING_LAW_RE.search(text)
    return m.group(1).strip().rstrip(".") if m else None


def detect_language(text: str) -> str:
    # Bound sample size to 2000 chars for O(1) evaluation on arbitrarily large texts
    sample = text[:2000]
    ascii_ratio = sum(1 for c in sample if ord(c) < 128) / max(len(sample), 1)
    return "en" if ascii_ratio > 0.9 else "unknown"


def title_for(ctype: str) -> str:
    return ctype.replace("_", " ").title()


def summarize_deadline_action(ctype: str, action: Optional[str]) -> str:
    if ctype == "arbitration_optout":
        return "Opt out of binding arbitration"
    if ctype == "notice_period":
        return "Respond to the notice"
    if ctype == "termination":
        return "Respond to the termination terms"
    if ctype == "renewal":
        return "Cancel before auto-renewal"
    if ctype == "payment_dispute":
        return "Raise a payment dispute"
    if ctype == "cure_period":
        return "Cure the breach"
    if ctype == "payment_terms":
        return "Meet the payment obligation"
    return f"Act on the {title_for(ctype)} clause"


def missing_elements_for(document_type: str, clause_type: str, text: str) -> list[str]:
    key = "default"
    if document_type in ("lease", "eviction_notice"):
        key = "lease"
    elif document_type in ("freelance_contract", "employment_offer"):
        key = "contract"
    elif document_type == "terms_of_service":
        key = "terms_of_service"
    low = text.lower()
    return [p for p in MISSING_ELEMENT_CHECKLIST.get(key, [])
            if p not in low and p.split()[0] not in low][:3]
