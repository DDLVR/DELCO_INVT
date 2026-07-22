"""Dashboard KPI helpers for PDF points 7 and 13 — alarmas para analistas."""

from __future__ import annotations

from typing import Any, Dict, List

from django.db.models import Count, Q
from django.urls import reverse

from clientes.models import Cliente


def _clientes_activos_qs():
    return Cliente.objects.filter(activo=True).exclude(numero_cliente__in=['', '0'])


def count_clientes_con_ip_duplicada() -> int:
    """Count active clients sharing an IP with at least one other active client."""
    ips_duplicadas = (
        _clientes_activos_qs()
        .exclude(Q(ip__isnull=True) | Q(ip=''))
        .values('ip')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list('ip', flat=True)
    )
    return _clientes_activos_qs().filter(ip__in=list(ips_duplicadas)).count()


def count_clientes_con_medidor_duplicado() -> int:
    """Count active clients sharing a meter serial with at least one other active client."""
    series_duplicadas = (
        _clientes_activos_qs()
        .exclude(Q(meter_serial_n_1__isnull=True) | Q(meter_serial_n_1=''))
        .values('meter_serial_n_1')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list('meter_serial_n_1', flat=True)
    )
    return _clientes_activos_qs().filter(meter_serial_n_1__in=list(series_duplicadas)).count()


def count_clientes_sin_actualizacion_stb() -> int:
    return _clientes_activos_qs().filter(estado_stb='PENDIENTE').count()


def count_clientes_sin_actualizacion_sci4() -> int:
    return _clientes_activos_qs().filter(estado_sci4='PENDIENTE').count()


def count_clientes_ot_sin_responder() -> int:
    """Clientes con al menos una OT abierta / pendiente de respuesta."""
    try:
        from ordenes_trabajo.models import OrdenTrabajo
        from reportes.services import ESTADOS_PENDIENTES_OT
    except Exception:
        return 0

    cliente_ids = (
        OrdenTrabajo.objects.filter(eliminado=False, estado__in=ESTADOS_PENDIENTES_OT)
        .exclude(cliente_id__isnull=True)
        .values_list('cliente_id', flat=True)
        .distinct()
    )
    return _clientes_activos_qs().filter(id__in=cliente_ids).count()


def count_clientes_reincidentes() -> int:
    """Más de dos visitas (OT) en los últimos 6 meses."""
    try:
        from ordenes_trabajo.models import OrdenTrabajo
        from ordenes_trabajo.services import six_month_window_start
    except Exception:
        return 0

    return (
        OrdenTrabajo.objects.filter(
            eliminado=False,
            fecha_creacion__date__gte=six_month_window_start(),
        )
        .exclude(estado='CANCELADA')
        .exclude(cliente_id__isnull=True)
        .values('cliente_id')
        .annotate(visitas=Count('id'))
        .filter(visitas__gt=2)
        .count()
    )


def count_clientes_medidor_terreno_distinto() -> int:
    """
    Clientes distintos con informe MoreApp abierto donde el medidor de terreno
    no coincide con el del sistema.
    """
    try:
        from ordenes_trabajo.models import IntegracionMoreApp, OrdenTrabajo
    except Exception:
        return 0

    qs = IntegracionMoreApp.objects.filter(
        eliminado=False,
        estado_revision__in=('PENDIENTE', 'CON_ADVERTENCIA'),
    ).filter(
        Q(descripcion_alerta__icontains='distinto')
        | Q(descripcion_alerta__icontains='terreno distinto')
    )

    codigos = set()
    orden_ids = set()
    for reg in qs.only('datos_procesados', 'orden_id', 'descripcion_alerta').iterator(chunk_size=300):
        desc = str(reg.descripcion_alerta or '').lower()
        datos = reg.datos_procesados if isinstance(reg.datos_procesados, dict) else {}
        pendientes = []
        resultado = datos.get('resultado_operativo') if isinstance(datos, dict) else {}
        if isinstance(resultado, dict):
            pendientes = resultado.get('pendientes_revision') or []
        texto_pend = ' '.join(
            str(p.get('motivo', '') if isinstance(p, dict) else p) for p in pendientes
        ).lower()
        if 'distinto' not in desc and 'distinto' not in texto_pend:
            continue
        codigo = str(datos.get('cliente_codigo') or '').strip()
        if codigo:
            codigos.add(codigo)
        if getattr(reg, 'orden_id', None):
            orden_ids.add(reg.orden_id)

    ids = set()
    if codigos:
        ids.update(
            _clientes_activos_qs().filter(numero_cliente__in=list(codigos)).values_list('id', flat=True)
        )
    if orden_ids:
        ids.update(
            OrdenTrabajo.objects.filter(id__in=orden_ids)
            .exclude(cliente_id__isnull=True)
            .values_list('cliente_id', flat=True)
        )
    return len(ids)


