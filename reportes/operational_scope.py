"""Alcance de datos para reportes operativos (excluye fichas solo importadas)."""

from __future__ import annotations

from typing import Iterable, Set

from django.db.models import Q, QuerySet

from clientes.models import Cliente
from ordenes_trabajo.models import IntegracionMoreApp, OrdenTrabajo

ESTADOS_MOREAPP_PROCESADOS = frozenset({
    'PROCESADO',
    'EXITOSO',
    'ALERTA_REVISION',
})


def hay_actividad_operativa() -> bool:
    """True si existe al menos una OT o un registro MoreApp procesado."""
    if OrdenTrabajo.objects.exists():
        return True
    return IntegracionMoreApp.objects.filter(
        estado_sincronizacion__in=ESTADOS_MOREAPP_PROCESADOS,
    ).exists()


def _codigos_cliente_desde_moreapp() -> Set[str]:
    codigos: Set[str] = set()
    for registro in IntegracionMoreApp.objects.filter(
        estado_sincronizacion__in=ESTADOS_MOREAPP_PROCESADOS,
    ).only('datos_procesados', 'datos_recibidos'):
        datos = registro.datos_procesados or {}
        if not isinstance(datos, dict):
            datos = {}
        for clave in ('cliente_codigo', 'numero_cliente', 'cliente'):
            valor = datos.get(clave)
            if valor:
                codigos.add(str(valor).strip())
                break
        else:
            payload = registro.datos_recibidos or {}
            if isinstance(payload, dict):
                data = payload.get('data', {})
                if isinstance(data, dict):
                    for fuente in (data, data.get('buscarCliente', {}), data.get('clienteParaMantenimiento', {})):
                        if not isinstance(fuente, dict):
                            continue
                        for clave in ('cliente', 'cliente1', 'CLIENTE', 'numeroCliente'):
                            valor = fuente.get(clave)
                            if valor:
                                codigos.add(str(valor).strip())
                                break
    return {c for c in codigos if c}


def cliente_ids_operativos() -> Set[int]:
    """Clientes con OT o con registro MoreApp procesado vinculado."""
    ids: Set[int] = set(
        OrdenTrabajo.objects.exclude(cliente_id__isnull=True).values_list('cliente_id', flat=True)
    )
    codigos = _codigos_cliente_desde_moreapp()
    if codigos:
        ids.update(
            Cliente.objects.filter(numero_cliente__in=codigos).values_list('pk', flat=True)
        )
    return ids


def clientes_operativos_qs() -> QuerySet:
    """
    Clientes que participan en operación de terreno.
    Las importaciones masivas de fichas NO alimentan reportes operativos.
    """
    if not hay_actividad_operativa():
        return Cliente.objects.none()

    ids = cliente_ids_operativos()
    if not ids:
        return Cliente.objects.none()

    return Cliente.objects.filter(pk__in=ids, activo=True)


def filtrar_clientes_operativos(qs: QuerySet) -> QuerySet:
    """Restringe un queryset de clientes al ámbito operativo."""
    operativos = clientes_operativos_qs()
    return qs.filter(pk__in=operativos.values_list('pk', flat=True))
