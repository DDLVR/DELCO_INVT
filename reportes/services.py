"""Consultas analíticas alineadas al PDF punto 9."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable, Dict, List, Optional, Tuple

from django.db.models import Count, Q
from django.utils import timezone

from clientes.models import Cliente
from ordenes_trabajo.models import IntegracionMoreApp, OrdenTrabajo
from ordenes_trabajo.services import six_month_window_start
from web.services.dashboard_metrics import (
    count_clientes_con_ip_duplicada,
    count_clientes_con_medidor_duplicado,
)

ReportResult = Tuple[List[str], List[List[Any]]]

ESTADOS_EJECUTADOS = {'REALIZADA', 'VALIDADA', 'FINALIZADA'}
ESTADOS_PENDIENTES_OT = OrdenTrabajo.ESTADOS_ABIERTOS | {
    'PENDIENTE_VALIDACION',
    'REALIZADA_PENDIENTE_COMPROBACION',
}


def parse_report_filters(params) -> Dict[str, Any]:
    fecha_desde = (params.get('fecha_desde') or '').strip()
    fecha_hasta = (params.get('fecha_hasta') or '').strip()
    tecnico_id = (params.get('tecnico_id') or '').strip()
    empresa = (params.get('empresa') or '').strip()
    return {
        'fecha_desde': _parse_date(fecha_desde),
        'fecha_hasta': _parse_date(fecha_hasta),
        'tecnico_id': int(tecnico_id) if tecnico_id.isdigit() else None,
        'empresa': empresa,
    }


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _aware_start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _aware_end(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.max))


def _cliente_row(cliente: Cliente) -> List[Any]:
    return [
        cliente.numero_cliente,
        cliente.customer_name or '',
        cliente.direccion or '',
        cliente.comuna or '',
        cliente.sector or '',
        cliente.empresa or '',
        cliente.meter_serial_n_1 or '',
        cliente.ip or '',
        cliente.puerto or '',
        cliente.modem or '',
        cliente.estado_telemetria or '',
        cliente.get_estado_stb_display() if cliente.estado_stb else '',
        cliente.get_estado_sci4_display() if cliente.estado_sci4 else '',
        cliente.sim_operador or '',
        cliente.sim_iccid or '',
        cliente.sim_abonado or '',
        cliente.get_sim_estado_display() if cliente.sim_estado else '',
    ]


CLIENTE_HEADERS = [
    'Numero Cliente',
    'Nombre',
    'Direccion',
    'Comuna',
    'Sector',
    'Empresa',
    'Serie Medidor',
    'IP',
    'Puerto',
    'Modem',
    'Estado Telemetria',
    'Estado STB',
    'Estado SCi4',
    'Operador SIM',
    'ICCID',
    'Abonado',
    'Estado SIM',
]


def report_clientes_completos(_filters: Dict[str, Any]) -> ReportResult:
    rows = [_cliente_row(c) for c in Cliente.objects.filter(activo=True).order_by('numero_cliente')]
    return CLIENTE_HEADERS, rows


def report_clientes_ejecutados(_filters: Dict[str, Any]) -> ReportResult:
    cliente_ids = (
        OrdenTrabajo.objects.filter(estado__in=ESTADOS_EJECUTADOS, cliente_id__isnull=False)
        .values_list('cliente_id', flat=True)
        .distinct()
    )
    rows = [_cliente_row(c) for c in Cliente.objects.filter(pk__in=cliente_ids, activo=True).order_by('numero_cliente')]
    return CLIENTE_HEADERS, rows


def report_clientes_pendientes(_filters: Dict[str, Any]) -> ReportResult:
    pendientes_ot = set(
        OrdenTrabajo.objects.filter(estado__in=ESTADOS_PENDIENTES_OT, cliente_id__isnull=False)
        .values_list('cliente_id', flat=True)
    )
    pendientes_moreapp = {
        codigo for codigo in IntegracionMoreApp.objects.filter(
            estado_revision__in={'PENDIENTE', 'CON_ADVERTENCIA'},
        ).values_list('datos_procesados__cliente_codigo', flat=True)
        if codigo
    }
    clientes = Cliente.objects.filter(activo=True).order_by('numero_cliente')
    rows = []
    for cliente in clientes:
        motivos = []
        if cliente.id in pendientes_ot:
            motivos.append('OT pendiente')
        if cliente.numero_cliente in pendientes_moreapp:
            motivos.append('MoreApp pendiente')
        if motivos:
            row = _cliente_row(cliente)
            row.append('; '.join(motivos))
            rows.append(row)
    headers = CLIENTE_HEADERS + ['Motivo Pendiente']
    return headers, rows


def report_ot_cerradas_sin_ejecutar(_filters: Dict[str, Any]) -> ReportResult:
    headers = [
        'ID OT', 'Cliente', 'Titulo', 'Estado', 'Tecnico', 'Fecha Creacion', 'Observaciones',
    ]
    qs = OrdenTrabajo.objects.filter(estado='CANCELADA', fecha_inicio_ejecucion__isnull=True)
    qs = _filter_ordenes_fecha(qs, _filters)
    rows = [
        [
            ot.id,
            ot.cliente.numero_cliente if ot.cliente else '',
            ot.titulo,
            ot.get_estado_display(),
            ot.tecnico_responsable.nombre_interno if ot.tecnico_responsable else '',
            ot.fecha_creacion.strftime('%Y-%m-%d %H:%M') if ot.fecha_creacion else '',
            ot.observaciones_tecnicas or '',
        ]
        for ot in qs.select_related('cliente', 'tecnico_responsable').order_by('-fecha_creacion')
    ]
    return headers, rows


def _filter_ordenes_fecha(qs, filters: Dict[str, Any]):
    if filters.get('fecha_desde'):
        qs = qs.filter(fecha_creacion__gte=_aware_start(filters['fecha_desde']))
    if filters.get('fecha_hasta'):
        qs = qs.filter(fecha_creacion__lte=_aware_end(filters['fecha_hasta']))
    if filters.get('tecnico_id'):
        qs = qs.filter(tecnico_responsable_id=filters['tecnico_id'])
    if filters.get('empresa'):
        qs = qs.filter(cliente__empresa__icontains=filters['empresa'])
    return qs


def report_trabajos_por_fecha(filters: Dict[str, Any]) -> ReportResult:
    headers = [
        'ID OT', 'Cliente', 'Empresa', 'Tecnico', 'Estado', 'Tipo Trabajo',
        'Fecha Inicio', 'Fecha Fin', 'Comuna',
    ]
    qs = OrdenTrabajo.objects.filter(estado__in=ESTADOS_EJECUTADOS)
    if filters.get('fecha_desde'):
        qs = qs.filter(fecha_fin_ejecucion__gte=_aware_start(filters['fecha_desde']))
    if filters.get('fecha_hasta'):
        qs = qs.filter(fecha_fin_ejecucion__lte=_aware_end(filters['fecha_hasta']))
    qs = _filter_ordenes_fecha(qs, filters)
    rows = [
        [
            ot.id,
            ot.cliente.numero_cliente if ot.cliente else '',
            ot.cliente.empresa if ot.cliente else '',
            ot.tecnico_responsable.nombre_interno if ot.tecnico_responsable else '',
            ot.get_estado_display(),
            ot.get_tipo_trabajo_display(),
            ot.fecha_inicio_ejecucion.strftime('%Y-%m-%d %H:%M') if ot.fecha_inicio_ejecucion else '',
            ot.fecha_fin_ejecucion.strftime('%Y-%m-%d %H:%M') if ot.fecha_fin_ejecucion else '',
            ot.cliente.comuna if ot.cliente else '',
        ]
        for ot in qs.select_related('cliente', 'tecnico_responsable').order_by('-fecha_fin_ejecucion')
    ]
    return headers, rows


def report_trabajos_por_tecnico(filters: Dict[str, Any]) -> ReportResult:
    headers = ['Tecnico', 'Total Ejecutados', 'Pendientes', 'En Ejecucion']
    qs = OrdenTrabajo.objects.filter(tecnico_responsable__isnull=False)
    if filters.get('fecha_desde'):
        qs = qs.filter(fecha_creacion__gte=_aware_start(filters['fecha_desde']))
    if filters.get('fecha_hasta'):
        qs = qs.filter(fecha_creacion__lte=_aware_end(filters['fecha_hasta']))
    aggregated = (
        qs.values('tecnico_responsable__nombre_interno')
        .annotate(
            ejecutados=Count('id', filter=Q(estado__in=ESTADOS_EJECUTADOS)),
            pendientes=Count('id', filter=Q(estado__in=ESTADOS_PENDIENTES_OT)),
            en_ejecucion=Count('id', filter=Q(estado='EN_EJECUCION')),
        )
        .order_by('-ejecutados')
    )
    rows = [
        [item['tecnico_responsable__nombre_interno'], item['ejecutados'], item['pendientes'], item['en_ejecucion']]
        for item in aggregated
    ]
    return headers, rows


def report_trabajos_por_empresa(filters: Dict[str, Any]) -> ReportResult:
    headers = ['Empresa', 'Total OT', 'Ejecutadas', 'Pendientes']
    qs = OrdenTrabajo.objects.filter(cliente__isnull=False)
    qs = _filter_ordenes_fecha(qs, filters)
    if filters.get('empresa'):
        qs = qs.filter(cliente__empresa__icontains=filters['empresa'])
    aggregated = (
        qs.values('cliente__empresa')
        .annotate(
            total=Count('id'),
            ejecutadas=Count('id', filter=Q(estado__in=ESTADOS_EJECUTADOS)),
            pendientes=Count('id', filter=Q(estado__in=ESTADOS_PENDIENTES_OT)),
        )
        .order_by('-total')
    )
    rows = [
        [item['cliente__empresa'] or 'SIN EMPRESA', item['total'], item['ejecutadas'], item['pendientes']]
        for item in aggregated
    ]
    return headers, rows


def report_trabajos_pendientes_por_causa(filters: Dict[str, Any]) -> ReportResult:
    headers = ['Tipo Trabajo', 'Estado OT', 'Cantidad']
    qs = OrdenTrabajo.objects.filter(estado__in=ESTADOS_PENDIENTES_OT)
    qs = _filter_ordenes_fecha(qs, filters)
    aggregated = (
        qs.values('tipo_trabajo', 'estado')
        .annotate(cantidad=Count('id'))
        .order_by('-cantidad')
    )
    tipo_map = dict(OrdenTrabajo.TIPO_TRABAJO_CHOICES)
    estado_map = dict(OrdenTrabajo.ESTADO_CHOICES)
    rows = [
        [tipo_map.get(item['tipo_trabajo'], item['tipo_trabajo']), estado_map.get(item['estado'], item['estado']), item['cantidad']]
        for item in aggregated
    ]
    return headers, rows


def report_trabajos_diarios(filters: Dict[str, Any]) -> ReportResult:
    headers = ['Fecha', 'OT Creadas', 'OT Ejecutadas']
    qs = OrdenTrabajo.objects.all()
    if filters.get('fecha_desde'):
        qs = qs.filter(fecha_creacion__gte=_aware_start(filters['fecha_desde']))
    if filters.get('fecha_hasta'):
        qs = qs.filter(fecha_creacion__lte=_aware_end(filters['fecha_hasta']))
    creadas = qs.values('fecha_creacion__date').annotate(cantidad=Count('id')).order_by('fecha_creacion__date')
    ejecutadas_qs = OrdenTrabajo.objects.filter(estado__in=ESTADOS_EJECUTADOS, fecha_fin_ejecucion__isnull=False)
    if filters.get('fecha_desde'):
        ejecutadas_qs = ejecutadas_qs.filter(fecha_fin_ejecucion__gte=_aware_start(filters['fecha_desde']))
    if filters.get('fecha_hasta'):
        ejecutadas_qs = ejecutadas_qs.filter(fecha_fin_ejecucion__lte=_aware_end(filters['fecha_hasta']))
    ejecutadas = {
        item['fecha_fin_ejecucion__date']: item['cantidad']
        for item in ejecutadas_qs.values('fecha_fin_ejecucion__date').annotate(cantidad=Count('id'))
    }
    rows = [
        [item['fecha_creacion__date'].strftime('%Y-%m-%d'), item['cantidad'], ejecutadas.get(item['fecha_creacion__date'], 0)]
        for item in creadas
    ]
    return headers, rows


def report_resultado_diario_tecnico(filters: Dict[str, Any]) -> ReportResult:
    headers = ['Fecha', 'Tecnico', 'Ejecutadas', 'Pendientes']
    qs = OrdenTrabajo.objects.filter(tecnico_responsable__isnull=False)
    if filters.get('fecha_desde'):
        qs = qs.filter(fecha_fin_ejecucion__gte=_aware_start(filters['fecha_desde']))
    if filters.get('fecha_hasta'):
        qs = qs.filter(fecha_fin_ejecucion__lte=_aware_end(filters['fecha_hasta']))
    if filters.get('tecnico_id'):
        qs = qs.filter(tecnico_responsable_id=filters['tecnico_id'])
    aggregated = (
        qs.values('fecha_fin_ejecucion__date', 'tecnico_responsable__nombre_interno')
        .annotate(
            ejecutadas=Count('id', filter=Q(estado__in=ESTADOS_EJECUTADOS)),
            pendientes=Count('id', filter=Q(estado__in=ESTADOS_PENDIENTES_OT)),
        )
        .order_by('-fecha_fin_ejecucion__date')
    )
    rows = [
        [
            item['fecha_fin_ejecucion__date'].strftime('%Y-%m-%d') if item['fecha_fin_ejecucion__date'] else '',
            item['tecnico_responsable__nombre_interno'],
            item['ejecutadas'],
            item['pendientes'],
        ]
        for item in aggregated
    ]
    return headers, rows


def report_clientes_reincidentes(_filters: Dict[str, Any]) -> ReportResult:
    headers = ['Numero Cliente', 'Nombre', 'Comuna', 'Visitas 6 Meses']
    desde = six_month_window_start()
    aggregated = (
        OrdenTrabajo.objects.filter(fecha_creacion__date__gte=desde)
        .exclude(estado='CANCELADA')
        .values('cliente_id', 'cliente__numero_cliente', 'cliente__customer_name', 'cliente__comuna')
        .annotate(visitas=Count('id'))
        .filter(visitas__gt=2)
        .order_by('-visitas')
    )
    rows = [
        [item['cliente__numero_cliente'], item['cliente__customer_name'] or '', item['cliente__comuna'] or '', item['visitas']]
        for item in aggregated
    ]
    return headers, rows


def _clientes_por_valor_duplicado(campo: str) -> ReportResult:
    headers = ['Valor Duplicado', 'Numero Cliente', 'Nombre', 'Comuna']
    duplicados = (
        Cliente.objects.filter(activo=True)
        .exclude(**{f'{campo}__isnull': True})
        .exclude(**{campo: ''})
        .values(campo)
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list(campo, flat=True)
    )
    clientes = Cliente.objects.filter(activo=True, **{f'{campo}__in': list(duplicados)}).order_by(campo, 'numero_cliente')
    rows = [
        [getattr(cliente, campo), cliente.numero_cliente, cliente.customer_name or '', cliente.comuna or '']
        for cliente in clientes
    ]
    return headers, rows


def report_clientes_ip_duplicada(_filters: Dict[str, Any]) -> ReportResult:
    return _clientes_por_valor_duplicado('ip')


def report_clientes_medidor_duplicado(_filters: Dict[str, Any]) -> ReportResult:
    return _clientes_por_valor_duplicado('meter_serial_n_1')


def report_clientes_pendientes_stb(_filters: Dict[str, Any]) -> ReportResult:
    rows = [_cliente_row(c) for c in Cliente.objects.filter(activo=True, estado_stb='PENDIENTE').order_by('numero_cliente')]
    return CLIENTE_HEADERS, rows


def report_clientes_pendientes_sci4(_filters: Dict[str, Any]) -> ReportResult:
    rows = [_cliente_row(c) for c in Cliente.objects.filter(activo=True, estado_sci4='PENDIENTE').order_by('numero_cliente')]
    return CLIENTE_HEADERS, rows


def report_clientes_disciplina_mercado(_filters: Dict[str, Any]) -> ReportResult:
    qs = Cliente.objects.filter(activo=True).filter(
        Q(note__icontains='disciplina') | Q(trabajo__icontains='disciplina') | Q(note__icontains='mercado')
    ).order_by('numero_cliente')
    rows = [_cliente_row(c) for c in qs]
    return CLIENTE_HEADERS, rows


def report_clientes_sin_comunicacion(_filters: Dict[str, Any]) -> ReportResult:
    qs = Cliente.objects.filter(
        activo=True,
        estado_telemetria__in={'SIN_COMUNICACION', 'NO_COMUNICA'},
    ).order_by('numero_cliente')
    rows = [_cliente_row(c) for c in qs]
    return CLIENTE_HEADERS, rows


def report_clientes_sin_suministro(_filters: Dict[str, Any]) -> ReportResult:
    qs = Cliente.objects.filter(activo=True).filter(
        Q(tipo_suministro__isnull=True) | Q(tipo_suministro='') | Q(note__icontains='sin suministro')
    ).order_by('numero_cliente')
    rows = [_cliente_row(c) for c in qs]
    return CLIENTE_HEADERS, rows


def report_clientes_estado_visita(_filters: Dict[str, Any]) -> ReportResult:
    keywords = ['cerrado', 'deshabitado', 'no permite', 'no permite acceso']
    q = Q()
    for kw in keywords:
        q |= Q(trabajo__icontains=kw) | Q(note__icontains=kw)
    qs = Cliente.objects.filter(activo=True).filter(q).order_by('numero_cliente')
    headers = CLIENTE_HEADERS + ['Trabajo/Nota']
    rows = []
    for cliente in qs:
        row = _cliente_row(cliente)
        row.append((cliente.trabajo or '') + ' | ' + (cliente.note or ''))
        rows.append(row)
    return headers, rows


REPORT_CATALOG: Dict[str, Dict[str, Any]] = {
    'clientes_completos': {
        'title': 'Base completa de clientes',
        'description': 'Todos los clientes activos con ficha operativa.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_completos,
    },
    'clientes_ejecutados': {
        'title': 'Clientes ejecutados',
        'description': 'Clientes con al menos una OT ejecutada/validada.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_ejecutados,
    },
    'clientes_pendientes': {
        'title': 'Clientes pendientes',
        'description': 'Clientes con OT o revisión MoreApp pendiente.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_pendientes,
    },
    'ot_cerradas_sin_ejecutar': {
        'title': 'Órdenes cerradas sin ejecutar',
        'description': 'OT anuladas sin fecha de inicio de ejecución.',
        'supports_date_range': True,
        'supports_tecnico': True,
        'supports_empresa': False,
        'runner': report_ot_cerradas_sin_ejecutar,
    },
    'trabajos_por_fecha': {
        'title': 'Trabajos ejecutados por rango de fechas',
        'description': 'Detalle de OT ejecutadas en el período.',
        'supports_date_range': True,
        'supports_tecnico': True,
        'supports_empresa': True,
        'runner': report_trabajos_por_fecha,
    },
    'trabajos_por_tecnico': {
        'title': 'Trabajos ejecutados por técnico',
        'description': 'Resumen de productividad por técnico.',
        'supports_date_range': True,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_trabajos_por_tecnico,
    },
    'trabajos_por_empresa': {
        'title': 'Trabajos ejecutados por empresa',
        'description': 'Resumen de OT agrupadas por empresa del cliente.',
        'supports_date_range': True,
        'supports_tecnico': False,
        'supports_empresa': True,
        'runner': report_trabajos_por_empresa,
    },
    'trabajos_pendientes_causa': {
        'title': 'Trabajos pendientes por causa',
        'description': 'Agrupación por tipo de trabajo y estado OT.',
        'supports_date_range': True,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_trabajos_pendientes_por_causa,
    },
    'trabajos_diarios': {
        'title': 'Cantidad de trabajos diarios',
        'description': 'OT creadas y ejecutadas por día.',
        'supports_date_range': True,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_trabajos_diarios,
    },
    'resultado_diario_tecnico': {
        'title': 'Resultado diario por técnico',
        'description': 'Ejecutadas y pendientes por técnico y fecha.',
        'supports_date_range': True,
        'supports_tecnico': True,
        'supports_empresa': False,
        'runner': report_resultado_diario_tecnico,
    },
    'clientes_reincidentes': {
        'title': 'Clientes visitados más de 2 veces en 6 meses',
        'description': 'Reincidencia operativa por cliente.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_reincidentes,
    },
    'clientes_ip_duplicada': {
        'title': 'Clientes con IP repetida',
        'description': f'Total afectados: {count_clientes_con_ip_duplicada()}',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_ip_duplicada,
    },
    'clientes_medidor_duplicado': {
        'title': 'Clientes con medidor repetido',
        'description': f'Total afectados: {count_clientes_con_medidor_duplicado()}',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_medidor_duplicado,
    },
    'clientes_pendientes_stb': {
        'title': 'Clientes pendientes de actualización STB',
        'description': 'Estado StarBeat pendiente.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_pendientes_stb,
    },
    'clientes_pendientes_sci4': {
        'title': 'Clientes pendientes de actualización SCi4',
        'description': 'Estado SCi4 pendiente.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_pendientes_sci4,
    },
    'clientes_disciplina_mercado': {
        'title': 'Clientes derivados a Disciplina de Mercado',
        'description': 'Detectados por notas/trabajo con referencia a disciplina.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_disciplina_mercado,
    },
    'clientes_sin_comunicacion': {
        'title': 'Clientes sin comunicación',
        'description': 'Estado de telemetría sin comunicación.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_sin_comunicacion,
    },
    'clientes_sin_suministro': {
        'title': 'Clientes sin suministro',
        'description': 'Sin tipo de suministro o marcados en notas.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_sin_suministro,
    },
    'clientes_estado_visita': {
        'title': 'Clientes cerrados, deshabitados o sin acceso',
        'description': 'Detectados por trabajo/nota operativa.',
        'supports_date_range': False,
        'supports_tecnico': False,
        'supports_empresa': False,
        'runner': report_clientes_estado_visita,
    },
}


def run_report(slug: str, filters: Dict[str, Any]) -> ReportResult:
    meta = REPORT_CATALOG.get(slug)
    if not meta:
        raise KeyError(f'Reporte no encontrado: {slug}')
    runner: Callable = meta['runner']
    return runner(filters)
