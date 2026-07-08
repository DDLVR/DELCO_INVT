"""Audit skeleton for traceability (requirement point 12).

This module is intentionally minimal and ready to be integrated
when the final audit model is confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging


logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    """Simple audit event structure."""

    actor_id: int | None
    action: str
    entity: str
    entity_id: str
    field_name: str | None = None
    old_value: Any = None
    new_value: Any = None
    reason: str | None = None


def register_audit_event(event: AuditEvent) -> None:
    """Placeholder entry point for audit persistence.

    Replace this with DB persistence once the audit model is finalized.
    """
    logger.info(
        "AUDIT actor=%s action=%s entity=%s entity_id=%s field=%s old=%r new=%r reason=%s",
        event.actor_id,
        event.action,
        event.entity,
        event.entity_id,
        event.field_name,
        event.old_value,
        event.new_value,
        event.reason,
    )
