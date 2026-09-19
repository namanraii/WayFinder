"""Deterministic Cost-of-Inaction Reasoner (spec §12).

The graph decides *whether* a consequence exists and which source clauses it
comes from.  The LLM is deliberately used only to put an already traversed
path into plain language.  In particular, an absent ``triggers`` edge never
causes an LLM call: the documented fallback is returned verbatim instead.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Iterable, Optional

from app.db import sqlite
from app.llm.guardrails import INACTION_UNSPECIFIED
from app.llm.orchestrator import LLMOrchestrator
from app.models import Option
from app.services.document_graph import traverse_triggers


def build(
    conn,
    document_id: str,
    deadline_node_id: Optional[str],
    orchestrator: Optional[LLMOrchestrator] = None,
    *,
    source_spans: Optional[Iterable[str]] = None,
) -> Option:
    """Build the required ``Do nothing`` option for one deadline.

    ``deadline_node_id`` is intentionally an explicit graph-node id rather
    than a clause id.  That keeps the causal lookup pinned to the particular
    obligation/deadline that generated the decision.  ``source_spans`` gives
    callers a truthful fallback citation when a graph is partially populated.
    """
    path = (
        traverse_triggers(conn, document_id, deadline_node_id, max_hops=3)
        if deadline_node_id
        else []
    )
    normalized_path = [_normalize_node(node) for node in path]
    consequence_nodes = [
        node for node in normalized_path if node.get("node_type") != "deadline"
    ]
    spans = _source_spans(
        conn,
        document_id,
        normalized_path,
        supplied=source_spans,
        deadline_node_id=deadline_node_id,
    )

    # This branch must remain before any orchestrator call.  It is the core
    # anti-hallucination guarantee tested in §21.1.
    if not consequence_nodes:
        return Option(
            option_id=_option_id(),
            action="Do nothing",
            consequence=INACTION_UNSPECIFIED,
            effort="none",
            cost="unknown — not specified in document",
            is_default_if_inaction=True,
            source_spans=spans,
        )

    phrase = _phrase_path(normalized_path, orchestrator)
    if not phrase:
        # A failed phrasing call must not create a free-text substitute.  This
        # wording is a deterministic rendering of the exact traversed texts.
        phrase = _deterministic_phrase(consequence_nodes)

    return Option(
        option_id=_option_id(),
        action="Do nothing",
        consequence=phrase,
        effort="none",
        cost=_summarize_stakes(consequence_nodes),
        is_default_if_inaction=True,
        source_spans=spans,
    )


def _phrase_path(path: list[dict[str, Any]], orchestrator: Optional[LLMOrchestrator]) -> str:
    """Ask the LLM to phrase, never infer, the structured graph path."""
    orchestrator = orchestrator or LLMOrchestrator()

    def validate(raw: Any) -> tuple[bool, list[str]]:
        value = _as_phrase(raw)
        return (bool(value), [] if value else ["Expected a non-empty consequence phrase"])

    result = orchestrator.generate(
        prompt_name="inaction_phrasing_v1",
        prompt_version="inaction_phrasing_v1",
        inputs={
            "consequence_path": path,
            "instruction": (
                "Phrase this exact causal chain in plain language. Do not add "
                "any consequence not present in the provided chain."
            ),
        },
        validator=validate,
        entity_type="decision",
        entity_id=None,
    )
    if not getattr(result, "ok", False):
        return ""
    return _as_phrase(getattr(result, "output", None))


def _as_phrase(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("consequence", "text", "answer", "phrase"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _normalize_node(node: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(node)
    props = normalized.get("properties")
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except json.JSONDecodeError:
            props = {}
    normalized["properties"] = props if isinstance(props, dict) else {}
    return normalized


def _source_spans(
    conn,
    document_id: str,
    path: list[dict[str, Any]],
    *,
    supplied: Optional[Iterable[str]],
    deadline_node_id: Optional[str],
) -> list[str]:
    spans = [span for span in (supplied or []) if isinstance(span, str) and span]

    for node in path:
        props = node.get("properties") or {}
        clause_id = props.get("source_clause_id") or node.get("ref_id")
        span = props.get("char_span")
        if clause_id and isinstance(span, (list, tuple)) and len(span) == 2:
            spans.append(f"{clause_id}:{span[0]}-{span[1]}")
        elif clause_id:
            spans.extend(_clause_span(conn, document_id, str(clause_id)))

    # A deadline node itself is a valid source for the fallback statement that
    # the document has not specified an inaction consequence.
    if not spans and deadline_node_id:
        node = sqlite.get(conn, "graph_nodes", "node_id", deadline_node_id)
        if node and node.get("ref_id"):
            spans.extend(_clause_span(conn, document_id, str(node["ref_id"])))

    # Preserve order while eliminating duplicate citations.
    unique: list[str] = []
    for span in spans:
        if span not in unique:
            unique.append(span)
    return unique


def _clause_span(conn, document_id: str, clause_id: str) -> list[str]:
    row = sqlite.get(conn, "clauses", "clause_id", clause_id)
    if not row or row.get("document_id") != document_id:
        return []
    return [f"{clause_id}:{row.get('char_start') or 0}-{row.get('char_end') or 0}"]


def _deterministic_phrase(nodes: list[dict[str, Any]]) -> str:
    texts = [
        str((node.get("properties") or {}).get("text", "")).strip().rstrip(".")
        for node in nodes
    ]
    texts = [text for text in texts if text]
    if not texts:
        # This is reachable only for malformed graph records that still have a
        # trigger edge.  It does not invent an outcome.
        return "The document states a consequence for not acting, but its text could not be read."
    return "If you do nothing, the document states: " + "; then ".join(texts) + "."


def _summarize_stakes(nodes: list[dict[str, Any]]) -> str:
    text = " ".join(
        str((node.get("properties") or {}).get("text", "")).lower() for node in nodes
    )
    if re.search(r"\b(terminate|termination|forfeit|lose|waiv|evict)\w*\b", text):
        return "loss of rights or termination stated in document"
    if re.search(r"\b(fee|penalty|damages|pay|payment|cost)\b", text):
        return "financial consequence stated in document"
    return "document-stated consequence"


def _option_id() -> str:
    return f"opt_inaction_{uuid.uuid4().hex[:10]}"

