from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
import logging

from usuarios.models import Usuario
from web.decorators import role_required

from .exports import build_excel_response, build_pdf_response
from .services import REPORT_CATALOG, parse_report_filters, run_report

logger = logging.getLogger(__name__)


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_hub_view(request):
    filters = parse_report_filters(request.GET)
    catalog = []
    total_filas = 0
    errores_reportes = []

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
            'supports_date_range': meta['supports_date_range'],
            'supports_tecnico': meta['supports_tecnico'],
            'supports_empresa': meta['supports_empresa'],
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

    return render(request, 'reportes/hub.html', {
        'catalog': catalog,
        'filters': request.GET,
        'tecnicos': Usuario.objects.filter(rol='TECNICO', is_active=True).order_by('nombre_interno'),
        'hay_actividad_operativa': tiene_actividad,
        'hay_datos_en_reportes': hay_datos_en_reportes,
        'total_filas_reportes': total_filas,
        'mostrar_catalogo': tiene_actividad and (hay_datos_en_reportes or bool(errores_reportes) or bool(catalog)),
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
