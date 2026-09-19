"""Pydantic models mirroring spec §7.3 (Decision Point) and §7.4 (Triage Tier)."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, model_validator

TriageTier = Literal[
    "self_serve",
    "self_serve_with_escalation_path",
    "legal_aid_recommended",
    "lawyer_now",
]


class Option(BaseModel):
    option_id: str
    action: str
    consequence: str
    effort: str = "medium"
    cost: str = "unknown"
    is_default_if_inaction: bool = False
    source_spans: List[str] = []


class TriageScores(BaseModel):
    reversibility: Literal["low", "high"]
    stakes: Literal["low", "medium", "high"]
    ambiguity: Literal["low", "high"]


class DecisionPoint(BaseModel):
    decision_id: str
    document_id: str
    title: str
    triggering_clause_ids: List[str]
    deadline: Optional[str] = None  # ISO date
    days_remaining: Optional[int] = None
    options: List[Option]
    triage_tier: Optional[TriageTier] = None
    triage_scores: Optional[TriageScores] = None
    triage_reasoning: Optional[str] = None
    resolution_artifact_id: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "medium"
    jurisdiction_confidence_note: Optional[str] = None
    source_spans: List[str] = []

    @model_validator(mode="after")
    def enforce_inaction_invariant(self) -> "DecisionPoint":
        """Spec §7.3 schema-level invariant: any Decision Point with a non-null
        deadline MUST contain at least one option with is_default_if_inaction=True,
        whose consequence is non-empty and references at least one source span
        (its own source_spans or the decision's). Rejected, never shown incomplete."""
        if self.deadline is not None:
            inaction = [o for o in self.options if o.is_default_if_inaction]
            if not inaction:
                raise ValueError(
                    "Decision Point with a deadline must include an is_default_if_inaction option"
                )
            for opt in inaction:
                if not opt.consequence.strip():
                    raise ValueError("inaction option consequence must be non-empty")
                if not (opt.source_spans or self.source_spans):
                    raise ValueError(
                        "inaction option must reference at least one source span"
                    )
        return self


class DecisionSummary(BaseModel):
    decision_id: str
    title: str
    deadline: Optional[str] = None
    days_remaining: Optional[int] = None
    triage_tier: Optional[TriageTier] = None
    confidence: Optional[Literal["high", "medium", "low"]] = "medium"


class DecisionListResponse(BaseModel):
    document_id: str
    processing_status: str
    decisions: List[DecisionSummary]

