"""Helpers de filtrado compartidos (lista + exportación)."""
from __future__ import annotations

from django.db.models import Count, Q
from django.db.models.functions import Length, Trim


def queryset_clientes_filtrado(request, *, aplicar_filtros: bool = True):
    """Queryset de clientes activos con los mismos filtros que la lista."""
    from clientes.models import Cliente

    base = Cliente.objects.filter(activo=True).exclude(numero_cliente__in=['', '0'])
    qs = (
        base.annotate(_ord_len=Length('numero_cliente'))
        .order_by('_ord_len', 'numero_cliente', 'meter_serial_n_1', 'id')
    )
    if not aplicar_filtros:
        return qs

    q = (request.GET.get('q') or '').strip()
    numero_cliente_filtro = (request.GET.get('numero_cliente') or '').strip()
    comuna_filtro = (request.GET.get('comuna') or '').strip()
    sector_filtro = (request.GET.get('sector') or '').strip()
    tipo_suministro_filtro = (request.GET.get('tipo_suministro') or '').strip()
    solo_duplicados = (request.GET.get('solo_duplicados') or '') == '1'
    alarma = (request.GET.get('alarma') or '').strip().lower()

    if solo_duplicados:
        # order_by() evita que un ordenamiento futuro del queryset contamine el GROUP BY
        numeros_duplicados = (
            base.order_by()
            .values('numero_cliente')
            .annotate(c=Count('id'))
            .filter(c__gt=1)
            .values_list('numero_cliente', flat=True)
        )
        qs = qs.filter(numero_cliente__in=numeros_duplicados)

    if alarma:
        from web.services.dashboard_metrics import aplicar_filtro_alarma_clientes
        qs = aplicar_filtro_alarma_clientes(qs, alarma)

    if numero_cliente_filtro:
        qs = qs.filter(numero_cliente__icontains=numero_cliente_filtro)
    if comuna_filtro:
        qs = qs.annotate(_comuna_norm=Trim('comuna')).filter(_comuna_norm__iexact=comuna_filtro)
    if sector_filtro:
        qs = qs.annotate(_sector_norm=Trim('sector')).filter(_sector_norm__iexact=sector_filtro)
    if tipo_suministro_filtro:
        qs = qs.annotate(_tipo_sum_norm=Trim('tipo_suministro')).filter(
            _tipo_sum_norm__iexact=tipo_suministro_filtro
        )
    if q:
        qs = qs.filter(
            Q(numero_cliente__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(comuna__icontains=q)
            | Q(direccion__icontains=q)
            | Q(installation_address__icontains=q)
            | Q(meter_serial_n_1__icontains=q)
            | Q(sector__icontains=q)
            | Q(tipo_suministro__icontains=q)
        )
    return qs
