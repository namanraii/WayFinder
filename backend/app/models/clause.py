"""Pydantic models mirroring spec §7.2 (Clause)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel


class Obligation(BaseModel):
    actor: str
    action: str
    deadline_relative: Optional[str] = None
    deadline_absolute: Optional[str] = None
    condition: Optional[str] = None


class Party2Right(BaseModel):
    actor: str
    right: str
    condition: Optional[str] = None


class Risk(BaseModel):
    type: str
    description: str
    severity: str  # low | medium | high


class Clause(BaseModel):
    clause_id: str
    document_id: str
    clause_title: Optional[str] = None
    clause_type: str = "general"
    page: Optional[int] = None
    char_span: Tuple[int, int] = (0, 0)
    original_text: str
    plain_language: Optional[str] = None
    obligations: List[Obligation] = []
    rights: List[Party2Right] = []
    risks: List[Risk] = []
    missing_elements: List[str] = []
    related_clause_ids: List[str] = []
    feeds_decision_id: Optional[str] = None
    extraction_confidence: float = 0.5
