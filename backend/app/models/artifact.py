"""Pydantic models mirroring spec §7.5 (Resolution Artifact)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ResolutionArtifact(BaseModel):
    artifact_id: str
    decision_id: str
    type: str
    status: str = "draft"
    content: str = ""
    fields_to_fill: List[str] = []
    generated_at: Optional[datetime] = None
    disclaimer: str = ""
    model_version: Optional[str] = None
    prompt_version: Optional[str] = None
