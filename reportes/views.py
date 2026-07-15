from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from urllib.parse import urlencode
import logging

from ordenes_trabajo.models import OrdenTrabajo
from usuarios.models import Usuario
from web.decorators import role_required

from .exports import build_excel_response, build_pdf_response
from .services import REPORT_CATALOG, parse_report_filters, run_report

logger = logging.getLogger(__name__)


def _opciones_filtro_reportes():
    """Opciones reales para el hub (solo valores con sentido operativo)."""
    from reportes.operational_scope import clientes_operativos_qs

    tecnico_ids = set(
        OrdenTrabajo.objects.exclude(tecnico_responsable_id=None)
        .values_list('tecnico_responsable_id', flat=True)
        .distinct()
    )
    tecnicos = Usuario.objects.filter(
        Q(rol='TECNICO', is_active=True) | Q(pk__in=tecnico_ids)
    ).order_by('nombre_interno')

    empresas = list(
        clientes_operativos_qs()
        .exclude(empresa__isnull=True)
        .exclude(empresa='')
        .order_by('empresa')
        .values_list('empresa', flat=True)
        .distinct()
    )
    if not empresas:
        empresas = list(
            OrdenTrabajo.objects.exclude(cliente__empresa__isnull=True)
            .exclude(cliente__empresa='')
            .order_by('cliente__empresa')
            .values_list('cliente__empresa', flat=True)
            .distinct()
        )

    comunas = list(
        clientes_operativos_qs()
        .exclude(comuna__isnull=True)
        .exclude(comuna='')
        .order_by('comuna')
        .values_list('comuna', flat=True)
        .distinct()
    )
    if not comunas:
        comunas = list(
            OrdenTrabajo.objects.exclude(cliente__comuna__isnull=True)
            .exclude(cliente__comuna='')
            .order_by('cliente__comuna')
            .values_list('cliente__comuna', flat=True)
            .distinct()
        )

    estados = list(OrdenTrabajo.ESTADO_CHOICES)
    tipos = list(OrdenTrabajo.TIPO_TRABAJO_CHOICES)

    return {
        'tecnicos': tecnicos,
        'empresas': empresas,
        'comunas': comunas,
        'estados_ot': estados,
        'tipos_trabajo': tipos,
    }


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_hub_view(request):
    filters = parse_report_filters(request.GET)
    catalog = []
    total_filas = 0
    errores_reportes = []
    query = urlencode({
        k: v for k, v in {
            'fecha_desde': request.GET.get('fecha_desde', ''),
            'fecha_hasta': request.GET.get('fecha_hasta', ''),
            'tecnico_id': request.GET.get('tecnico_id', ''),
            'empresa': request.GET.get('empresa', ''),
            'estado_ot': request.GET.get('estado_ot', ''),
            'tipo_trabajo': request.GET.get('tipo_trabajo', ''),
            'comuna': request.GET.get('comuna', ''),
        }.items() if v
    })

    for slug, meta in REPORT_CATALOG.items():
        title = meta.get('title') or slug
        had_error = False
        try:
            _, rows = run_report(slug, filters)
            row_count = len(rows)
        except Exception:
            logger.exception('Error generando reporte %s en hub', slug)
            row_count = 0
            had_error = True
            errores_reportes.append(title)

        total_filas += row_count
        catalog.append({
            'slug': slug,
            'title': title,
            'description': meta['description'],
            'supports_date_range': meta.get('supports_date_range', False),
            'supports_tecnico': meta.get('supports_tecnico', False),
            'supports_empresa': meta.get('supports_empresa', False),
            'supports_estado': meta.get('supports_estado', False),
            'supports_tipo': meta.get('supports_tipo', False),
            'supports_comuna': meta.get('supports_comuna', False),
            'row_count': row_count,
            'error': had_error,
        })

    if errores_reportes:
        messages.warning(
            request,
            'Algunos reportes no pudieron generarse: '
            + '; '.join(errores_reportes[:5])
            + ('…' if len(errores_reportes) > 5 else ''),
        )

    from reportes.operational_scope import hay_actividad_operativa

    tiene_actividad = hay_actividad_operativa()
    hay_datos_en_reportes = total_filas > 0
    opciones = _opciones_filtro_reportes()

    return render(request, 'reportes/hub.html', {
        'catalog': catalog,
        'filters': request.GET,
        'filter_query': query,
        'tecnicos': opciones['tecnicos'],
        'empresas': opciones['empresas'],
        'comunas': opciones['comunas'],
        'estados_ot': opciones['estados_ot'],
        'tipos_trabajo': opciones['tipos_trabajo'],
        'hay_actividad_operativa': tiene_actividad,
        'hay_datos_en_reportes': hay_datos_en_reportes,
        'total_filas_reportes': total_filas,
        'mostrar_catalogo': tiene_actividad and (hay_datos_en_reportes or bool(errores_reportes)),
        'filtros_activos': any([
            request.GET.get('fecha_desde'),
            request.GET.get('fecha_hasta'),
            request.GET.get('tecnico_id'),
            request.GET.get('empresa'),
            request.GET.get('estado_ot'),
            request.GET.get('tipo_trabajo'),
            request.GET.get('comuna'),
        ]),
    })


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_export_view(request, slug):
    if slug not in REPORT_CATALOG:
        return HttpResponseBadRequest('Reporte no válido')

    formato = (request.GET.get('formato') or 'excel').strip().lower()
    if formato not in ('excel', 'pdf', 'xlsx'):
        return HttpResponseBadRequest('Formato no válido. Use excel o pdf.')
    if formato == 'xlsx':
        formato = 'excel'

    meta = REPORT_CATALOG[slug]
    titulo = meta.get('title') or slug

    from reportes.operational_scope import hay_actividad_operativa
    try:
        if not hay_actividad_operativa():
            headers, rows = run_report(slug, {})
            rows = []
        else:
            filters = parse_report_filters(request.GET)
            headers, rows = run_report(slug, filters)
    except Exception:
        logger.exception('Error exportando reporte %s formato=%s', slug, formato)
        messages.error(
            request,
            f'No se pudo generar el {formato.upper()} de este reporte. Revisa los logs del servidor.',
        )
        return redirect('reportes_hub')

    if formato == 'pdf':
        return build_pdf_response(
            f'reporte_{slug}.pdf',
            headers,
            rows,
            title=titulo,
        )
    return build_excel_response(f'reporte_{slug}.xlsx', headers, rows)
