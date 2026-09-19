"""Pydantic models mirroring spec §7.1 (Document)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class Jurisdiction(BaseModel):
    status: Literal["confirmed", "inferred", "unknown"] = "unknown"
    country: Optional[str] = None
    state_or_region: Optional[str] = None
    source: Literal["user_input", "governing_law_clause", "address_field", "none"] = "none"


class Consent(BaseModel):
    consented_at: Optional[datetime] = None
    training_opt_in: bool = False


class Document(BaseModel):
    document_id: str
    user_id: str
    uploaded_at: Optional[datetime] = None
    original_filename: Optional[str] = None
    storage_uri: str
    mime_type: Optional[str] = None
    page_count: Optional[int] = None
    language_detected: Optional[str] = None
    document_type: Optional[str] = None
    document_type_confidence: Optional[float] = None
    jurisdiction: Jurisdiction = Jurisdiction()
    role_context: Optional[str] = None
    processing_status: Literal[
        "ingested", "segmented", "extracted", "graphed", "decisions_ready", "failed"
    ] = "ingested"
    consent: Consent = Consent()
