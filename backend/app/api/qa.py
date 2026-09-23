"""Document Q&A API endpoints (spec §14.4, §16, §19.5)."""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import sqlite
from app.services import qa
from app.services.repository import load_document

router = APIRouter(tags=["qa"])


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    citations: Optional[List[Any]] = []
    confidence: Optional[str] = "medium"
    linked_decision_id: Optional[str] = None
    disclaimer: Optional[str] = None


@router.post("/documents/{document_id}/ask", response_model=AskResponse)
async def ask_document(document_id: str, body: AskRequest) -> AskResponse:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    with sqlite.connect() as conn:
        doc = load_document(conn, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {document_id!r} not found")

        try:
            result = qa.answer_question(conn, document_id, body.question)
            return AskResponse(
                answer=result["answer"],
                citations=result.get("citations", []),
                confidence=result.get("confidence", "medium"),
                linked_decision_id=result.get("linked_decision_id"),
                disclaimer=result.get("disclaimer"),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Q&A failed: {exc}")
