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


ACCIONES_ACTIVIDAD = {
    'CREADA': 'Creada',
    'MODIFICADA': 'Modificada',
    'ELIMINADA': 'Eliminada',
    'COMPLETADA': 'Completada',
    'ERROR_ENVIO': 'Error de envío',
}


def upsert_activity_audit(
    *,
    actor_id,
    entity: str,
    entity_id: str,
    accion: str,
    snapshot: dict,
    extra: dict | None = None,
) -> None:
    """Un registro por entidad: se actualiza con la actividad nueva, no se duplica la fila."""
    from django.utils import timezone

    from web.models import AuditLog

    codigo = str(accion or 'MODIFICADA').upper()
    action = ('TAREA_%s' % codigo)[:80]
    etiqueta = ACCIONES_ACTIVIDAD.get(codigo, codigo.title())
    evento = {
        'cuando': timezone.now().isoformat(),
        'accion': codigo,
        'actor_id': actor_id,
        'detalle': extra or {},
        'datos': snapshot or {},
    }
    try:
        log = (
            AuditLog.objects.filter(entity=entity, entity_id=str(entity_id))
            .order_by('id')
            .first()
        )
        if log is None:
            register_audit_event(
                AuditEvent(
                    actor_id=actor_id,
                    action=action,
                    entity=entity,
                    entity_id=str(entity_id),
                    field_name='actividad',
                    old_value=None,
                    new_value={'actual': snapshot, 'actividad': [evento]},
                    reason=etiqueta,
                )
            )
            return
        previo = None
        actividad = []
        try:
            parsed = json.loads(log.new_value or '{}')
            if isinstance(parsed, dict):
                previo = parsed.get('actual')
                if isinstance(parsed.get('actividad'), list):
                    actividad = list(parsed['actividad'])
        except Exception:
            previo = log.new_value
        actividad.append(evento)
        log.actor_id = actor_id
        log.action = action
        log.field_name = 'actividad'
        log.old_value = json.dumps(previo, ensure_ascii=False, default=str) if previo is not None else None
        log.new_value = json.dumps(
            {'actual': snapshot, 'actividad': actividad},
            ensure_ascii=False,
            default=str,
        )
        log.reason = ' > '.join(
            ACCIONES_ACTIVIDAD.get(str(item.get('accion') or ''), str(item.get('accion') or ''))
            for item in actividad
        )[:500]
        log.save()
    except Exception:
        logger.exception(
            'AUDIT_UPSERT_ERROR entity=%s entity_id=%s accion=%s',
            entity,
            entity_id,
            accion,
        )


def audit_field_changes(
    *,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: str,
    before: dict,
    after: dict,
    fields: list[str] | None = None,
    reason: str | None = None,
) -> None:
    """Register one audit row per changed field (PDF punto 12)."""
    tracked = fields or list(before.keys())
    for field_name in tracked:
        old_value = before.get(field_name)
        new_value = after.get(field_name)
        if old_value == new_value:
            continue
        register_audit_event(
            AuditEvent(
                actor_id=actor_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
            )
        )
