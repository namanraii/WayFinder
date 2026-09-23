"""Deadline Tracker API endpoints (spec §9.2, §16, §19.5)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response

from app.db import sqlite
from app.models import DeadlineTrackerEntry
from app.services import deadline_tracker

router = APIRouter(tags=["tracker"])


@router.get("/users/{user_id}/tracker", response_model=List[DeadlineTrackerEntry])
async def list_user_deadlines(
    user_id: str,
    response: Response,
    limit: Optional[int] = Query(None, ge=1, le=200, description="Max deadlines to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> List[DeadlineTrackerEntry]:
    response.headers["Cache-Control"] = "private, max-age=30"
    with sqlite.connect() as conn:
        items = deadline_tracker.list_for_user(conn, user_id)
        if offset > 0 or limit is not None:
            end = (offset + limit) if limit is not None else len(items)
            return items[offset:end]
        return items


@router.get("/tracker/{tracker_id}/export.ics")
async def export_tracker_ics(tracker_id: str):
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
