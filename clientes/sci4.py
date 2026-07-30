"""Utilidades de sincronización manual con SCi4 (sin API externa)."""
from __future__ import annotations

from typing import Any, Mapping

from web.services.audit import AuditEvent, register_audit_event

# Campos cuya modificación exige revisión / actualización en SCi4 (base comercial externa)
CAMPOS_CRITICOS_SCI4 = (
    'meter_serial_n_1',
    'modem',
    'ip',
    'puerto',
    'medidor_actual_id',
    'sim_iccid',
    'sim_operador',
    'sim_abonado',
)

# Tipos de OT que implican cambio de equipo → alerta para actualizar base comercial
TIPOS_OT_ALERTA_SCI4 = frozenset({
    'CAMBIO',
    'INSTALACION',
    'RETIRO',
})

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
    Si cambió medidor/módem/IP/puerto/SIM, marca SCi4 pendiente.
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


def _snapshot_criticos(cliente) -> dict[str, Any]:
    return {campo: getattr(cliente, campo, None) for campo in CAMPOS_CRITICOS_SCI4}


def actualizar_ficha_cliente_desde_ot(orden, *, es_retiro: bool = False) -> list[str]:
    """
    Refleja en la ficha del cliente los equipos de la OT (nuestra plataforma).
    Retorna lista de campos de ficha que cambiaron.
    """
    cliente = getattr(orden, 'cliente', None)
    if not cliente:
        return []

    before = _snapshot_criticos(cliente)
    updates: list[str] = []

    if es_retiro:
        if orden.medidor_id and cliente.medidor_actual_id == orden.medidor_id:
            cliente.medidor_actual = None
            updates.append('medidor_actual')
        if orden.medidor and _norm(cliente.meter_serial_n_1) == _norm(orden.medidor.serie):
            cliente.meter_serial_n_1 = ''
            updates.append('meter_serial_n_1')
        if orden.modem and _norm(cliente.modem) == _norm(orden.modem.serie):
            cliente.modem = ''
            updates.append('modem')
        if orden.simcard:
            sim_id = _norm(getattr(orden.simcard, 'imei', None) or getattr(orden.simcard, 'serie_plastico', None))
            if sim_id and _norm(cliente.sim_iccid) == sim_id:
                cliente.sim_iccid = ''
                updates.append('sim_iccid')
    else:
        if orden.medidor_id:
            if cliente.medidor_actual_id != orden.medidor_id:
                # No forzar OneToOne si está ocupado: medidor_actual lo maneja sync inventario
                pass
            serie = getattr(orden.medidor, 'serie', None) or ''
            if serie and _norm(cliente.meter_serial_n_1) != _norm(serie):
                cliente.meter_serial_n_1 = serie
                updates.append('meter_serial_n_1')
            marca = getattr(orden.medidor, 'marca', None) or ''
            if marca and _norm(getattr(cliente, 'meter_manufacturer_id', None)) != _norm(marca):
                cliente.meter_manufacturer_id = marca
                updates.append('meter_manufacturer_id')
        if orden.modem_id:
            serie_modem = getattr(orden.modem, 'serie', None) or ''
            if serie_modem and _norm(cliente.modem) != _norm(serie_modem):
                cliente.modem = serie_modem
                updates.append('modem')
            ip_modem = getattr(orden.modem, 'ip', None) or ''
            if ip_modem and _norm(cliente.ip) != _norm(ip_modem):
                cliente.ip = ip_modem
                updates.append('ip')
            puerto_modem = getattr(orden.modem, 'puerto', None) or ''
            if puerto_modem and _norm(cliente.puerto) != _norm(puerto_modem):
                cliente.puerto = puerto_modem
                updates.append('puerto')
        if orden.simcard_id:
            sim = orden.simcard
            sim_id = _norm(getattr(sim, 'imei', None) or getattr(sim, 'serie_plastico', None))
            if sim_id and _norm(cliente.sim_iccid) != sim_id:
                cliente.sim_iccid = sim_id
                updates.append('sim_iccid')
            operador = getattr(sim, 'operador', None) or ''
            if operador and _norm(cliente.sim_operador) != _norm(operador):
                cliente.sim_operador = operador
                updates.append('sim_operador')
            abonado = getattr(sim, 'numero_abonado', None) or getattr(sim, 'abonado', None) or ''
            if abonado and _norm(cliente.sim_abonado) != _norm(abonado):
                cliente.sim_abonado = abonado
                updates.append('sim_abonado')
            ip_sim = getattr(sim, 'direccion_ip', None) or getattr(sim, 'ip_fija', None) or ''
            if ip_sim and _norm(cliente.ip) != _norm(ip_sim):
                cliente.ip = ip_sim
                updates.append('ip')

    if updates:
        # Quitar duplicados preservando orden
        updates = list(dict.fromkeys(updates))
        # medidor_actual se guarda aparte si cambió en retiro
        save_fields = [f for f in updates if f != 'medidor_actual']
        if 'medidor_actual' in updates:
            save_fields.append('medidor_actual')
        save_fields.append('fecha_actualizacion')
        cliente.save(update_fields=list(dict.fromkeys(save_fields)))

    after = _snapshot_criticos(cliente)
    return hubo_cambio_critico_sci4(before, after) or [
        f for f in updates if f in CAMPOS_CRITICOS_SCI4 or f == 'meter_manufacturer_id'
    ]


def alertar_sci4_por_orden_equipos(
    orden,
    *,
    actor_id: int | None = None,
    es_retiro: bool = False,
) -> bool:
    """
    Tras ejecutar/cerrar una OT de instalación/cambio/retiro:
    1) Actualiza ficha del cliente en nuestra plataforma.
    2) Marca Pendiente SCi4 para que administración actualice la base comercial externa.
    """
    if not orden or not orden.cliente_id:
        return False
    if (orden.tipo_trabajo or '') not in TIPOS_OT_ALERTA_SCI4:
        return False
    if not (orden.medidor_id or orden.modem_id or orden.simcard_id):
        return False

    cliente = orden.cliente
    campos = actualizar_ficha_cliente_desde_ot(orden, es_retiro=es_retiro)
    equipos = []
    if orden.medidor_id:
        equipos.append(f'medidor {getattr(orden.medidor, "serie", orden.medidor_id)}')
    if orden.modem_id:
        equipos.append(f'módem {getattr(orden.modem, "serie", orden.modem_id)}')
    if orden.simcard_id:
        equipos.append(f'SIM {getattr(orden.simcard, "imei", orden.simcard_id)}')

    reason = (
        f'OT #{orden.pk} ({orden.get_tipo_trabajo_display()}) — '
        f'cambio de equipo pendiente de actualizar en base comercial'
    )
    if equipos:
        reason = f'{reason}: {", ".join(equipos)}'

    return marcar_sci4_pendiente(
        cliente,
        actor_id=actor_id,
        reason=reason,
        campos=campos or None,
    )
