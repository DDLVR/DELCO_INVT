"""Sincroniza órdenes de trabajo con inventario y ficha de cliente."""

from __future__ import annotations

from typing import Any, Dict

from django.db import transaction

ESTADOS_APLICAN_INVENTARIO = frozenset({
    'REALIZADA',
    'REALIZADA_PENDIENTE_COMPROBACION',
    'VALIDADA',
    'FINALIZADA',
})

TIPOS_INSTALAN = frozenset({'INSTALACION', 'CAMBIO', 'CONFIGURACION', 'MANTENCION'})
TIPOS_RETIRAN = frozenset({'RETIRO'})
TIPOS_REPARAN = frozenset({'REPARACION'})


def _helpers():
    from integraciones.reader import (
        _actualizar_equipo_operativo,
        _es_estado_instalado,
        _obtener_estado_por_nombre,
        _obtener_o_crear_ubicacion,
        _registrar_movimiento_equipo,
    )

    return {
        'actualizar': _actualizar_equipo_operativo,
        'es_instalado': _es_estado_instalado,
        'estado': _obtener_estado_por_nombre,
        'ubicacion': _obtener_o_crear_ubicacion,
        'movimiento': _registrar_movimiento_equipo,
    }


def _estado_objetivo_por_tipo(tipo_trabajo: str):
    h = _helpers()
    if tipo_trabajo in TIPOS_INSTALAN:
        return h['estado']('Instalado')
    if tipo_trabajo in TIPOS_RETIRAN:
        return h['estado']('Retirado') or h['estado']('En bodega')
    if tipo_trabajo in TIPOS_REPARAN:
        return h['estado']('En reparación')
    return None


def _registro_stub():
    class _Stub:
        actualizo_equipos = False

    return _Stub()


def sync_equipos_desde_cliente(orden) -> bool:
    """Copia equipos instalados del cliente hacia la OT."""
    if not orden or not orden.cliente_id:
        return False

    from inventario.models import Modem, SimCard

    cliente = orden.cliente
    updates: list[str] = []

    if cliente.medidor_actual_id and orden.medidor_id != cliente.medidor_actual_id:
        orden.medidor_id = cliente.medidor_actual_id
        updates.append('medidor')

    if not orden.modem_id:
        modem = (
            Modem.objects.filter(cliente=cliente, estado_inventario__nombre__icontains='instal')
            .order_by('-id')
            .first()
        )
        if modem:
            orden.modem = modem
            updates.append('modem')

    if not orden.simcard_id:
        sim = (
            SimCard.objects.filter(cliente=cliente, estado_inventario__nombre__icontains='instal')
            .order_by('-id')
            .first()
        )
        if sim:
            orden.simcard = sim
            updates.append('simcard')

    if updates:
        orden.save(update_fields=updates)
        return True
    return False


def asignar_equipos_en_orden(orden, medidor=None, modem=None, simcard=None) -> bool:
    """Asigna equipos concretos a la OT sin tocar inventario."""
    if not orden:
        return False

    updates: list[str] = []
    if medidor and orden.medidor_id != medidor.id:
        orden.medidor = medidor
        updates.append('medidor')
    if modem and orden.modem_id != modem.id:
        orden.modem = modem
        updates.append('modem')
    if simcard and orden.simcard_id != simcard.id:
        orden.simcard = simcard
        updates.append('simcard')

    if updates:
        orden.save(update_fields=updates)
        return True
    return False


def _aplicar_retiro_equipo(equipo, tipo_equipo: str, orden, usuario) -> bool:
    h = _helpers()
    estado_retirado = h['estado']('Retirado') or h['estado']('En bodega')
    if not estado_retirado:
        return False

    cambios: list[str] = []
    if getattr(equipo, 'estado_inventario_id', None) != estado_retirado.id:
        equipo.estado_inventario = estado_retirado
        cambios.append('estado_inventario')

    if getattr(equipo, 'cliente_id', None):
        equipo.cliente = None
        cambios.append('cliente')

    bodega = h['ubicacion']('BODEGA_DELCO', 'Bodega Principal')
    if hasattr(equipo, 'ubicacion_actual_id') and equipo.ubicacion_actual_id != bodega.id:
        equipo.ubicacion_actual = bodega
        cambios.append('ubicacion_actual')

    if not cambios:
        return False

    equipo.save(update_fields=cambios)
    h['movimiento'](
        equipo,
        tipo_equipo,
        f'OT #{orden.pk} — retiro de equipo',
        estado_retirado.nombre,
        origen_sistema='OT',
        tipo_override='RETIRO',
        responsable_override=usuario,
        referencia_ot=str(orden.pk),
    )
    return True


