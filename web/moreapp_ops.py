"""Estado operativo MoreApp para UI y cron (Puntos PDF 6 y 8)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

CACHE_LAST_SYNC = 'moreapp:last_sync_status'

_ORIGEN_AMIGABLE = {
    'manual_web': 'desde esta pantalla',
    'manual': 'manual',
    'cron': 'automática del servidor',
    'comando': 'desde el servidor',
}


def registrar_resultado_sync(stats: Optional[Dict[str, Any]], origen: str = 'manual') -> None:
    """Guarda un resumen de la última sincronización (manual o cron)."""
    if not isinstance(stats, dict):
        return
    payload = {
        'origen': origen,
        'ts': timezone.now().isoformat(),
        'base_dir': stats.get('base_dir') or '',
        'nuevos': int(stats.get('nuevos') or 0),
        'duplicados': int(stats.get('duplicados') or 0),
        'alertas': int(stats.get('alertas') or 0),
        'errores': int(stats.get('errores') or 0),
        'omitidos': int(stats.get('omitidos') or 0),
        'carpetas_revisadas': int(stats.get('carpetas_revisadas') or 0),
        'incompleto': bool(stats.get('incompleto')),
        'motivo_corte': str(stats.get('motivo_corte') or ''),
        'modo': str(stats.get('modo') or ''),
    }
    cache.set(CACHE_LAST_SYNC, payload, timeout=60 * 60 * 24 * 14)
    for key in (
        'moreapp:aviso_conteos',
        'moreapp:list_kpis',
        'moreapp:adv_breakdown',
        'operacional:codigos_moreapp',
        'operacional:cliente_ids',
    ):
        cache.delete(key)


def _formato_fecha_local(iso_ts: str) -> str:
    if not iso_ts:
        return ''
    dt = parse_datetime(str(iso_ts))
    if dt is None:
        return str(iso_ts)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    else:
        dt = timezone.localtime(dt)
    return dt.strftime('%d/%m/%Y %H:%M')


def construir_ops_status_moreapp() -> Dict[str, Any]:
    """Snapshot amigable para el panel del listado MoreApp."""
    base = str(getattr(settings, 'MOREAPP_REGISTROS_DIR', '') or '')
    dir_existe = bool(base) and os.path.isdir(base)
    dir_legible = False
    if dir_existe:
        try:
            os.listdir(base)
            dir_legible = True
        except OSError:
            dir_legible = False

    if dir_existe and dir_legible:
        estado_carpeta = 'ok'
        estado_carpeta_texto = 'Listo para recibir informes de terreno'
    elif dir_existe:
        estado_carpeta = 'sin_lectura'
        estado_carpeta_texto = 'No se pueden leer los informes (avisar a soporte)'
    else:
        estado_carpeta = 'faltante'
        estado_carpeta_texto = 'Falta la carpeta de informes (avisar a soporte)'

    ultimo = cache.get(CACHE_LAST_SYNC) or {}
    origen_raw = str(ultimo.get('origen') or '')
    origen_texto = _ORIGEN_AMIGABLE.get(origen_raw, 'del sistema')
    ts_texto = _formato_fecha_local(str(ultimo.get('ts') or ''))

    ultimo_registro = None
    try:
        from ordenes_trabajo.models import IntegracionMoreApp

        reg = (
            IntegracionMoreApp.objects.order_by('-fecha_recepcion')
            .only('fecha_recepcion', 'nombre_formulario', 'numero_correlativo')
            .first()
        )
        if reg and reg.fecha_recepcion:
            ultimo_registro = {
                'fecha': reg.fecha_recepcion.isoformat(),
                'fecha_texto': timezone.localtime(reg.fecha_recepcion).strftime('%d/%m/%Y %H:%M'),
                'formulario': reg.nombre_formulario or '',
                'correlativo': reg.numero_correlativo,
            }
    except Exception:
        ultimo_registro = None

    return {
        'base_dir': base,
        'dir_existe': dir_existe,
        'dir_legible': dir_legible,
        'estado_carpeta': estado_carpeta,
        'estado_carpeta_texto': estado_carpeta_texto,
        'auto_sync_enabled': bool(getattr(settings, 'MOREAPP_AUTO_SYNC_ENABLED', False)),
        'max_segundos': int(getattr(settings, 'MOREAPP_WEB_SYNC_MAX_SEGUNDOS', 30) or 30),
        'max_archivos': int(getattr(settings, 'MOREAPP_WEB_SYNC_MAX_ARCHIVOS', 40) or 40),
        'auto_refresh_seconds': int(getattr(settings, 'MOREAPP_AUTO_REFRESH_SECONDS', 0) or 0),
        'ultimo_sync': ultimo,
        'ultimo_sync_origen_texto': origen_texto,
        'ultimo_sync_fecha_texto': ts_texto,
        'ultimo_registro': ultimo_registro,
    }
