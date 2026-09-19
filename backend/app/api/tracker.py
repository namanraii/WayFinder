"""Deadline Tracker API endpoints (spec §9.2, §16, §19.5)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Response

from app.db import sqlite
from app.models import DeadlineTrackerEntry
from app.services import deadline_tracker

router = APIRouter(tags=["tracker"])


@router.get("/users/{user_id}/tracker", response_model=List[DeadlineTrackerEntry])
def list_user_deadlines(user_id: str) -> List[DeadlineTrackerEntry]:
    with sqlite.connect() as conn:
        return deadline_tracker.list_for_user(conn, user_id)


@router.get("/tracker/{tracker_id}/export.ics")
def export_tracker_ics(tracker_id: str):
    with sqlite.connect() as conn:
        try:
            _, content = deadline_tracker.export_ics(conn, tracker_id)
            return Response(
                content=content,
                media_type="text/calendar; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{tracker_id}.ics"',
                },
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Tracker entry {tracker_id!r} not found")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ICS export failed: {exc}")