def count_clientes_sin_comunicacion() -> int:
    return _clientes_activos_qs().filter(
        estado_telemetria__in=('SIN_COMUNICACION', 'NO_COMUNICA')
    ).count()


def count_clientes_sin_medidor() -> int:
    return _clientes_activos_qs().filter(
        Q(estado_telemetria='SIN_MEDIDOR')
        | Q(meter_serial_n_1__isnull=True)
        | Q(meter_serial_n_1='')
    ).count()


def count_clientes_sim_sin_datos() -> int:
    return _clientes_activos_qs().filter(sim_estado='SIN_DATOS').count()


def count_clientes_modem_sin_respuesta() -> int:
    q = Q()
    for kw in (
        'módem sin respuesta',
        'modem sin respuesta',
        'módem no responde',
        'modem no responde',
        'modem sin resp',
    ):
        q |= Q(note__icontains=kw) | Q(trabajo__icontains=kw) | Q(modem__icontains=kw)
    # Proxy: telemetría sin comunicación y con módem informado
    q |= (
        Q(estado_telemetria__in=('SIN_COMUNICACION', 'NO_COMUNICA'))
        & ~Q(modem__isnull=True)
        & ~Q(modem='')
    )
    return _clientes_activos_qs().filter(q).count()


def count_clientes_disciplina_mercado() -> int:
    return _clientes_activos_qs().filter(
        Q(note__icontains='disciplina')
        | Q(trabajo__icontains='disciplina')
        | Q(note__icontains='mercado')
    ).count()


def count_clientes_cerrado_reiterado() -> int:
    """Clientes con antecedentes de cerrado / no permite / deshabitado."""
    q = Q()
    for kw in ('cerrado', 'deshabitado', 'no permite', 'no permite acceso'):
        q |= Q(trabajo__icontains=kw) | Q(note__icontains=kw)
    return _clientes_activos_qs().filter(q).count()


def count_clientes_ejecutado_no_actualizado() -> int:
    """
    Trabajo ejecutado en terreno (OT realizada/validada o MoreApp) pero STB/SCi4 pendiente.
    """
    try:
        from ordenes_trabajo.models import OrdenTrabajo, IntegracionMoreApp
    except Exception:
        return _clientes_activos_qs().filter(
            Q(estado_stb='PENDIENTE') | Q(estado_sci4='PENDIENTE')
        ).count()

    estados_ejecutados = {
        'REALIZADA',
        'VALIDADA',
        'FINALIZADA',
        'REALIZADA_PENDIENTE_COMPROBACION',
    }
    ids_ot = set(
        OrdenTrabajo.objects.filter(eliminado=False, estado__in=estados_ejecutados)
        .exclude(cliente_id__isnull=True)
        .values_list('cliente_id', flat=True)
    )
    codigos_moreapp = set()
    for reg in (
        IntegracionMoreApp.objects.filter(eliminado=False)
        .exclude(estado_sincronizacion__in=('ERROR_JSON', 'ERROR_LECTURA', 'ERROR'))
        .only('datos_procesados')
        .iterator(chunk_size=500)
    ):
        datos = reg.datos_procesados if isinstance(reg.datos_procesados, dict) else {}
        codigo = str(datos.get('cliente_codigo') or '').strip()
        if codigo:
            codigos_moreapp.add(codigo)

    ids_moreapp = set(
        _clientes_activos_qs().filter(numero_cliente__in=list(codigos_moreapp)).values_list('id', flat=True)
    ) if codigos_moreapp else set()

    ids = ids_ot | ids_moreapp
    if not ids:
        return 0
    return _clientes_activos_qs().filter(
        id__in=ids
    ).filter(
        Q(estado_stb='PENDIENTE') | Q(estado_sci4='PENDIENTE')
    ).count()


