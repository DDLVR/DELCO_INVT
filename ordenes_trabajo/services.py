"""Work-order service skeleton.

Base helpers to implement requirement point 5 validations and workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List


@dataclass
class OTValidationResult:
    """Validation result for OT checks."""

    has_blocking_error: bool
    warnings: List[str]
    errors: List[str]


def validate_ot_duplicate(open_ot_exists: bool, same_requirement_exists: bool) -> OTValidationResult:
    """Validate duplicate OT conditions."""
    errors: List[str] = []
    warnings: List[str] = []

    if open_ot_exists:
        errors.append("Ya existe una OT abierta para este cliente.")
    if same_requirement_exists:
        warnings.append("Ya existe una OT con requerimiento similar.")

    return OTValidationResult(has_blocking_error=bool(errors), warnings=warnings, errors=errors)


def should_flag_reincidence(visits_last_6_months: int, today: date | None = None) -> bool:
    """Return true when client has more than two visits in the last 6 months."""
    _ = today or date.today()
    return visits_last_6_months > 2


def six_month_window_start(today: date | None = None) -> date:
    """Helper to compute a practical 6-month lookback window."""
    base = today or date.today()
    return base - timedelta(days=183)
