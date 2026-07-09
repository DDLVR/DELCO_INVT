"""Audit skeleton for traceability (requirement point 12).

This module is intentionally minimal and ready to be integrated
when the final audit model is confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
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
    """Persist event in DB and mirror to logger as technical backup."""

    def _serialize(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)

    try:
        from web.models import AuditLog

        AuditLog.objects.create(
            actor_id=event.actor_id,
            action=(event.action or '')[:80],
            entity=(event.entity or '')[:120],
            entity_id=(event.entity_id or '')[:120],
            field_name=(event.field_name or '')[:120] if event.field_name else None,
            old_value=_serialize(event.old_value),
            new_value=_serialize(event.new_value),
            reason=event.reason,
        )
    except Exception:
        # No romper flujo operativo por error de auditoría.
        logger.exception('AUDIT_DB_ERROR action=%s entity=%s entity_id=%s', event.action, event.entity, event.entity_id)

    logger.info(
        'AUDIT actor=%s action=%s entity=%s entity_id=%s field=%s old=%r new=%r reason=%s',
        event.actor_id,
        event.action,
        event.entity,
        event.entity_id,
        event.field_name,
        event.old_value,
        event.new_value,
        event.reason,
    )
