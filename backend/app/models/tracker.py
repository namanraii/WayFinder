"""Pydantic models mirroring spec §7.7 (Comparison Result) and §7.8 (Deadline Tracker Entry)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ClauseDiff(BaseModel):
    clause_type: str
    status: str  # same | similar | changed | added | removed
    before: Optional[str] = None
    after: Optional[str] = None
    affected_decision_ids: List[str] = []
    risk_delta: Optional[str] = None  # increased | decreased | unchanged


class ComparisonResult(BaseModel):
    comparison_id: str
    document_id_a: str
    document_id_b: str
    clause_diffs: List[ClauseDiff]
    decision_impact_summary: str


class DeadlineTrackerEntry(BaseModel):
    tracker_id: str
    decision_id: str
    deadline: str
    resolving_action: Optional[str] = None
    inaction_consequence_short: Optional[str] = None
    reminder_schedule: List[str] = ["T-7d", "T-3d", "T-1d"]
    status: str = "open"  # open | resolved | missed
    calendar_export_ics_uri: Optional[str] = None
