"""Schema validation layer — spec §9.3. Pydantic models ARE the validators."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from app.models import Clause, DecisionPoint


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    value: object = None


def validate_decision(payload: dict) -> ValidationResult:
    """Validate a decision draft against §7.3, including the inaction-option
    invariant enforced by the DecisionPoint model validator."""
    try:
        return ValidationResult(ok=True, value=DecisionPoint(**payload))
    except ValidationError as exc:
        return ValidationResult(ok=False, errors=[str(e) for e in exc.errors()])


def validate_clause(payload: dict) -> ValidationResult:
    try:
        return ValidationResult(ok=True, value=Clause(**payload))
    except ValidationError as exc:
        return ValidationResult(ok=False, errors=[str(e) for e in exc.errors()])
