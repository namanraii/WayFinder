"""WhatsApp access channel webhook stub (spec §16, §19.7)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.db import sqlite
from app.services.repository import load_decisions

router = APIRouter(tags=["whatsapp"])


class WhatsAppWebhookResponse(BaseModel):
    status: str
    reply_text: str
    decision_id: Optional[str] = None


@router.post("/webhooks/whatsapp", response_model=WhatsAppWebhookResponse)
async def whatsapp_webhook(request: Request) -> WhatsAppWebhookResponse:
    # Accept JSON or form-encoded (Twilio / Meta style)
    content_type = request.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        form = await request.form()
        data = dict(form)

    body_text = str(data.get("Body") or data.get("text") or "").strip()
    from_user = str(data.get("From") or data.get("from") or "whatsapp_user")
    document_id = str(data.get("document_id") or "")

    with sqlite.connect() as conn:
        # If document_id provided or query latest document for user
        if not document_id:
            row = sqlite.query(
                conn,
                "SELECT document_id FROM documents ORDER BY uploaded_at DESC LIMIT 1",
            )
            if row:
                document_id = row[0]["document_id"]

        if document_id:
            decisions = load_decisions(conn, document_id)
            if decisions:
                top_decision = decisions[0]
                inaction = next((opt for opt in top_decision.options if opt.is_default_if_inaction), None)
                consequence = inaction.consequence if inaction else "loss of your rights or remedies"
                # Strip citations/markup for clean mobile SMS / WhatsApp rendering
                consequence_first = consequence.split(".")[0].strip()
                deadline_str = top_decision.deadline or "stated in document"

                reply = (
                    f"You have 1 urgent decision: {top_decision.title}. "
                    f"Deadline: {deadline_str}. "
                    f"If you don't act: {consequence_first}. "
                    "Reply 1 to see your options, or 2 to talk to a legal aid volunteer."
                )
                return WhatsAppWebhookResponse(
                    status="success",
                    reply_text=reply,
                    decision_id=top_decision.decision_id,
                )

        # Fallback default intake prompt
        return WhatsAppWebhookResponse(
            status="awaiting_document",
            reply_text=(
                "Welcome to Wayfinder. Please send a photo or PDF of your legal document or notice, "
                "and we will extract your deadlines and decisions."
            ),
        )
