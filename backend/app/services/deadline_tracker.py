"""Deadline tracking and calendar export (spec §9.2 and §7.8)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.db import sqlite
from app.models import DeadlineTrackerEntry
from app.services.repository import load_decision, tracker_from_row


def sync_for_document(conn, document_id: str) -> list[DeadlineTrackerEntry]:
    created = []
    # Load all decisions with deadlines in one query instead of N individual queries
    rows = sqlite.query(
        conn,
        "SELECT * FROM decisions WHERE document_id = ? AND deadline IS NOT NULL",
        (document_id,),
    )
    if not rows:
        return []

    from app.services.repository import decision_from_row
    decisions = [decision_from_row(r) for r in rows]

    # Check all existing trackers in one query
    dec_ids = [d.decision_id for d in decisions]
    placeholders = ", ".join("?" for _ in dec_ids)
    existing_rows = sqlite.query(
        conn,
        f"SELECT * FROM deadline_tracker WHERE decision_id IN ({placeholders})",
        dec_ids,
    )
    existing_by_dec = {r["decision_id"]: tracker_from_row(r) for r in existing_rows}

    rows_to_insert: list[dict] = []
    for decision in decisions:
        if decision.decision_id in existing_by_dec:
            created.append(existing_by_dec[decision.decision_id])
            continue
        inaction = next((option for option in decision.options if option.is_default_if_inaction), None)
        action = next((option.action for option in decision.options if not option.is_default_if_inaction), decision.title)
        entry = DeadlineTrackerEntry(
            tracker_id=f"trk_{uuid.uuid4().hex[:12]}", decision_id=decision.decision_id,
            deadline=decision.deadline, resolving_action=action,
            inaction_consequence_short=(inaction.consequence[:240] if inaction else None),
        )
        rows_to_insert.append({
            "tracker_id": entry.tracker_id, "decision_id": entry.decision_id,
            "deadline": entry.deadline, "resolving_action": entry.resolving_action,
            "inaction_consequence_short": entry.inaction_consequence_short,
            "reminder_schedule": entry.reminder_schedule, "status": entry.status,
        })
        created.append(entry)

    if rows_to_insert:
        sqlite.batch_insert(conn, "deadline_tracker", rows_to_insert)

    return created


def list_for_user(conn, user_id: str) -> list[DeadlineTrackerEntry]:
    rows = sqlite.query(conn, """SELECT t.* FROM deadline_tracker t
        JOIN decisions d ON d.decision_id = t.decision_id
        JOIN documents doc ON doc.document_id = d.document_id
        WHERE doc.user_id = ? AND t.status = 'open' ORDER BY t.deadline""", (user_id,))
    return [tracker_from_row(row) for row in rows]


def export_ics(conn, tracker_id: str) -> tuple[str, str]:
    row = sqlite.get(conn, "deadline_tracker", "tracker_id", tracker_id)
    if not row:
        raise KeyError(f"Tracker entry {tracker_id!r} was not found")
    entry = tracker_from_row(row)
    decision = load_decision(conn, entry.decision_id)
    title = (decision.title if decision else "Wayfinder deadline").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    description = " ".join(filter(None, [entry.resolving_action, entry.inaction_consequence_short])).replace("\\", "\\\\").replace("\n", "\\n")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    date_value = entry.deadline.replace("-", "")
    content = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Wayfinder//Deadline Tracker//EN", "BEGIN:VEVENT",
        f"UID:{entry.tracker_id}@wayfinder.local", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{date_value}",
        f"SUMMARY:{title}", f"DESCRIPTION:{description}", "END:VEVENT", "END:VCALENDAR", "",
    ])
    sqlite.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = sqlite.EXPORT_DIR / f"{entry.tracker_id}.ics"
    path.write_text(content, encoding="utf-8")
    return str(path), content
