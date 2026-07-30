"""Utilidades de sincronización manual con SCi4 (sin API externa)."""
from __future__ import annotations

from typing import Any, Mapping

from web.services.audit import AuditEvent, register_audit_event

# Campos cuya modificación exige revisión / actualización en SCi4
CAMPOS_CRITICOS_SCI4 = (
    'meter_serial_n_1',
    'modem',
    'ip',
    'puerto',
    'medidor_actual_id',
)

_NORM_EMPTY = {None, '', 'null', 'nulo', 'none', '-'}


def _norm(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if text.lower() in _NORM_EMPTY:
        return ''
    return text


def hubo_cambio_critico_sci4(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Devuelve nombres de campos críticos que cambiaron."""
    cambiados = []
    for campo in CAMPOS_CRITICOS_SCI4:
        if campo not in before and campo not in after:
            continue
        if _norm(before.get(campo)) != _norm(after.get(campo)):
            cambiados.append(campo)
    return cambiados


def marcar_sci4_pendiente(
    cliente,
    *,
    actor_id: int | None = None,
    reason: str = 'Cambio de dato crítico pendiente de sincronizar en SCi4',
    campos: list[str] | None = None,
) -> bool:
    """
    Marca estado_sci4=PENDIENTE si aún no lo está.
    Retorna True si hubo cambio de estado.
    """
    anterior = cliente.estado_sci4 or 'SIN_REGISTRO'
    if anterior == 'PENDIENTE':
        return False

    cliente.estado_sci4 = 'PENDIENTE'
    cliente.save(update_fields=['estado_sci4', 'fecha_actualizacion'])

    detalle = reason
    if campos:
        detalle = f'{reason} ({", ".join(campos)})'

    register_audit_event(
        AuditEvent(
            actor_id=actor_id,
            action='CLIENT_UPDATE',
            entity='Cliente',
            entity_id=str(cliente.id),
            field_name='estado_sci4',
            old_value=anterior,
            new_value='PENDIENTE',
            reason=detalle,
        )
    )
    return True


def marcar_sci4_actualizado(
    cliente,
    *,
    actor_id: int | None = None,
    reason: str = 'Validación externa en SCi4 confirmada',
) -> bool:
    """Marca estado_sci4=ACTUALIZADO tras revisión manual en SCi4."""
    anterior = cliente.estado_sci4 or 'SIN_REGISTRO'
    if anterior == 'ACTUALIZADO':
        return False

    cliente.estado_sci4 = 'ACTUALIZADO'
    cliente.save(update_fields=['estado_sci4', 'fecha_actualizacion'])

    register_audit_event(
        AuditEvent(
            actor_id=actor_id,
            action='CLIENT_UPDATE',
            entity='Cliente',
            entity_id=str(cliente.id),
            field_name='estado_sci4',
            old_value=anterior,
            new_value='ACTUALIZADO',
            reason=reason,
        )
    )
    return True


def aplicar_pendiente_si_cambio_critico(
    cliente,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    actor_id: int | None = None,
) -> tuple[bool, list[str]]:
    """
    Si cambió medidor/módem/IP/puerto, marca SCi4 pendiente.
    Retorna (marcado, campos_cambiados).
    """
    campos = hubo_cambio_critico_sci4(before, after)
    if not campos:
        return False, []
    marcado = marcar_sci4_pendiente(
        cliente,
        actor_id=actor_id,
        campos=campos,
    )
    return marcado, campos
