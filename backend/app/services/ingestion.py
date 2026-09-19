"""Ingestion Service — spec §9.2. Upload, text extraction, language /
jurisdiction-signal detection, document classification. Never guesses
jurisdiction: writes 'unknown' unless an explicit signal exists (§10)."""
from __future__ import annotations

import re
from pathlib import Path

from app.db import sqlite
from app.services import heuristics as hz

TEXT_MIME = {"text/plain", "text/markdown"}


def extract_text(storage_path: Path, mime_type: str) -> tuple[str, int]:
    """Returns (text, page_count). OCR (Tesseract) is out of scope for the
    local demo; PDFs are text-extracted via pypdf."""
    if mime_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(storage_path))
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
        return text, len(reader.pages)
    return storage_path.read_text(encoding="utf-8", errors="replace"), 1


def run(conn, document_id: str) -> str:
    doc = sqlite.get(conn, "documents", "document_id", document_id)
    text, page_count = extract_text(Path(doc["storage_uri"]), doc["mime_type"] or "text/plain")

    language = hz.detect_language(text)
    doc_type, doc_conf = hz.classify_document(text, doc["original_filename"] or "")

    # Jurisdiction signals (§9.2, §10): governing-law clause -> confirmed;
    # never silently default. Address-field heuristic -> inferred (skipped
    # here unless a recognizable pattern exists).
    j_status, j_region, j_source = "unknown", None, "none"
    law = hz.detect_governing_law(text)
    if law:
        j_status, j_region, j_source = "confirmed", law, "governing_law_clause"

    # Respect explicit user input collected at upload (§19.5 Upload screen).
    if doc["jurisdiction_source"] == "user_input" and doc["jurisdiction_status"]:
        j_status = doc["jurisdiction_status"]
        j_region = doc["jurisdiction_region"]
        j_source = "user_input"

    sqlite.update(conn, "documents", "document_id", document_id, {
        "page_count": page_count,
        "language_detected": language,
        "document_type": doc_type,
        "document_type_confidence": doc_conf,
        "jurisdiction_status": j_status,
        "jurisdiction_region": j_region,
        "jurisdiction_source": j_source,
        "processing_status": "segmented",
    })
    # stash raw text alongside the upload for downstream services
    Path(doc["storage_uri"]).with_suffix(".extracted.txt").write_text(text, encoding="utf-8")
    return text
