"""Cálculo de alarmas operativas para dashboard (PDF puntos 7 y 13)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone


def _clientes_activos():
    from clientes.models import Cliente

    return Cliente.objects.filter(activo=True)


def contar_ips_duplicadas() -> int:
    """Cantidad de IPs repetidas entre clientes activos."""
    return (
        _clientes_activos()
        .exclude(Q(ip__isnull=True) | Q(ip=''))
        .values('ip')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .count()
    )


def contar_medidores_duplicados() -> int:
    """Cantidad de series de medidor repetidas entre clientes activos."""
    return (
        _clientes_activos()
        .exclude(Q(meter_serial_n_1__isnull=True) | Q(meter_serial_n_1=''))
        .values('meter_serial_n_1')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .count()
    )


def contar_clientes_reincidentes() -> int:
    """Clientes con más de 2 OT ejecutadas en los últimos 6 meses."""
    from ordenes_trabajo.models import OrdenTrabajo
    from ordenes_trabajo.services import six_month_window_start

    desde = six_month_window_start()
    estados_ejecutadas = [
        'REALIZADA',
        'REALIZADA_PENDIENTE_COMPROBACION',
        'PENDIENTE_VALIDACION',
        'VALIDADA',
        'FINALIZADA',
    ]
    return (
        OrdenTrabajo.objects.filter(
            fecha_creacion__date__gte=desde,
            estado__in=estados_ejecutadas,
            cliente__isnull=False,
        )
        .values('cliente_id')
        .annotate(visitas=Count('id'))
        .filter(visitas__gt=2)
        .count()
    )


def obtener_kpis_ordenes() -> dict:
    """KPIs de órdenes de trabajo para dashboard."""
    from ordenes_trabajo.models import OrdenTrabajo

    estados_abiertos = OrdenTrabajo.ESTADOS_ABIERTOS
    estados_ejecutadas = {
        'REALIZADA',
        'REALIZADA_PENDIENTE_COMPROBACION',
        'PENDIENTE_VALIDACION',
        'VALIDADA',
        'FINALIZADA',
    }
    hoy = timezone.now().date()

    return {
        'total_ordenes': OrdenTrabajo.objects.count(),
        'ordenes_pendientes': OrdenTrabajo.objects.filter(estado__in=estados_abiertos).count(),
        'ordenes_completadas': OrdenTrabajo.objects.filter(estado__in=estados_ejecutadas).count(),
        'ordenes_canceladas': OrdenTrabajo.objects.filter(estado='CANCELADA').count(),
        'ordenes_cerradas_sin_ejecutar': OrdenTrabajo.objects.filter(
            estado='CANCELADA',
            fecha_inicio_ejecucion__isnull=True,
        ).count(),
        'ordenes_pendientes_validacion': OrdenTrabajo.objects.filter(
            estado='PENDIENTE_VALIDACION'
        ).count(),
        'trabajos_ejecutados_hoy': OrdenTrabajo.objects.filter(
            fecha_fin_ejecucion__date=hoy,
            estado__in=estados_ejecutadas,
        ).count(),
        'ot_sin_respuesta': OrdenTrabajo.objects.filter(
            estado__in=['CREADA', 'ASIGNADA', 'PENDIENTE_VALIDACION'],
            fecha_creacion__lt=timezone.now() - timedelta(days=7),
        ).count(),
    }


def obtener_panel_alarmas() -> list[dict]:
    """Lista de alarmas operativas para analistas."""
    from ordenes_trabajo.models import IntegracionMoreApp

    kpis_ot = obtener_kpis_ordenes()
    alarmas: list[dict] = []

    def _add(codigo, titulo, cantidad, url_name='dashboard', severidad='warning'):
        if cantidad:
            alarmas.append(
                {
                    'codigo': codigo,
                    'titulo': titulo,
                    'cantidad': cantidad,
                    'url_name': url_name,
                    'severidad': severidad,
                }
            )

    _add('ip_duplicada', 'IPs repetidas entre clientes', contar_ips_duplicadas(), 'clientes_list')
    _add('medidor_duplicado', 'Medidores repetidos entre clientes', contar_medidores_duplicados(), 'clientes_list')
    _add('reincidencia', 'Clientes con más de 2 visitas (6 meses)', contar_clientes_reincidentes(), 'ordenes_list')
    _add('ot_abiertas', 'OT abiertas', kpis_ot['ordenes_pendientes'], 'ordenes_list', 'info')
    _add(
        'ot_sin_respuesta',
        'OT pendientes sin respuesta (> 7 días)',
        kpis_ot['ot_sin_respuesta'],
        'ordenes_list',
        'danger',
    )
    _add(
        'ot_cerradas_sin_ejecutar',
        'OT cerradas sin ejecutar',
        kpis_ot['ordenes_cerradas_sin_ejecutar'],
        'ordenes_list',
    )
    _add(
        'moreapp_pendientes',
        'Registros MoreApp sin revisar',
        IntegracionMoreApp.objects.filter(estado_revision='PENDIENTE').count(),
        'pendientes_operativos',
        'danger',
    )
    _add(
        'moreapp_advertencia',
        'Registros MoreApp con advertencia',
        IntegracionMoreApp.objects.filter(estado_revision='CON_ADVERTENCIA').count(),
        'pendientes_operativos',
    )

    umbral = timezone.now() - timedelta(days=7)
    _add(
        'moreapp_envejecidos',
        'MoreApp sin revisar > 7 días',
        IntegracionMoreApp.objects.filter(
            estado_revision='PENDIENTE',
            fecha_recepcion__lt=umbral,
        ).count(),
        'pendientes_operativos',
        'danger',
    )

    return alarmas
