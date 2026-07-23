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

from .exports import PdfExportUnavailable, build_excel_response, build_pdf_response
from .services import REPORT_CATALOG, parse_report_filters, run_report

logger = logging.getLogger(__name__)


def _opciones_filtro_reportes():
    """Opciones reales para el hub (cacheadas; valores con sentido operativo)."""
    from reportes.operational_scope import clientes_operativos_qs

    def _calc():
        tecnico_ids = set(
            OrdenTrabajo.objects.filter(eliminado=False)
            .exclude(tecnico_responsable_id=None)
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
                OrdenTrabajo.objects.filter(eliminado=False)
                .exclude(cliente__empresa__isnull=True)
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
                OrdenTrabajo.objects.filter(eliminado=False)
                .exclude(cliente__comuna__isnull=True)
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
    """Hub de reportes con filtros y conteos por informe."""
    aviso_export = request.session.pop('reportes_aviso_export', None)
    if aviso_export:
        messages.warning(request, aviso_export)

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
        OrdenTrabajo.objects.filter(eliminado=False).exists() or clientes_operativos_qs().exists()
    )

    filtros_parseados = parse_report_filters(filters_raw) if hay_datos_exportables else {}

    def _conteos_catalogo():
        items = []
        for slug, meta in REPORT_CATALOG.items():
            row_count = None
            error = False
            try:
                if hay_datos_exportables and tiene_actividad:
                    _, rows = run_report(slug, filtros_parseados)
                    row_count = len(rows)
                elif hay_datos_exportables:
                    row_count = 0
            except Exception:
                logger.exception('Error calculando conteo reporte %s', slug)
                error = True
                row_count = None
            items.append({
                'slug': slug,
                'title': meta.get('title') or slug,
                'description': meta['description'],
                'supports_date_range': meta.get('supports_date_range', False),
                'supports_tecnico': meta.get('supports_tecnico', False),
                'supports_empresa': meta.get('supports_empresa', False),
                'supports_estado': meta.get('supports_estado', False),
                'supports_tipo': meta.get('supports_tipo', False),
                'supports_comuna': meta.get('supports_comuna', False),
                'row_count': row_count,
                'error': error,
            })
        return items

    cache_key = f'reportes:hub_conteos:{query or "all"}'
    if hay_datos_exportables:
        catalog = cache_get_or_set(cache_key, _conteos_catalogo, TTL_CORTO)
    else:
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
    tecnicos_ids = [t['id'] for t in opciones.get('tecnicos', [])]
    tecnicos = (
        Usuario.objects.filter(pk__in=tecnicos_ids).order_by('nombre_interno')
        if tecnicos_ids else Usuario.objects.none()
    )

    filtros_activos = any([
        request.GET.get('periodo'),
        request.GET.get('tecnico_id'),
        request.GET.get('empresa'),
        request.GET.get('estado_ot'),
        request.GET.get('tipo_trabajo'),
        request.GET.get('comuna'),
    ])

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
        'mostrar_catalogo': bool(hay_datos_exportables),
        'conteos_diferidos': False,
        'filtros_activos': filtros_activos,
        'total_registros_catalogo': sum(
            (item.get('row_count') or 0) for item in catalog if not item.get('error')
        ),
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
    # Alarmas de calidad (dashboard punto 7): siempre exportan sobre clientes activos,
    # aunque el hub de reportes operativos esté vacío.
    es_alarma_calidad = bool(meta.get('alarm_quality'))

    from reportes.operational_scope import hay_actividad_operativa
    try:
        if (not es_alarma_calidad) and (not hay_actividad_operativa()):
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
        try:
            return build_pdf_response(
                f'reporte_{slug}.pdf',
                headers,
                rows,
                title=titulo,
            )
        except PdfExportUnavailable as exc:
            logger.warning('Export PDF no disponible (%s); se entrega Excel.', exc)
            aviso = (
                f'{exc} Se descargó el reporte en Excel. '
                'Instala reportlab en el servidor para exportar PDF.'
            )
            # La descarga no renderiza HTML: dejar aviso para la próxima pantalla (hub u otra).
            request.session['reportes_aviso_export'] = aviso
            messages.warning(request, aviso)
            return build_excel_response(
                f'reporte_{slug}.xlsx',
                headers,
                rows,
                title=titulo,
                sheet_title=(titulo[:31] if titulo else 'Reporte'),
                group_by_first_column=slug in {
                    'clientes_ip_duplicada',
                    'clientes_medidor_duplicado',
                },
            )
    return build_excel_response(
        f'reporte_{slug}.xlsx',
        headers,
        rows,
        title=titulo,
        sheet_title=(titulo[:31] if titulo else 'Reporte'),
        group_by_first_column=slug in {
            'clientes_ip_duplicada',
            'clientes_medidor_duplicado',
        },
    )
