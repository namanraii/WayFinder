"""Pydantic models mirroring spec §7.6 (Prep Pack)."""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class PrepPack(BaseModel):
    prep_pack_id: str
    decision_id: str
    contents: Dict[str, Any]
    export_formats: List[str] = ["pdf", "share_link"]
