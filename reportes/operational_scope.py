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
    """True si existe al menos una OT o un registro MoreApp procesado.

    No se cachea: ``exists()`` es barato y un False stale ocultaría el hub
    justo después de crear la primera OT.
    """
    if OrdenTrabajo.objects.exists():
        return True
    return IntegracionMoreApp.objects.filter(
        estado_sincronizacion__in=ESTADOS_MOREAPP_PROCESADOS,
    ).exists()


def _codigos_cliente_desde_moreapp() -> Set[str]:
    from web.perf_cache import cache_get_or_set, TTL_MEDIO

    def _calc():
        codigos: Set[str] = set()
        # Solo campos ya normalizados: evita recorrer datos_recibidos en cada request
        for codigo in (
            IntegracionMoreApp.objects.filter(
                estado_sincronizacion__in=ESTADOS_MOREAPP_PROCESADOS,
            )
            .exclude(datos_procesados__cliente_codigo__isnull=True)
            .values_list('datos_procesados__cliente_codigo', flat=True)
            .iterator(chunk_size=2000)
        ):
            if codigo:
                texto = str(codigo).strip()
                if texto:
                    codigos.add(texto)
        return codigos

    return set(cache_get_or_set('operacional:codigos_moreapp', _calc, TTL_MEDIO))


def cliente_ids_operativos() -> Set[int]:
    """Clientes con OT o con registro MoreApp procesado vinculado."""
    from web.perf_cache import cache_get_or_set, TTL_MEDIO

    def _calc():
        ids: Set[int] = set(
            OrdenTrabajo.objects.exclude(cliente_id__isnull=True)
            .values_list('cliente_id', flat=True)
            .distinct()
        )
        codigos = _codigos_cliente_desde_moreapp()
        if codigos:
            ids.update(
                Cliente.objects.filter(numero_cliente__in=codigos).values_list('pk', flat=True)
            )
        return ids

    return set(cache_get_or_set('operacional:cliente_ids', _calc, TTL_MEDIO))


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
