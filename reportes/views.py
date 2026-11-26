from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from urllib.parse import urlencode
import logging

from web.decorators import role_required

from .exports import PdfExportUnavailable, build_excel_response, build_pdf_response
from .services import REPORT_CATALOG, parse_report_filters, run_report

logger = logging.getLogger(__name__)


def _filtros_descarga(request):
    """Fecha, técnico y n° de cliente que viajan al Excel y al PDF."""
    params = {}
    for clave in ('fecha_desde', 'fecha_hasta', 'tecnico', 'num_cliente'):
        valor = (request.GET.get(clave) or '').strip()
        if valor:
            params[clave] = valor
    return urlencode(params)


def _conteo_registros(form_id, fecha_desde, fecha_hasta, num_cliente):
    """Total que informa MoreApp para la fecha y el cliente. El técnico se aplica al archivo."""
    from integraciones.moreapp_registros_views import _cargar_submissions

    try:
        _items, raw = _cargar_submissions(
            form_id,
            page=0,
            page_size=1,
            tecnico='',
            num_cliente=num_cliente,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    except Exception:
        logger.exception('No se pudo contar los registros del formulario %s', form_id)
        return None
    if not isinstance(raw, dict) or raw.get('totalSize') is None:
        return None
    try:
        return int(raw.get('totalSize'))
    except (TypeError, ValueError):
        return None


def _conteo_cacheado(form_id, fecha_desde, fecha_hasta, num_cliente):
    from web.perf_cache import TTL_CORTO, cache_get_or_set

    clave = 'reportes:conteo:%s:%s:%s:%s' % (form_id, fecha_desde, fecha_hasta, num_cliente)
    return cache_get_or_set(
        clave,
        lambda: _conteo_registros(form_id, fecha_desde, fecha_hasta, num_cliente),
        TTL_CORTO,
    )


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def reportes_hub_view(request):
    """Catálogo de informes de los formularios asignados. El admin ve todos."""
    session = getattr(request, 'session', None)
    aviso_export = session.pop('reportes_aviso_export', None) if session is not None else None
    if aviso_export:
        messages.warning(request, aviso_export)

    from integraciones.moreapp_formularios_views import contexto_formularios_asignados

    try:
        from integraciones.moreapp_api_ingest import ingest_asignados_si_corresponde
        from web.perf_cache import en_segundo_plano

        en_segundo_plano(lambda: ingest_asignados_si_corresponde(aplicar_operativo=False))
    except Exception:
        pass

    ve_todos = getattr(request.user, 'rol', '') == 'ADMIN'
    context = contexto_formularios_asignados(request, todos=ve_todos)
    asignado = (request.GET.get('asignado') or '').strip()
    if ve_todos and asignado:
        needle = asignado.casefold()
        context['formularios'] = [
            fila for fila in context.get('formularios') or []
            if any(needle in (nombre or '').casefold() for nombre in (fila.get('asignados') or []))
        ]
    fecha_desde = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta = (request.GET.get('fecha_hasta') or '').strip()
    tecnico = (request.GET.get('tecnico') or '').strip()
    num_cliente = (request.GET.get('num_cliente') or '').strip()
    formularios = context.get('formularios') or []
    total = 0
    if formularios:
        from concurrent.futures import ThreadPoolExecutor

        def _uno(fila):
            return _conteo_cacheado(fila.get('id') or '', fecha_desde, fecha_hasta, num_cliente)

        trabajadores = min(4, len(formularios))
        with ThreadPoolExecutor(max_workers=trabajadores) as pool:
            conteos = list(pool.map(_uno, formularios))
        for fila, conteo in zip(formularios, conteos):
            fila['row_count'] = conteo
            if conteo:
                total += conteo
    context.update({
        've_todos': ve_todos,
        'asignado': asignado,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'tecnico': tecnico,
        'num_cliente': num_cliente,
        'filtros_descarga': _filtros_descarga(request),
        'total_registros': total,
        'tiene_filtros': bool(
            context.get('query') or asignado or fecha_desde or fecha_hasta or tecnico or num_cliente
        ),
    })
    return render(request, 'reportes/hub.html', context)


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