def _url_reporte(slug: str) -> str:
    try:
        return reverse('reportes_export', kwargs={'slug': slug})
    except Exception:
        return reverse('reportes_hub')


def build_panel_alarmas_analistas() -> List[Dict[str, Any]]:
    """
    Catálogo completo del PDF punto 7 (14 alarmas).
    Siempre retorna las 14 entradas para el panel del dashboard.
    """
    items = [
        {
            'key': 'ip_duplicada',
            'label': 'IP repetida',
            'count': count_clientes_con_ip_duplicada(),
            'severity': 'danger',
            'url': _url_reporte('clientes_ip_duplicada'),
        },
        {
            'key': 'medidor_duplicado',
            'label': 'Medidor repetido',
            'count': count_clientes_con_medidor_duplicado(),
            'severity': 'danger',
            'url': _url_reporte('clientes_medidor_duplicado'),
        },
        {
            'key': 'pendiente_stb',
            'label': 'Sin actualización STB',
            'count': count_clientes_sin_actualizacion_stb(),
            'severity': 'warning',
            'url': _url_reporte('clientes_pendientes_stb'),
        },
        {
            'key': 'pendiente_sci4',
            'label': 'Sin actualización SCi4',
            'count': count_clientes_sin_actualizacion_sci4(),
            'severity': 'warning',
            'url': _url_reporte('clientes_pendientes_sci4'),
        },
        {
            'key': 'ot_sin_responder',
            'label': 'OT sin responder',
            'count': count_clientes_ot_sin_responder(),
            'severity': 'warning',
            'url': _url_reporte('clientes_pendientes'),
        },
        {
            'key': 'reincidentes',
            'label': 'Más de 2 visitas (6 meses)',
            'count': count_clientes_reincidentes(),
            'severity': 'warning',
            'url': _url_reporte('clientes_reincidentes'),
        },
        {
            'key': 'medidor_terreno_distinto',
            'label': 'Medidor terreno distinto al sistema',
            'count': count_clientes_medidor_terreno_distinto(),
            'severity': 'danger',
            'url': _url_reporte('clientes_medidor_terreno_distinto'),
        },
        {
            'key': 'sin_comunicacion',
            'label': 'Sin comunicación',
            'count': count_clientes_sin_comunicacion(),
            'severity': 'warning',
            'url': _url_reporte('clientes_sin_comunicacion'),
        },
        {
            'key': 'sin_medidor',
            'label': 'Sin medidor',
            'count': count_clientes_sin_medidor(),
            'severity': 'warning',
            'url': _url_reporte('clientes_sin_medidor'),
        },
        {
            'key': 'sim_sin_datos',
            'label': 'SIM sin datos',
            'count': count_clientes_sim_sin_datos(),
            'severity': 'warning',
            'url': _url_reporte('clientes_sim_sin_datos'),
        },
        {
            'key': 'modem_sin_respuesta',
            'label': 'Módem sin respuesta',
            'count': count_clientes_modem_sin_respuesta(),
            'severity': 'warning',
            'url': _url_reporte('clientes_modem_sin_respuesta'),
        },
        {
            'key': 'disciplina_mercado',
            'label': 'Disciplina de Mercado',
            'count': count_clientes_disciplina_mercado(),
            'severity': 'info',
            'url': _url_reporte('clientes_disciplina_mercado'),
        },
        {
            'key': 'cerrado_reiterado',
            'label': 'Cerrado / no permite / deshabitado',
            'count': count_clientes_cerrado_reiterado(),
            'severity': 'secondary',
            'url': _url_reporte('clientes_estado_visita'),
        },
        {
            'key': 'ejecutado_no_actualizado',
            'label': 'Ejecutado, no actualizado en sistema',
            'count': count_clientes_ejecutado_no_actualizado(),
            'severity': 'danger',
            'url': _url_reporte('clientes_ejecutado_no_actualizado'),
        },
    ]
    return items