@transaction.atomic
def sync_orden_a_inventario(orden, usuario, estado_destino: str) -> Dict[str, Any]:
    """Refleja en inventario los equipos de la OT al cerrar o validar el trabajo."""
    if estado_destino not in ESTADOS_APLICAN_INVENTARIO:
        return {'aplicado': False, 'motivo': 'estado_sin_sync', 'equipos': 0}

    if not orden.cliente_id:
        return {'aplicado': False, 'motivo': 'sin_cliente', 'equipos': 0}

    h = _helpers()
    registro = _registro_stub()
    cliente = orden.cliente
    observacion = f'OT #{orden.pk} — {orden.get_tipo_trabajo_display()} ({estado_destino})'
    medidor_ref = orden.medidor
    equipos_actualizados = 0
    es_retiro = orden.tipo_trabajo in TIPOS_RETIRAN

    if es_retiro:
        for equipo, tipo in (
            (orden.medidor, 'MEDIDOR'),
            (orden.modem, 'MODEM'),
            (orden.simcard, 'SIM'),
        ):
            if equipo and _aplicar_retiro_equipo(equipo, tipo, orden, usuario):
                equipos_actualizados += 1

        if orden.medidor_id and cliente.medidor_actual_id == orden.medidor_id:
            cliente.medidor_actual = None
            cliente.save(update_fields=['medidor_actual'])

        return {
            'aplicado': equipos_actualizados > 0,
            'motivo': 'ok' if equipos_actualizados else 'sin_cambios',
            'equipos': equipos_actualizados,
        }

    estado_obj = _estado_objetivo_por_tipo(orden.tipo_trabajo)
    if not estado_obj:
        return {'aplicado': False, 'motivo': 'tipo_sin_sync', 'equipos': 0}

    for equipo, tipo in (
        (orden.medidor, 'MEDIDOR'),
        (orden.modem, 'MODEM'),
        (orden.simcard, 'SIM'),
    ):
        if not equipo:
            continue

        kwargs: Dict[str, Any] = {
            'medidor_asociado': medidor_ref if tipo != 'MEDIDOR' else None,
            'registrar_pendiente': None,
            'responsable_movimiento': usuario,
            'referencia_ot': str(orden.pk),
        }

        if tipo == 'MODEM':
            kwargs['ip_dejada'] = getattr(cliente, 'ip', '') or ''
            kwargs['puerto'] = getattr(cliente, 'puerto', '') or ''
        if tipo == 'SIM':
            kwargs['ip_dejada'] = getattr(cliente, 'ip', '') or ''

        if h['actualizar'](
            equipo,
            tipo,
            estado_obj,
            cliente,
            observacion,
            registro,
            **kwargs,
        ):
            equipos_actualizados += 1

    return {
        'aplicado': equipos_actualizados > 0,
        'motivo': 'ok' if equipos_actualizados else 'sin_cambios',
        'equipos': equipos_actualizados,
    }


def sincronizar_orden_completa(orden, usuario, estado_destino: str) -> Dict[str, Any]:
    """Vincula equipos del cliente a la OT y aplica inventario si el estado lo requiere."""
    sync_equipos_desde_cliente(orden)
    return sync_orden_a_inventario(orden, usuario, estado_destino)


def vincular_moreapp_a_orden(
    cliente,
    registro_moreapp=None,
    ruta_carpeta: str = '',
    usuario=None,
    medidor=None,
    modem=None,
    simcard=None,
):
    """Une un registro MoreApp con la OT abierta del cliente y copia equipos procesados."""
    from ordenes_trabajo.utils import vincular_informe_cliente_a_orden

    orden = vincular_informe_cliente_a_orden(
        cliente=cliente,
        registro_moreapp=registro_moreapp,
        ruta_carpeta=ruta_carpeta,
        usuario=usuario,
    )
    if orden:
        asignar_equipos_en_orden(orden, medidor=medidor, modem=modem, simcard=simcard)
        sync_equipos_desde_cliente(orden)
    return orden
