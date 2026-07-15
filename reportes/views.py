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
from web.perf_cache import cache_get_or_set, TTL_CORTO

from .exports import build_excel_response, build_pdf_response
from .services import REPORT_CATALOG, parse_report_filters, run_report

logger = logging.getLogger(__name__)


def _opciones_filtro_reportes():
    """Opciones reales para el hub (cacheadas; valores con sentido operativo)."""
    from reportes.operational_scope import clientes_operativos_qs

    def _calc():
        tecnico_ids = set(
            OrdenTrabajo.objects.exclude(tecnico_responsable_id=None)
            .values_list('tecnico_responsable_id', flat=True)
            .distinct()
        )
        tecnicos = list(
            Usuario.objects.filter(
                Q(rol='TECNICO', is_active=True) | Q(pk__in=tecnico_ids)
            ).order_by('nombre_interno').values('id', 'nombre_interno')
        )

        empresas = list(
            clientes_operativos_qs()
            .exclude(empresa__isnull=True)
            .exclude(empresa='')
            .order_by('empresa')
            .values_list('empresa', flat=True)
            .distinct()[:200]
        )
        if not empresas:
            empresas = list(
                OrdenTrabajo.objects.exclude(cliente__empresa__isnull=True)
                .exclude(cliente__empresa='')
                .order_by('cliente__empresa')
                .values_list('cliente__empresa', flat=True)
                .distinct()[:200]
            )

        comunas = list(
            clientes_operativos_qs()
            .exclude(comuna__isnull=True)
            .exclude(comuna='')
            .order_by('comuna')
            .values_list('comuna', flat=True)
            .distinct()[:200]
        )
        if not comunas:
            comunas = list(
                OrdenTrabajo.objects.exclude(cliente__comuna__isnull=True)
                .exclude(cliente__comuna='')
                .order_by('cliente__comuna')
                .values_list('cliente__comuna', flat=True)
                .distinct()[:200]
            )

        return {
            'tecnicos': tecnicos,
            'empresas': empresas,
            'comunas': comunas,
            'estados_ot': list(OrdenTrabajo.ESTADO_CHOICES),
            'tipos_trabajo': list(OrdenTrabajo.TIPO_TRABAJO_CHOICES),
        }

    return cache_get_or_set('reportes:opciones_filtro', _calc, TTL_CORTO)


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_hub_view(request):
    """
    Hub liviano: no ejecuta los 19 reportes en cada carga.
    Los conteos se calculan solo al exportar o vía endpoint puntual.
    """
    filters_raw = request.GET
    query = urlencode({
        k: v for k, v in {
            'periodo': filters_raw.get('periodo', ''),
            'tecnico_id': filters_raw.get('tecnico_id', ''),
            'empresa': filters_raw.get('empresa', ''),
            'estado_ot': filters_raw.get('estado_ot', ''),
            'tipo_trabajo': filters_raw.get('tipo_trabajo', ''),
            'comuna': filters_raw.get('comuna', ''),
        }.items() if v
    })

    from reportes.operational_scope import hay_actividad_operativa, clientes_operativos_qs

    tiene_actividad = hay_actividad_operativa()
    # Catálogo solo si hay OT o clientes operativos linkeados (MoreApp huérfano no basta)
    hay_datos_exportables = (
        OrdenTrabajo.objects.exists() or clientes_operativos_qs().exists()
    )

    catalog = []
    for slug, meta in REPORT_CATALOG.items():
        catalog.append({
            'slug': slug,
            'title': meta.get('title') or slug,
            'description': meta['description'],
            'supports_date_range': meta.get('supports_date_range', False),
            'supports_tecnico': meta.get('supports_tecnico', False),
            'supports_empresa': meta.get('supports_empresa', False),
            'supports_estado': meta.get('supports_estado', False),
            'supports_tipo': meta.get('supports_tipo', False),
            'supports_comuna': meta.get('supports_comuna', False),
            'row_count': None,
            'error': False,
        })

    opciones = _opciones_filtro_reportes()
    # Reconstruir queryset liviano de técnicos desde cache de dicts
    tecnicos_ids = [t['id'] for t in opciones.get('tecnicos', [])]
    tecnicos = Usuario.objects.filter(pk__in=tecnicos_ids).order_by('nombre_interno') if tecnicos_ids else Usuario.objects.none()

    return render(request, 'reportes/hub.html', {
        'catalog': catalog,
        'filters': request.GET,
        'filter_query': query,
        'tecnicos': tecnicos,
        'empresas': opciones.get('empresas', []),
        'comunas': opciones.get('comunas', []),
        'estados_ot': opciones.get('estados_ot', []),
        'tipos_trabajo': opciones.get('tipos_trabajo', []),
        'hay_actividad_operativa': tiene_actividad,
        'hay_datos_en_reportes': hay_datos_exportables,
        'total_filas_reportes': None,
        'mostrar_catalogo': bool(hay_datos_exportables),
        'conteos_diferidos': True,
        'filtros_activos': any([
            request.GET.get('periodo'),
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
