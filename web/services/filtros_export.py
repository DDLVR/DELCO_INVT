"""Helpers de filtrado compartidos (lista + exportación)."""
from __future__ import annotations

from django.db.models import Count, Q
from django.db.models.functions import Length, Trim


def es_sin_proyecto(valor) -> bool:
    """True si el valor representa ausencia de proyecto (cualquier casing / vacío)."""
    texto = (str(valor).strip() if valor is not None else '')
    if not texto:
        return True
    normalizado = ' '.join(texto.casefold().replace('_', ' ').split())
    return normalizado in {
        'sin proyecto',
        'sinproyectos',
        'sin proyectos',
        '__vacio__',
        'null',
        'nulo',
        'none',
        '-',
    }


def q_sin_proyecto(campo: str = 'proyecto') -> Q:
    """Filtro ORM que agrupa vacío + variantes de 'sin proyecto'."""
    return (
        Q(**{f'{campo}__isnull': True})
        | Q(**{campo: ''})
        | Q(**{f'{campo}__iexact': 'SIN PROYECTO'})
        | Q(**{f'{campo}__iexact': 'sin proyecto'})
        | Q(**{f'{campo}__iexact': 'Sin Proyecto'})
        | Q(**{f'{campo}__iexact': 'SIN_PROYECTO'})
    )


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
    proyecto_filtro = (request.GET.get('proyecto') or '').strip()
    marca_filtro = (request.GET.get('marca') or request.GET.get('meter_manufacturer_id') or '').strip()
    serie_filtro = (request.GET.get('serie') or request.GET.get('meter_serial_n_1') or '').strip()
    empresa_filtro = (request.GET.get('empresa') or '').strip()
    ip_filtro = (request.GET.get('ip') or '').strip()
    nombre_filtro = (request.GET.get('nombre') or request.GET.get('customer_name') or '').strip()
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
    if proyecto_filtro:
        if es_sin_proyecto(proyecto_filtro):
            qs = qs.filter(q_sin_proyecto('proyecto'))
        else:
            qs = qs.annotate(_proyecto_norm=Trim('proyecto')).filter(_proyecto_norm__iexact=proyecto_filtro)
    if marca_filtro:
        qs = qs.annotate(_marca_norm=Trim('meter_manufacturer_id')).filter(
            _marca_norm__iexact=marca_filtro
        )
    if serie_filtro:
        qs = qs.filter(meter_serial_n_1__icontains=serie_filtro)
    if empresa_filtro:
        qs = qs.annotate(_empresa_norm=Trim('empresa')).filter(_empresa_norm__iexact=empresa_filtro)
    if ip_filtro:
        qs = qs.filter(ip__icontains=ip_filtro)
    if nombre_filtro:
        qs = qs.filter(customer_name__icontains=nombre_filtro)
    if q:
        qs = qs.filter(
            Q(numero_cliente__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(comuna__icontains=q)
            | Q(direccion__icontains=q)
            | Q(installation_address__icontains=q)
            | Q(meter_serial_n_1__icontains=q)
            | Q(meter_manufacturer_id__icontains=q)
            | Q(sector__icontains=q)
            | Q(tipo_suministro__icontains=q)
            | Q(proyecto__icontains=q)
            | Q(empresa__icontains=q)
            | Q(ip__icontains=q)
            | Q(modem__icontains=q)
        )
    return qs
