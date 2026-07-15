"""Estado operativo MoreApp para UI y cron (Puntos PDF 6 y 8)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

CACHE_LAST_SYNC = 'moreapp:last_sync_status'


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
    # Invalidar conteos livianos que dependen de MoreApp
    for key in (
        'moreapp:aviso_conteos',
        'moreapp:list_kpis',
        'moreapp:adv_breakdown',
        'operacional:codigos_moreapp',
        'operacional:cliente_ids',
    ):
        cache.delete(key)


def construir_ops_status_moreapp() -> Dict[str, Any]:
    """Snapshot para el panel ops del listado MoreApp."""
    base = str(getattr(settings, 'MOREAPP_REGISTROS_DIR', '') or '')
    dir_existe = bool(base) and os.path.isdir(base)
    dir_legible = False
    if dir_existe:
        try:
            os.listdir(base)
            dir_legible = True
        except OSError:
            dir_legible = False

    ultimo = cache.get(CACHE_LAST_SYNC) or {}
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
                'formulario': reg.nombre_formulario or '',
                'correlativo': reg.numero_correlativo,
            }
    except Exception:
        ultimo_registro = None

    return {
        'base_dir': base,
        'dir_existe': dir_existe,
        'dir_legible': dir_legible,
        'auto_sync_enabled': bool(getattr(settings, 'MOREAPP_AUTO_SYNC_ENABLED', False)),
        'max_segundos': int(getattr(settings, 'MOREAPP_WEB_SYNC_MAX_SEGUNDOS', 30) or 30),
        'max_archivos': int(getattr(settings, 'MOREAPP_WEB_SYNC_MAX_ARCHIVOS', 40) or 40),
        'auto_refresh_seconds': int(getattr(settings, 'MOREAPP_AUTO_REFRESH_SECONDS', 0) or 0),
        'ultimo_sync': ultimo,
        'ultimo_registro': ultimo_registro,
        'cron_ejemplo': (
            'cd /home50/delcochi/delcochile_inventario && '
            './venv/bin/python manage.py sincronizar_registros --limite-web'
        ),
    }
