"""Auditoría persistente (PDF punto 12)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging


logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    """Estructura de evento de auditoría."""

    actor_id: int | None
    action: str
    entity: str
    entity_id: str
    field_name: str | None = None
    old_value: Any = None
    new_value: Any = None
    reason: str | None = None


def _serialize_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def register_audit_event(event: AuditEvent) -> None:
    """Persiste el evento en BD y deja traza en log."""
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

    try:
        from web.models import AuditoriaRegistro

        AuditoriaRegistro.objects.create(
            actor_id=event.actor_id,
            action=event.action,
            entity=event.entity,
            entity_id=str(event.entity_id),
            field_name=event.field_name,
            old_value=_serialize_value(event.old_value),
            new_value=_serialize_value(event.new_value),
            reason=event.reason,
        )
    except Exception:
        logger.exception('No se pudo persistir evento de auditoría')
