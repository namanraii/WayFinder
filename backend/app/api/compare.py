"""Document Comparison API endpoints (spec §14.2, §16, §19.5)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import sqlite
from app.models import ComparisonResult
from app.services import comparison
from app.services.repository import load_document

router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    document_id_a: str
    document_id_b: str


@router.post("/documents/compare", response_model=ComparisonResult)
async def compare_documents(body: CompareRequest) -> ComparisonResult:
    with sqlite.connect() as conn:
        doc_a = load_document(conn, body.document_id_a)
        if not doc_a:
            raise HTTPException(status_code=404, detail=f"Document {body.document_id_a!r} not found")
        doc_b = load_document(conn, body.document_id_b)
        if not doc_b:
            raise HTTPException(status_code=404, detail=f"Document {body.document_id_b!r} not found")

        try:
            return comparison.compare_documents(conn, body.document_id_a, body.document_id_b)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Comparison failed: {exc}")
