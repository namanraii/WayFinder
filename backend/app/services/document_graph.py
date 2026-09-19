"""Document Graph Service — spec §8, §9.4.

Deterministic, rule-based: builds graph nodes/edges from Clause rows into the
Postgres-adjacency-equivalent tables (graph_nodes / graph_edges). No LLM call
in this service. Storage is SQLite locally with identical table shapes.
"""
from __future__ import annotations

import uuid

from app.db import sqlite
from app.services import heuristics as hz

# Node types: document, party, clause, obligation, right, deadline,
# payment_term, penalty, decision_point.
# Edge types: imposes, grants, triggers, resolves, references,
# conflicts_with, feeds.


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _eid() -> str:
    return f"edge_{uuid.uuid4().hex[:8]}"


def build(conn, document_id: str, clauses: list[dict]) -> None:
    doc_node = _nid("docnode")
    sqlite.insert(conn, "graph_nodes", {
        "node_id": doc_node, "document_id": document_id,
        "node_type": "document", "ref_id": document_id, "properties": {},
    })

    deadline_nodes: list[str] = []
    penalty_nodes: list[str] = []

    for clause in clauses:
        c_node = _nid("cnode")
        sqlite.insert(conn, "graph_nodes", {
            "node_id": c_node, "document_id": document_id,
            "node_type": "clause", "ref_id": clause["clause_id"],
            "properties": {"clause_type": clause["clause_type"],
                           "title": clause.get("clause_title")},
        })

        for ob in clause.get("obligations") or []:
            o_node = _nid("onode")
            sqlite.insert(conn, "graph_nodes", {
                "node_id": o_node, "document_id": document_id,
                "node_type": "obligation", "ref_id": clause["clause_id"],
                "properties": ob,
            })
            _edge(conn, document_id, c_node, o_node, "imposes")
            if ob.get("deadline_absolute") or ob.get("deadline_relative"):
                d_node = _nid("dnode")
                sqlite.insert(conn, "graph_nodes", {
                    "node_id": d_node, "document_id": document_id,
                    "node_type": "deadline", "ref_id": clause["clause_id"],
                    "properties": {
                        "deadline_absolute": ob.get("deadline_absolute"),
                        "deadline_relative": ob.get("deadline_relative"),
                    },
                })
                _edge(conn, document_id, o_node, d_node, "resolves")
                deadline_nodes.append(d_node)

        cons = hz.consequence_sentences(clause.get("original_text", ""))
        for sent in cons:
            p_node = _nid("pnode")
            sqlite.insert(conn, "graph_nodes", {
                "node_id": p_node, "document_id": document_id,
                "node_type": "penalty", "ref_id": clause["clause_id"],
                "properties": {"text": sent,
                               "source_clause_id": clause["clause_id"],
                               "char_span": clause.get("char_span")},
            })
            penalty_nodes.append(p_node)

    # 'triggers' edges: each deadline in a clause triggers the penalties
    # stated in the SAME clause (consequence sentences are co-located).
    for clause in clauses:
        c_dls = _nodes_for(conn, document_id, "deadline", clause["clause_id"])
        c_pens = _nodes_for(conn, document_id, "penalty", clause["clause_id"])
        for d in c_dls:
            for p in c_pens:
                _edge(conn, document_id, d["node_id"], p["node_id"], "triggers")

    # 'references' edges between clauses that share decision-bearing type
    # signals (e.g. notice_period <-> termination) for candidate merging.
    for i, a in enumerate(clauses):
        for b in clauses[i + 1:]:
            if {a["clause_type"], b["clause_type"]} <= hz.DECISION_BEARING_TYPES:
                a_node = _node_of_clause(conn, document_id, a["clause_id"])
                b_node = _node_of_clause(conn, document_id, b["clause_id"])
                if a_node and b_node:
                    _edge(conn, document_id, a_node["node_id"], b_node["node_id"], "references")

    sqlite.update(conn, "documents", "document_id", document_id,
                  {"processing_status": "graphed"})


def traverse_triggers(conn, document_id: str, deadline_node_id: str, max_hops: int = 3) -> list[dict]:
    """Deterministic traversal from a Deadline node along 'triggers' edges to
    penalty nodes (spec §12). Returns the ordered list of traversed nodes."""
    seen: set[str] = set()
    path: list[dict] = []
    frontier = [deadline_node_id]
    start = sqlite.get(conn, "graph_nodes", "node_id", deadline_node_id)
    if start:
        path.append(start)
    for _ in range(max_hops):
        nxt = []
        for node_id in frontier:
            edges = sqlite.query(
                conn,
                "SELECT * FROM graph_edges WHERE from_node_id = ? AND edge_type = 'triggers'",
                (node_id,),
            )
            for e in edges:
                if e["to_node_id"] in seen:
                    continue
                seen.add(e["to_node_id"])
                node = sqlite.get(conn, "graph_nodes", "node_id", e["to_node_id"])
                if node:
                    path.append(node)
                    nxt.append(e["to_node_id"])
        if not nxt:
            break
        frontier = nxt
    return path


def _edge(conn, document_id, from_id, to_id, edge_type) -> None:
    sqlite.insert(conn, "graph_edges", {
        "edge_id": _eid(), "document_id": document_id,
        "from_node_id": from_id, "to_node_id": to_id, "edge_type": edge_type,
    })


def _nodes_for(conn, document_id, node_type, ref_id) -> list[dict]:
    return sqlite.query(
        conn,
        "SELECT * FROM graph_nodes WHERE document_id = ? AND node_type = ? AND ref_id = ?",
        (document_id, node_type, ref_id),
    )


def _node_of_clause(conn, document_id, clause_id) -> dict | None:
    rows = _nodes_for(conn, document_id, "clause", clause_id)
    return rows[0] if rows else None
