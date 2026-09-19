"""Decisions API endpoints (spec §16, §18.6, §19.5)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import sqlite
from app.llm import guardrails
from app.models import DecisionPoint, PrepPack, ResolutionArtifact
from app.services import resolution_artifacts
from app.services.repository import load_decision

router = APIRouter(tags=["decisions"])


class ResolveRequest(BaseModel):
    option_id: Optional[str] = None


@router.get("/decisions/{decision_id}", response_model=DecisionPoint)
def get_decision(decision_id: str) -> DecisionPoint:
    with sqlite.connect() as conn:
        decision = load_decision(conn, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id!r} not found")
        return decision


@router.post("/decisions/{decision_id}/resolve", response_model=ResolutionArtifact)
def resolve_decision(decision_id: str, body: Optional[ResolveRequest] = None) -> ResolutionArtifact:
    with sqlite.connect() as conn:
        decision = load_decision(conn, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id!r} not found")

        # Server-side tier gate enforcement (§18.6, §21.1)
        # Never call LLM orchestrator for lawyer_now or legal_aid_recommended
        if not guardrails.check_tier_gate(decision.triage_tier):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Resolution draft generation is blocked for tier '{decision.triage_tier}'. "
                    "Because this decision carries high stakes or irreversible consequences, "
                    "Wayfinder does not generate self-serve legal correspondence for this tier. "
                    "Please use the consultation Prep Pack to seek legal aid or professional counsel."
                ),
            )

        option_id = body.option_id if body else None
        try:
            artifact = resolution_artifacts.generate_artifact(
                conn,
                decision_id,
                option_id=option_id,
            )
            return artifact
        except resolution_artifacts.ArtifactGenerationBlocked as err:
            raise HTTPException(status_code=403, detail=str(err))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Artifact generation failed: {exc}")


@router.post("/decisions/{decision_id}/prep-pack", response_model=PrepPack)
def get_or_create_prep_pack(decision_id: str) -> PrepPack:
    with sqlite.connect() as conn:
        decision = load_decision(conn, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id!r} not found")
        try:
            return resolution_artifacts.get_or_create_prep_pack(conn, decision_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Prep pack creation failed: {exc}")
