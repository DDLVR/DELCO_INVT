from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import render

from usuarios.models import Usuario
from web.decorators import role_required

from .exports import build_excel_response
from .services import REPORT_CATALOG, parse_report_filters, run_report


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_hub_view(request):
    filters = parse_report_filters(request.GET)
    catalog = []
    total_filas = 0
    for slug, meta in REPORT_CATALOG.items():
        _, rows = run_report(slug, filters)
        row_count = len(rows)
        total_filas += row_count
        catalog.append({
            'slug': slug,
            'title': meta['title'],
            'description': meta['description'],
            'supports_date_range': meta['supports_date_range'],
            'supports_tecnico': meta['supports_tecnico'],
            'supports_empresa': meta['supports_empresa'],
            'row_count': row_count,
        })

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
        'mostrar_catalogo': tiene_actividad and hay_datos_en_reportes,
    })


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_export_view(request, slug):
    if slug not in REPORT_CATALOG:
        return HttpResponseBadRequest('Reporte no válido')

    from reportes.operational_scope import hay_actividad_operativa
    if not hay_actividad_operativa():
        headers, rows = run_report(slug, {})
        return build_excel_response(f'reporte_{slug}.xlsx', headers, [])

    filters = parse_report_filters(request.GET)
    headers, rows = run_report(slug, filters)
    filename = f'reporte_{slug}.xlsx'
    return build_excel_response(filename, headers, rows)
