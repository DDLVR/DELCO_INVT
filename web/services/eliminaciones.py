"""Soft-delete unificado con snapshot inmutable en movimientos.

Al eliminar inventario, OT, reportes MoreApp o clientes:
- el registro queda oculto en su listado original (soft-delete)
- se crea un MovimientoInventario tipo ELIMINACION con snapshot JSON
  (sin archivos binarios) visible en /movimientos/
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

ENTIDAD_MEDIDOR = 'MEDIDOR'
ENTIDAD_SIM = 'SIM'
ENTIDAD_MODEM = 'MODEM'
ENTIDAD_CLIENTE = 'CLIENTE'
ENTIDAD_ORDEN = 'ORDEN_TRABAJO'
ENTIDAD_MOREAPP = 'MOREAPP'

ENTIDAD_CHOICES = [
    (ENTIDAD_MEDIDOR, 'Medidor'),
    (ENTIDAD_SIM, 'SIM Card'),
    (ENTIDAD_MODEM, 'Módem'),
    (ENTIDAD_CLIENTE, 'Cliente'),
    (ENTIDAD_ORDEN, 'Orden de trabajo'),
    (ENTIDAD_MOREAPP, 'Reporte MoreApp'),
]


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, models.Model):
        return {'id': value.pk, 'repr': str(value)}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    return str(value)


def snapshot_instance(instance: models.Model) -> Dict[str, Any]:
    """Serializa campos del modelo excluyendo FileField/ImageField."""
    data = {
        '_modelo': instance.__class__.__name__,
        '_pk': instance.pk,
    }
    for field in instance._meta.concrete_fields:
        if isinstance(field, (models.FileField, models.ImageField)):
            # Solo referencia textual del nombre, nunca el binario.
            raw = getattr(instance, field.name)
            data[field.name] = str(raw) if raw else ''
            continue
        try:
            data[field.name] = _serialize_value(getattr(instance, field.name))
        except Exception:
            data[field.name] = None
    return data


def ubicacion_sistema_eliminaciones():
    from inventario.models import Ubicacion

    ubicacion = Ubicacion.objects.filter(nombre='Sistema / Eliminaciones').first()
    if ubicacion:
        return ubicacion
    return Ubicacion.objects.create(
        tipo='BODEGA_DELCO',
        nombre='Sistema / Eliminaciones',
        direccion='Registro histórico de eliminaciones',
    )


def _identificador_para(entidad: str, instance: models.Model) -> str:
    if entidad == ENTIDAD_MEDIDOR:
        return getattr(instance, 'serie', '') or str(instance.pk)
    if entidad == ENTIDAD_SIM:
        return (
            getattr(instance, 'imei', None)
            or getattr(instance, 'abonado', None)
            or str(instance.pk)
        )
    if entidad == ENTIDAD_MODEM:
        return getattr(instance, 'serie', '') or str(instance.pk)
    if entidad == ENTIDAD_CLIENTE:
        return getattr(instance, 'numero_cliente', '') or str(instance.pk)
    if entidad == ENTIDAD_ORDEN:
        return f'OT#{instance.pk}'
    if entidad == ENTIDAD_MOREAPP:
        return getattr(instance, 'moreapp_submission_id', '') or str(instance.pk)
    return str(instance.pk)


def _marcar_soft_delete(instance: models.Model, usuario, entidad: str) -> None:
    """Aplica soft-delete según el tipo de entidad."""
    ahora = timezone.now()
    if entidad == ENTIDAD_CLIENTE:
        instance.activo = False
        update_fields = ['activo']
        if hasattr(instance, 'fecha_eliminacion'):
            instance.fecha_eliminacion = ahora
            update_fields.append('fecha_eliminacion')
        if hasattr(instance, 'eliminado_por_id'):
            instance.eliminado_por = usuario
            update_fields.append('eliminado_por')
        instance.save(update_fields=update_fields)
        return

    instance.eliminado = True
    update_fields = ['eliminado']
    if hasattr(instance, 'fecha_eliminacion'):
        instance.fecha_eliminacion = ahora
        update_fields.append('fecha_eliminacion')
    if hasattr(instance, 'eliminado_por_id'):
        instance.eliminado_por = usuario
        update_fields.append('eliminado_por')
    instance.save(update_fields=update_fields)


def _ya_eliminado(instance: models.Model, entidad: str) -> bool:
    if entidad == ENTIDAD_CLIENTE:
        return not bool(getattr(instance, 'activo', True))
    return bool(getattr(instance, 'eliminado', False))


@transaction.atomic
def registrar_eliminacion(
    entidad: str,
    instance: models.Model,
    usuario,
    motivo: str = '',
    crear_item_inventario: bool = False,
) -> Tuple[Any, bool]:
    """Soft-delete + movimiento ELIMINACION con snapshot.

    Returns:
        (movimiento, creado) — creado=False si ya estaba eliminado.
    """
    from inventario.models import MovimientoInventario, MovimientoItem

    if _ya_eliminado(instance, entidad):
        return None, False

    snapshot = snapshot_instance(instance)
    if motivo:
        snapshot['_motivo_eliminacion'] = motivo.strip()

    identificador = _identificador_para(entidad, instance)
    ubicacion = ubicacion_sistema_eliminaciones()
    if entidad in (ENTIDAD_MEDIDOR, ENTIDAD_SIM, ENTIDAD_MODEM):
        ubicacion_equipo = getattr(instance, 'ubicacion_actual', None)
        if ubicacion_equipo is not None:
            ubicacion = ubicacion_equipo

    responsable_nombre = getattr(usuario, 'nombre_interno', None) or str(usuario)
    observacion_parts = [
        f'Eliminación de {entidad} {identificador}',
        f'por {responsable_nombre}',
    ]
    if motivo and motivo.strip():
        observacion_parts.append(f'Motivo: {motivo.strip()}')

    movimiento = MovimientoInventario.objects.create(
        tipo='ELIMINACION',
        origen_sistema='MANUAL',
        origen=ubicacion,
        destino=ubicacion,
        responsable=usuario,
        observacion=' | '.join(observacion_parts),
        referencia_ot=f'OT#{instance.pk}' if entidad == ENTIDAD_ORDEN else '',
        entidad_eliminada=entidad,
        entidad_id=str(instance.pk),
        identificador_entidad=str(identificador)[:255],
        datos_eliminacion=snapshot,
    )

    if crear_item_inventario and entidad in (ENTIDAD_MEDIDOR, ENTIDAD_SIM, ENTIDAD_MODEM):
        item_kwargs = {
            'movimiento': movimiento,
            'tipo_equipo': entidad,
            'cantidad': 1,
        }
        if entidad == ENTIDAD_MEDIDOR:
            item_kwargs['medidor'] = instance
        elif entidad == ENTIDAD_SIM:
            item_kwargs['simcard'] = instance
        else:
            item_kwargs['modem'] = instance
        MovimientoItem.objects.create(**item_kwargs)

    _marcar_soft_delete(instance, usuario, entidad)

    try:
        from web.services.audit import AuditEvent, register_audit_event

        register_audit_event(
            AuditEvent(
                actor_id=getattr(usuario, 'id', None),
                action='SOFT_DELETE',
                entity=entidad,
                entity_id=str(instance.pk),
                field_name='eliminado' if entidad != ENTIDAD_CLIENTE else 'activo',
                old_value=False if entidad != ENTIDAD_CLIENTE else True,
                new_value=True if entidad != ENTIDAD_CLIENTE else False,
                reason=motivo.strip() or f'Eliminación lógica de {entidad}',
            )
        )
    except Exception:
        logger.exception('No se pudo registrar audit de eliminación %s #%s', entidad, instance.pk)

    return movimiento, True
