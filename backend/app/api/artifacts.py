"""Resolution Artifacts API endpoints (spec §16, §19.5)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import sqlite
from app.models import ResolutionArtifact
from app.services import resolution_artifacts

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{artifact_id}", response_model=ResolutionArtifact)
def get_artifact(artifact_id: str) -> ResolutionArtifact:
    with sqlite.connect() as conn:
        artifact = resolution_artifacts.get_artifact(conn, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id!r} not found")
        return artifact
