"""LLM providers for the orchestrator (spec §9.3, §19.4).

- StubProvider: deterministic, offline, heuristic-driven. Implements each
  prompt's structured output without network calls so the pipeline and tests
  run anywhere. This is the default.
- OpenAIProvider: activated via env vars (WAYFINDER_LLM_PROVIDER=openai,
  OPENAI_API_KEY, optional OPENAI_BASE_URL / WAYFINDER_MODEL). Service logic
  never touches a vendor SDK directly — only this wrapper does.
"""
from __future__ import annotations

import json
import os
from typing import Any

from app.services import heuristics as hz


def default_provider():
    if os.environ.get("WAYFINDER_LLM_PROVIDER", "stub") == "openai":
        return OpenAIProvider()
    return StubProvider()


class StubProvider:
    model_version = "wayfinder-stub-v1"

    def complete(self, *, prompt_name: str, prompt_text: str, inputs: dict) -> Any:
        handler = getattr(self, f"_do_{_base(prompt_name)}", None)
        if handler is None:
            raise ValueError(f"stub provider has no handler for prompt {prompt_name}")
        return handler(inputs)

    # -- clause_extraction_v1 -------------------------------------------
    def _do_clause_extraction(self, i: dict) -> dict:
        text: str = i["clause_text"]
        ctype, conf = hz.classify_clause(text)
        dl = hz.extract_deadline(text)
        obligations = []
        if dl and i.get("role_hint"):
            obligations.append({
                "actor": i["role_hint"],
                "action": hz.detect_obligation_action(text) or "act",
                "deadline_relative": dl[0],
                "deadline_absolute": i.get("deadline_absolute"),
                "condition": "stated in clause",
            })
        risks = []
        cons = hz.consequence_sentences(text)
        if dl and cons:
            risks.append({
                "type": "deadline_pressure",
                "description": "Short, hard deadline with a stated default-if-missed consequence.",
                "severity": "high",
            })
        elif dl:
            risks.append({
                "type": "deadline_pressure",
                "description": "A deadline applies; the clause does not state a consequence for missing it.",
                "severity": "medium",
            })
        if ctype in ("indemnity_trigger", "liability"):
            risks.append({"type": "financial_exposure",
                          "description": "This clause may create financial exposure for you.",
                          "severity": "medium"})
        plain = _plain_rewrite(text, dl, cons)
        return {
            "clause_id": i["clause_id"],
            "document_id": i["document_id"],
            "clause_title": i.get("clause_title") or hz.title_for(ctype),
            "clause_type": ctype,
            "page": i.get("page"),
            "char_span": i.get("char_span", [0, len(text)]),
            "original_text": text,
            "plain_language": plain,
            "obligations": obligations,
            "rights": [],
            "risks": risks,
            "missing_elements": hz.missing_elements_for(
                i.get("document_type", ""), ctype, text),
            "related_clause_ids": [],
            "feeds_decision_id": None,
            "extraction_confidence": conf,
        }

    # -- decision_extraction_v1 ------------------------------------------
    def _do_decision_extraction(self, i: dict) -> dict:
        clauses = i["triggering_clauses"]
        primary = clauses[0]
        ctype = primary.get("clause_type", "general")
        deadline = i.get("deadline")
        action = hz.detect_obligation_action(primary.get("original_text", ""))
        verb = hz.summarize_deadline_action(ctype, action)
        title = verb + (" or accept the default outcome" if deadline else "")
        options = [{
            "option_id": "opt_a",
            "action": verb + " using the guided template",
            "consequence": (
                "This may preserve the rights this clause gives you, because you "
                "acted within the stated timeframe. Consider keeping proof of sending."
            ),
            "effort": "low",
            "cost": "none (self-serve template available)",
            "is_default_if_inaction": False,
            "source_spans": [f"{c['clause_id']}:0-{len(c.get('original_text', ''))}" for c in clauses],
        }]
        if len(clauses) > 1 or ctype in ("notice_period", "termination", "payment_dispute"):
            options.append({
                "option_id": "opt_b",
                "action": "Contact the other party directly to negotiate",
                "consequence": (
                    "This may resolve the matter informally, but it appears to create "
                    "no binding record if the other party later disputes what was agreed."
                ),
                "effort": "medium",
                "cost": "none",
                "is_default_if_inaction": False,
                "source_spans": [f"{clauses[0]['clause_id']}:0-{len(clauses[0].get('original_text', ''))}"],
            })
        # NOTE: the stub deliberately omits the inaction branch — §11.3's
        # ensure_inaction_option backfills it deterministically, which is the
        # guaranteed (non-LLM) enforcement path for the §7.3 invariant.
        return {
            "decision_id": i["decision_id"],
            "document_id": i["document_id"],
            "title": title,
            "triggering_clause_ids": [c["clause_id"] for c in clauses],
            "deadline": deadline,
            "days_remaining": i.get("days_remaining"),
            "options": options,
            "confidence": "high" if deadline else "medium",
            "source_spans": [f"{c['clause_id']}:0-{len(c.get('original_text', ''))}" for c in clauses],
        }

    def _do_decision_extraction_repair(self, i: dict) -> dict:
        return i["draft"]  # deterministic repair is handled by ensure_inaction_option

    # -- inaction_phrasing_v1 --------------------------------------------
    def _do_inaction_phrasing(self, i: dict) -> str:
        path = i["consequence_path"]
        steps = []
        for node in path:
            if node.get("node_type") == "penalty":
                steps.append(node.get("properties", {}).get("text", "a stated penalty"))
        if not steps:
            return (
                "If you do nothing, the consequences stated in the document "
                "may apply, but the exact chain could not be determined."
            )
        chain = "; then ".join(s.rstrip(".") for s in steps)
        return (
            f"If you do nothing, the document says this may happen: {chain}. "
            "This appears to be the default outcome stated in the document itself."
        )

    # -- artifact_generation_v1 -------------------------------------------
    def _do_artifact_generation(self, i: dict) -> dict:
        template: str = i["template_structure"]
        facts: dict = i.get("extracted_facts", {})
        filled = template
        remaining = []
        for field in i.get("template_fields", []):
            token = f"[{field}]"
            value = facts.get(field)
            if value:
                filled = filled.replace(token, str(value))
            elif token in filled:
                remaining.append(field)
        return {"content": filled, "fields_to_fill": remaining}

    # -- qa_grounded_v1 ----------------------------------------------------
    def _do_qa_grounded(self, i: dict) -> dict:
        clauses = i.get("retrieved_clauses", [])
        if not clauses:
            return {
                "answer": "The uploaded document does not appear to contain enough information to answer this question.",
                "citations": [], "confidence": "low", "linked_decision_id": None,
            }
        top = clauses[0]
        linked = (i.get("linked_decisions") or {})
        answer = top.get("plain_language") or top.get("original_text", "")
        return {
            "answer": answer,
            "citations": [
                {"clause_id": c["clause_id"],
                 "reference": (c.get("original_text", "")[:120] + "…")}
                for c in clauses[:3]
            ],
            "confidence": "medium" if len(clauses) > 1 else "low",
            "linked_decision_id": linked.get(top.get("feeds_decision_id")),
        }


def _base(prompt_name: str) -> str:
    # clause_extraction_v1 -> clause_extraction
    return prompt_name.rsplit("_v", 1)[0]


def _plain_rewrite(text: str, dl, cons) -> str:
    parts = []
    if dl:
        parts.append(f"You have {dl[0]} to act under this clause.")
    if cons:
        parts.append("If you don't: " + cons[0].rstrip(".") + ".")
    if not parts:
        first = text.strip().split(". ")[0].strip()
        parts.append("In plain terms: " + first.rstrip(".") + ".")
    return " ".join(parts)


class OpenAIProvider:
    def __init__(self):
        self.model_version = os.environ.get("WAYFINDER_MODEL", "gpt-4o-mini")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def complete(self, *, prompt_name: str, prompt_text: str, inputs: dict) -> Any:
        import httpx

        body = {
            "model": self.model_version,
            "messages": [
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": json.dumps(inputs, default=str)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
