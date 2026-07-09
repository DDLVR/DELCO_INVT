"""Dashboard KPI helpers for PDF points 7 and 13."""

from __future__ import annotations

from django.db.models import Count, Q

from clientes.models import Cliente


def count_clientes_con_ip_duplicada() -> int:
    """Count active clients sharing an IP with at least one other active client."""
    ips_duplicadas = (
        Cliente.objects.filter(activo=True)
        .exclude(Q(ip__isnull=True) | Q(ip=''))
        .values('ip')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list('ip', flat=True)
    )
    return Cliente.objects.filter(activo=True, ip__in=list(ips_duplicadas)).count()


def count_clientes_con_medidor_duplicado() -> int:
    """Count active clients sharing a meter serial with at least one other active client."""
    series_duplicadas = (
        Cliente.objects.filter(activo=True)
        .exclude(Q(meter_serial_n_1__isnull=True) | Q(meter_serial_n_1=''))
        .values('meter_serial_n_1')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list('meter_serial_n_1', flat=True)
    )
    return Cliente.objects.filter(activo=True, meter_serial_n_1__in=list(series_duplicadas)).count()


def count_clientes_sin_actualizacion_stb() -> int:
    return Cliente.objects.filter(activo=True, estado_stb='PENDIENTE').count()


def count_clientes_sin_actualizacion_sci4() -> int:
    return Cliente.objects.filter(activo=True, estado_sci4='PENDIENTE').count()
