from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponseBadRequest

from usuarios.models import Usuario
from web.decorators import role_required

from .exports import build_excel_response
from .services import REPORT_CATALOG, parse_report_filters, run_report


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_hub_view(request):
    filters = parse_report_filters(request.GET)
    catalog = []
    for slug, meta in REPORT_CATALOG.items():
        catalog.append({
            'slug': slug,
            'title': meta['title'],
            'description': meta['description'],
            'supports_date_range': meta['supports_date_range'],
            'supports_tecnico': meta['supports_tecnico'],
            'supports_empresa': meta['supports_empresa'],
        })

    return render(request, 'reportes/hub.html', {
        'catalog': catalog,
        'filters': request.GET,
        'tecnicos': Usuario.objects.filter(rol='TECNICO', is_active=True).order_by('nombre_interno'),
    })


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_export_view(request, slug):
    if slug not in REPORT_CATALOG:
        return HttpResponseBadRequest('Reporte no válido')

    filters = parse_report_filters(request.GET)
    headers, rows = run_report(slug, filters)
    filename = f'reporte_{slug}.xlsx'
    return build_excel_response(filename, headers, rows)
