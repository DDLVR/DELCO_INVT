"""
Avisos operativos MoreApp para ADMIN / ADMINISTRATIVO.

Cuenta pendientes/advertencias y detecta informes nuevos desde la última
revisión del usuario (session), para mostrar banner y badge en el menú.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from django.utils import timezone
from django.utils.dateparse import parse_datetime

SESSION_KEY_VISTO = 'moreapp_aviso_visto_ts'
ROLES_AVISO = ('ADMIN', 'ADMINISTRATIVO')
ESTADOS_POR_REVISAR = ('PENDIENTE', 'CON_ADVERTENCIA')


def _qs_por_revisar():
    from ordenes_trabajo.models import IntegracionMoreApp

    return IntegracionMoreApp.objects.filter(estado_revision__in=ESTADOS_POR_REVISAR)


def marcar_aviso_moreapp_visto(request) -> None:
    """Marca el momento en que el usuario revisó la cola MoreApp."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return
    if getattr(request.user, 'rol', None) not in ROLES_AVISO:
        return
    request.session[SESSION_KEY_VISTO] = timezone.now().isoformat()
    request.session.modified = True


def _timestamp_visto(request) -> Optional[timezone.datetime]:
    raw = request.session.get(SESSION_KEY_VISTO)
    if not raw:
        return None
    dt = parse_datetime(str(raw))
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def construir_aviso_moreapp(request) -> Dict[str, Any]:
    """
    Construye el dict de aviso para templates.

    Campos:
      activo, pendientes, advertencias, por_revisar, nuevos,
      llegaron_hoy, recientes (lista corta)
    """
    vacio = {
        'activo': False,
        'pendientes': 0,
        'advertencias': 0,
        'por_revisar': 0,
        'nuevos': 0,
        'llegaron_hoy': 0,
        'recientes': [],
    }

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or getattr(user, 'rol', None) not in ROLES_AVISO:
        return vacio

    try:
        from ordenes_trabajo.models import IntegracionMoreApp
    except Exception:
        return vacio

    ahora = timezone.now()
    qs = _qs_por_revisar()
    pendientes = qs.filter(estado_revision='PENDIENTE').count()
    advertencias = qs.filter(estado_revision='CON_ADVERTENCIA').count()
    por_revisar = pendientes + advertencias
    llegaron_hoy = qs.filter(fecha_recepcion__gte=ahora - timedelta(hours=24)).count()

    visto = _timestamp_visto(request)
    if visto:
        nuevos = qs.filter(fecha_recepcion__gt=visto).count()
    else:
        # Primera visita de sesión: resaltar los de las últimas 24 h
        nuevos = llegaron_hoy

    recientes_qs = qs.order_by('-fecha_recepcion')[:5]
    recientes = []
    for item in recientes_qs:
        recientes.append({
            'id': item.id,
            'numero_correlativo': item.numero_correlativo,
            'nombre_formulario': item.nombre_formulario or '',
            'estado_revision': item.estado_revision,
            'fecha_recepcion': item.fecha_recepcion.isoformat() if item.fecha_recepcion else '',
            'orden_id': item.orden_id,
        })

    return {
        'activo': por_revisar > 0,
        'pendientes': pendientes,
        'advertencias': advertencias,
        'por_revisar': por_revisar,
        'nuevos': nuevos,
        'llegaron_hoy': llegaron_hoy,
        'recientes': recientes,
    }
