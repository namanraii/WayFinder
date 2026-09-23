"""Documents API endpoints (spec §16, §19.5)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile

from app.db import sqlite
from app.models import Clause, DecisionListResponse, DecisionSummary, Document
from app.services import pipeline
from app.services.repository import load_clauses, load_decisions, load_document

router = APIRouter(tags=["documents"])


def _ensure_user(conn, user_id: str, training_opt_in: bool = False) -> None:
    existing = sqlite.get(conn, "users", "user_id", user_id)
    if not existing:
        sqlite.insert(conn, "users", {
            "user_id": user_id,
            "training_opt_in": 1 if training_opt_in else 0,
            "preferred_language": "en",
        })
    else:
        sqlite.update(conn, "users", "user_id", user_id, {
            "training_opt_in": 1 if training_opt_in else 0,
        })


@router.post("/documents", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Form("usr_demo"),
    role_context: str = Form("tenant"),
    training_opt_in: str = Form("false"),
    country: Optional[str] = Form(None),
    state_or_region: Optional[str] = Form(None),
) -> Document:
    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    opt_in = training_opt_in.lower() in ("true", "1", "yes")

    with sqlite.connect() as conn:
        _ensure_user(conn, user_id, opt_in)

        filename = file.filename or "uploaded_document"
        clean_filename = Path(filename).name
        dest_path = sqlite.UPLOAD_DIR / f"{document_id}_{clean_filename}"
        sqlite.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        dest_path.write_bytes(content)

        mime_type = "application/pdf" if clean_filename.lower().endswith(".pdf") else "text/plain"

        # Determine user-provided jurisdiction if given
        has_user_jurisdiction = bool((country and country.strip()) or (state_or_region and state_or_region.strip()))
        j_status = "inferred" if has_user_jurisdiction else "unknown"
        j_source = "user_input" if has_user_jurisdiction else "none"

        sqlite.insert(conn, "documents", {
            "document_id": document_id,
            "user_id": user_id,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "original_filename": clean_filename,
            "storage_uri": str(dest_path),
            "mime_type": mime_type,
            "role_context": role_context.strip() or "general",
            "processing_status": "ingested",
            "jurisdiction_status": j_status,
            "jurisdiction_country": country.strip() if country else None,
            "jurisdiction_region": state_or_region.strip() if state_or_region else None,
            "jurisdiction_source": j_source,
            "consented_at": datetime.now(timezone.utc).isoformat(),
        })

        # Run pipeline synchronously for local runtime
        try:
            pipeline.run(conn, document_id)
        except Exception as exc:
            # Document status is marked failed in pipeline.run
            doc = load_document(conn, document_id)
            if doc:
                return doc
            raise HTTPException(status_code=500, detail=f"Pipeline processing failed: {exc}")

        doc = load_document(conn, document_id)
        if not doc:
            raise HTTPException(status_code=500, detail="Document could not be retrieved after processing")
        return doc


@router.get("/documents/{document_id}", response_model=Document)
async def get_document(document_id: str, response: Response) -> Document:
    response.headers["Cache-Control"] = "private, max-age=120"
    with sqlite.connect() as conn:
        doc = load_document(conn, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {document_id!r} not found")
        return doc


@router.get("/documents/{document_id}/clauses", response_model=List[Clause])
async def get_document_clauses(
    document_id: str,
    response: Response,
    limit: Optional[int] = Query(None, ge=1, le=500, description="Max clauses to return"),
    offset: int = Query(0, ge=0, description="Clause offset for pagination"),
) -> List[Clause]:
    response.headers["Cache-Control"] = "private, max-age=60"
    with sqlite.connect() as conn:
        doc = load_document(conn, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {document_id!r} not found")
        clauses = load_clauses(conn, document_id)
        if offset > 0 or limit is not None:
            end = (offset + limit) if limit is not None else len(clauses)
            return clauses[offset:end]
        return clauses


@router.get("/documents/{document_id}/decisions", response_model=DecisionListResponse)
async def get_document_decisions(
    document_id: str,
    response: Response,
    limit: Optional[int] = Query(None, ge=1, le=100, description="Max decisions to return"),
    offset: int = Query(0, ge=0, description="Decision offset for pagination"),
) -> DecisionListResponse:
    response.headers["Cache-Control"] = "private, max-age=60"
    with sqlite.connect() as conn:
        doc = load_document(conn, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {document_id!r} not found")
        decisions = load_decisions(conn, document_id)
        summaries = [
            DecisionSummary(
                decision_id=d.decision_id,
                title=d.title,
                deadline=d.deadline,
                days_remaining=d.days_remaining,
                triage_tier=d.triage_tier,
                confidence=d.confidence,
            )
            for d in decisions
        ]
        if offset > 0 or limit is not None:
            end = (offset + limit) if limit is not None else len(summaries)
            summaries = summaries[offset:end]
        return DecisionListResponse(
            document_id=doc.document_id,
            processing_status=doc.processing_status,
            decisions=summaries,
        )

