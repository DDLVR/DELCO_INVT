
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import models
from inventario.models import MovimientoInventario, MovimientoItem, Ubicacion, Medidor, SimCard, Modem
from django.views.decorators.http import require_POST
from django.conf import settings
from .decorators import admin_or_administrativo

@login_required
@admin_or_administrativo
@require_POST
def inventario_eliminar_view(request, pk):
    """Soft-delete de equipo: oculta en inventario y deja snapshot en movimientos."""
    from web.services.eliminaciones import (
        ENTIDAD_MEDIDOR,
        ENTIDAD_MODEM,
        ENTIDAD_SIM,
        registrar_eliminacion,
    )

    tipo = request.POST.get('tipo', 'medidor')
    motivo = request.POST.get('motivo', '').strip()
    try:
        if tipo == 'medidor':
            equipo = get_object_or_404(Medidor, pk=pk, eliminado=False)
            entidad = ENTIDAD_MEDIDOR
        elif tipo == 'sim':
            equipo = get_object_or_404(SimCard, pk=pk, eliminado=False)
            entidad = ENTIDAD_SIM
        elif tipo == 'modem':
            equipo = get_object_or_404(Modem, pk=pk, eliminado=False)
            entidad = ENTIDAD_MODEM
        else:
            return JsonResponse({'success': False, 'message': 'Tipo de equipo no válido'})

        _, creado = registrar_eliminacion(
            entidad,
            equipo,
            request.user,
            motivo=motivo,
            crear_item_inventario=True,
        )
        if not creado:
            return JsonResponse({'success': False, 'message': 'El equipo ya estaba eliminado'})
        return JsonResponse({
            'success': True,
            'message': f'{tipo.capitalize()} eliminado. Quedó registrado en Movimientos.',
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Error al eliminar: {str(e)}'})
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count
import json
import ast
import re
import logging
import traceback
import hmac
from io import BytesIO
from datetime import datetime
from urllib.parse import quote_plus
from .decorators import role_required, admin_or_administrativo
from inventario.models import Medidor, SimCard, Modem, EstadoInventario, Ubicacion
from clientes.models import Cliente
from importaciones.utils import (
    importar_equipos_excel,
    importar_clientes_excel,
    exportar_equipos_excel,
    exportar_equipos_excel_completo,
    exportar_clientes_excel,
    exportar_clientes_excel_completo,
)
from importaciones.models import ImportacionExcel, ImportacionExcelError
from web.services.validators import (
    merge_issues,
    normalize_ip_value,
    validate_ip_duplicate_on_active_clients,
    validate_ip_format,
    validate_ip_port_coherence,
    validate_ip_restricted_status,
    validate_meter_required_fields,
    validate_meter_uniqueness,
    validate_modem_assignment,
    validate_modem_inventory_status,
    validate_restriccion_con_justificacion,
)
from web.services.dashboard_metrics import (
    build_panel_alarmas_analistas,
    count_clientes_con_ip_duplicada,
    count_clientes_con_medidor_duplicado,
    count_clientes_sin_actualizacion_sci4,
    count_clientes_sin_actualizacion_stb,
)
from web.services.audit import AuditEvent, audit_field_changes, register_audit_event

logger = logging.getLogger(__name__)


def _ordenes_trabajo_habilitadas():
    return getattr(settings, 'ORDENES_TRABAJO_HABILITADAS', True)


def _extraer_submission_moreapp(observacion: str) -> str:
    """Saca el submission id desde la observación de un movimiento MOREAPP."""
    if not observacion:
        return ''
    match = re.search(r'submission:\s*([a-f0-9]+)', str(observacion), re.IGNORECASE)
    return match.group(1).strip() if match else ''


def _tipo_movimiento_desde_estado(estado_nombre):
    """Mapea estado de inventario a tipo de movimiento Kardex."""
    nombre = (estado_nombre or '').strip().lower()
    if 'bodega' in nombre:
        return 'RECEPCION'
    if 'instal' in nombre:
        return 'INSTALACION'
    if 'retir' in nombre or 'baja' in nombre:
        return 'RETIRO'
    if 'repar' in nombre:
        return 'DEVOLUCION'
    return 'ENTREGA'


def _obtener_estado_inventario(nombre, descripcion=''):
    estado, _ = EstadoInventario.objects.get_or_create(
        nombre=nombre,
        defaults={'descripcion': descripcion},
    )
    return estado


def _registrar_movimiento_inventario(
    equipo,
    tipo_item,
    usuario,
    observacion,
    tipo_movimiento=None,
    origen=None,
    destino=None,
):
    """Registra movimiento en Kardex para cambios de inventario."""
    ubicacion_actual = getattr(equipo, 'ubicacion_actual', None)
    if ubicacion_actual is None:
        ubicacion_actual = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
    if ubicacion_actual is None:
        ubicacion_actual = Ubicacion.objects.create(tipo='BODEGA_DELCO', nombre='Bodega Principal')

    origen_mov = origen or ubicacion_actual
    destino_mov = destino or ubicacion_actual

    if not tipo_movimiento:
        estado_nombre = equipo.estado_inventario.nombre if getattr(equipo, 'estado_inventario', None) else ''
        tipo_movimiento = _tipo_movimiento_desde_estado(estado_nombre)

    movimiento = MovimientoInventario.objects.create(
        tipo=tipo_movimiento,
        origen=origen_mov,
        destino=destino_mov,
        responsable=usuario,
        observacion=observacion,
    )

    item_kwargs = {
        'movimiento': movimiento,
        'tipo_equipo': tipo_item,
        'cantidad': 1,
    }
    if tipo_item == 'MEDIDOR':
        item_kwargs['medidor'] = equipo
    elif tipo_item == 'SIM':
        item_kwargs['simcard'] = equipo
    elif tipo_item == 'MODEM':
        item_kwargs['modem'] = equipo

    MovimientoItem.objects.create(**item_kwargs)


@csrf_exempt
def login_view(request):
    """Autenticación de usuarios con RUT"""
    # Si ya está logueado, no mostrar login
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == "POST":
        rut = request.POST.get("username")  # RUT
        password = request.POST.get("password")
        # Limpiar el RUT: quitar puntos y guion
        rut_limpio = rut.replace('.', '').replace('-', '').upper()
        from usuarios.models import Usuario
        try:
            # Buscar usuario por rut en ambos formatos
            usuario = Usuario.objects.filter(rut=rut).first()
            if not usuario:
                usuario = Usuario.objects.filter(rut=rut_limpio).first()
            if not usuario:
                messages.error(request, "RUT no encontrado en el sistema.")
            else:
                # Intentar autenticar
                user = authenticate(request, username=usuario.rut, password=password)
                if user is not None:
                    login(request, user)
                    request.session.cycle_key()
                    request.session['auth_login_ts'] = int(datetime.now().timestamp())
                    request.session.set_expiry(int(getattr(settings, 'ABSOLUTE_SESSION_TIMEOUT_SECONDS', 28800)))
                    messages.success(request, f"Bienvenido {usuario.nombre_interno}!")
                    return redirect('dashboard')
                else:
                    messages.error(request, "Contraseña incorrecta.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, "auth/login.html")


def logout_view(request):
    """Cierre de sesión"""
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    """Dashboard principal - redirige según rol"""
    
    rol = request.user.rol
    context = {
        'rol': rol,
        'usuario': request.user,
        'ordenes_habilitadas': _ordenes_trabajo_habilitadas(),
        'moreapp_auto_refresh_seconds': int(getattr(settings, 'MOREAPP_AUTO_REFRESH_SECONDS', 300) or 300),
    }
    
    # ADMIN y ADMINISTRATIVO: Vista general de todo
    if rol in ['ADMIN', 'ADMINISTRATIVO']:
        sync_stats = _ejecutar_autosync_moreapp_si_corresponde()
        if sync_stats and int(sync_stats.get('nuevos') or 0) > 0:
            messages.info(
                request,
                f'LLegaron {sync_stats["nuevos"]} informe(s) MoreApp nuevos. '
                'Revise la cola de pendientes para validar el trabajo.',
            )

        if _ordenes_trabajo_habilitadas():
            from ordenes_trabajo.models import OrdenTrabajo, IntegracionMoreApp
            from ordenes_trabajo.services import six_month_window_start
            from ordenes_trabajo.utils import contadores_colas_ordenes
            from reportes.services import ESTADOS_PENDIENTES_OT

            ot_qs = OrdenTrabajo.objects.filter(eliminado=False)
            context['total_ordenes'] = ot_qs.count()
            context['ordenes_pendientes'] = ot_qs.filter(estado__in=ESTADOS_PENDIENTES_OT).count()
            # Cerradas = validadas/finalizadas (no confundir con post-MoreApp)
            context['ordenes_completadas'] = ot_qs.filter(
                estado__in={'VALIDADA', 'FINALIZADA', 'REALIZADA'}
            ).count()
            context['ordenes_por_validar'] = ot_qs.filter(
                estado__in={'REALIZADA_PENDIENTE_COMPROBACION', 'PENDIENTE_VALIDACION'}
            ).count()
            context['ordenes_canceladas'] = ot_qs.filter(estado='CANCELADA').count()
            context['ordenes_cerradas_sin_ejecutar'] = ot_qs.filter(
                estado='CANCELADA',
                fecha_inicio_ejecucion__isnull=True,
            ).count()
            context['ot_colas'] = contadores_colas_ordenes(ot_qs)
            context['moreapp_sin_ot'] = IntegracionMoreApp.objects.filter(
                orden__isnull=True,
                eliminado=False,
            ).exclude(estado_sincronizacion__in=('ERROR_JSON', 'ERROR_LECTURA', 'ERROR')).count()
            context['clientes_reincidentes'] = (
                OrdenTrabajo.objects.filter(
                    eliminado=False,
                    fecha_creacion__date__gte=six_month_window_start(),
                )
                .exclude(estado='CANCELADA')
                .values('cliente_id')
                .annotate(visitas=Count('id'))
                .filter(visitas__gt=2)
                .count()
            )
        else:
            context['total_ordenes'] = 0
            context['ordenes_pendientes'] = 0
            context['ordenes_completadas'] = 0
            context['ordenes_por_validar'] = 0
            context['ordenes_canceladas'] = 0
            context['ordenes_cerradas_sin_ejecutar'] = 0
            context['ot_colas'] = {}
            context['moreapp_sin_ot'] = 0
            context['clientes_reincidentes'] = 0

        from web.perf_cache import cache_get_or_set, TTL_CORTO

        def _alarmas_panel():
            return build_panel_alarmas_analistas()

        alarmas = cache_get_or_set('dashboard:alarmas_analistas', _alarmas_panel, TTL_CORTO)
        context['alarmas_analistas'] = alarmas
        context['alarmas_analistas_activas'] = sum(1 for a in alarmas if int(a.get('count') or 0) > 0)
        context['clientes_ip_duplicada'] = next((a['count'] for a in alarmas if a['key'] == 'ip_duplicada'), 0)
        context['clientes_medidor_duplicado'] = next((a['count'] for a in alarmas if a['key'] == 'medidor_duplicado'), 0)
        context['clientes_pendientes_stb'] = next((a['count'] for a in alarmas if a['key'] == 'pendiente_stb'), 0)
        context['clientes_pendientes_sci4'] = next((a['count'] for a in alarmas if a['key'] == 'pendiente_sci4'), 0)
        
        # Usuarios
        def _kpis_inventario_dashboard():
            return {
                'usuarios_activos': request.user.__class__.objects.filter(is_active=True).count(),
                'total_tecnicos': request.user.__class__.objects.filter(rol='TECNICO', is_active=True).count(),
                'total_administrativos': request.user.__class__.objects.filter(rol='ADMINISTRATIVO', is_active=True).count(),
                'total_medidores': Medidor.objects.filter(eliminado=False).count(),
                'medidores_bodega': Medidor.objects.filter(eliminado=False, estado_inventario__nombre='En bodega').count(),
                'medidores_instalados': Medidor.objects.filter(eliminado=False, estado_inventario__nombre='Instalado').count(),
                'total_sims': SimCard.objects.filter(eliminado=False).count(),
                'sims_bodega': SimCard.objects.filter(eliminado=False, estado_inventario__nombre='En bodega').count(),
                'sims_instaladas': SimCard.objects.filter(eliminado=False, estado_inventario__nombre='Instalado').count(),
                'total_modems': Modem.objects.filter(eliminado=False).count(),
                'modems_bodega': Modem.objects.filter(eliminado=False, estado_inventario__nombre='En bodega').count(),
                'modems_instalados': Modem.objects.filter(eliminado=False, estado_inventario__nombre='Instalado').count(),
                'total_clientes': (
                    Cliente.objects.filter(activo=True)
                    .exclude(numero_cliente__in=['', '0'])
                    .values('numero_cliente')
                    .distinct()
                    .count()
                ),
                'medidores_por_estado': list(
                    Medidor.objects.filter(eliminado=False).values('estado_inventario__nombre')
                    .annotate(cantidad=Count('id'))
                    .order_by('-cantidad')[:5]
                ),
                'sims_por_estado': list(
                    SimCard.objects.filter(eliminado=False).values('estado_inventario__nombre')
                    .annotate(cantidad=Count('id'))
                    .order_by('-cantidad')[:5]
                ),
                'modems_por_estado': list(
                    Modem.objects.filter(eliminado=False).values('estado_inventario__nombre')
                    .annotate(cantidad=Count('id'))
                    .order_by('-cantidad')[:5]
                ),
                'movimientos_tipo_breakdown': list(
                    MovimientoInventario.objects.values('tipo')
                    .annotate(c=Count('id'))
                    .order_by('-c')
                ),
                'movimientos_origen_breakdown': list(
                    MovimientoInventario.objects.values('origen_sistema')
                    .annotate(c=Count('id'))
                    .order_by('-c')
                ),
            }

        inv = cache_get_or_set('dashboard:admin_inv_kpis', _kpis_inventario_dashboard, TTL_CORTO)
        context.update(inv)

        # Calcular porcentajes para barras de progreso (evitar división por cero)
        context['medidores_instalados_pct'] = round((context['medidores_instalados'] / context['total_medidores'] * 100) if context['total_medidores'] > 0 else 0)
        context['medidores_bodega_pct'] = round((context['medidores_bodega'] / context['total_medidores'] * 100) if context['total_medidores'] > 0 else 0)
        
        context['sims_instaladas_pct'] = round((context['sims_instaladas'] / context['total_sims'] * 100) if context['total_sims'] > 0 else 0)
        context['sims_bodega_pct'] = round((context['sims_bodega'] / context['total_sims'] * 100) if context['total_sims'] > 0 else 0)
        
        context['modems_instalados_pct'] = round((context['modems_instalados'] / context['total_modems'] * 100) if context['total_modems'] > 0 else 0)
        context['modems_bodega_pct'] = round((context['modems_bodega'] / context['total_modems'] * 100) if context['total_modems'] > 0 else 0)
        
        # Movimientos de inventario (últimos 7 días)
        from datetime import timedelta
        from django.utils import timezone
        ahora = timezone.now()
        fecha_hace_7_dias = ahora - timedelta(days=7)

        context['movimientos_recientes'] = MovimientoInventario.objects.filter(
            fecha_hora__gte=fecha_hace_7_dias
        ).count()
        context['movimientos_hoy'] = MovimientoInventario.objects.filter(
            fecha_hora__date=timezone.localdate()
        ).count()

        # Indicadores operativos (Puntos 6 y 11) — mismos criterios que el banner/badge
        try:
            from ordenes_trabajo.models import IntegracionMoreApp
            from web.moreapp_avisos import _conteos_globales_aviso

            aviso_conteos = _conteos_globales_aviso()
            context['moreapp_pendientes'] = int(aviso_conteos.get('pendientes') or 0)
            context['moreapp_con_advertencia'] = int(aviso_conteos.get('advertencias') or 0)
            # Envejecimiento: registros con revisión pendiente > 7 días (Punto 11)
            umbral_7d = ahora - timedelta(days=7)
            context['moreapp_envejecidos'] = IntegracionMoreApp.objects.filter(
                estado_revision='PENDIENTE',
                eliminado=False,
                fecha_recepcion__lt=umbral_7d,
            ).count()
            context['moreapp_sinc_breakdown'] = list(
                IntegracionMoreApp.objects.filter(eliminado=False)
                .values('estado_sincronizacion')
                .annotate(c=Count('id'))
                .order_by('-c')
            )
            context['moreapp_formulario_breakdown'] = list(
                IntegracionMoreApp.objects.filter(eliminado=False)
                .values('nombre_formulario')
                .annotate(c=Count('id'))
                .order_by('-c')
            )
            context['moreapp_adv_breakdown'] = _calcular_adv_breakdown(IntegracionMoreApp)
        except Exception:
            context['moreapp_pendientes'] = 0
            context['moreapp_con_advertencia'] = 0
            context['moreapp_envejecidos'] = 0
            context['moreapp_sinc_breakdown'] = []
            context['moreapp_formulario_breakdown'] = []
            context['moreapp_adv_breakdown'] = []

        return render(request, 'dashboards/admin_dashboard.html', context)
    elif rol == 'TECNICO':
        from ordenes_trabajo.models import OrdenTrabajo
        mis_ordenes_qs = OrdenTrabajo.objects.filter(tecnico_responsable=request.user)
        context['mis_ordenes'] = mis_ordenes_qs.order_by('-fecha_creacion')[:10]
        context['en_ejecucion'] = mis_ordenes_qs.filter(estado='EN_EJECUCION').count()
        context['finalizadas'] = mis_ordenes_qs.filter(
            estado__in={'REALIZADA', 'VALIDADA', 'FINALIZADA'}
        ).count()
        return render(request, 'dashboards/tecnico_dashboard.html', context)
    
    # GERENCIA: KPIs y reportes
    elif rol == 'GERENCIA':
        from ordenes_trabajo.models import OrdenTrabajo
        total = OrdenTrabajo.objects.count()
        finalizadas = OrdenTrabajo.objects.filter(
            estado__in={'REALIZADA', 'VALIDADA', 'FINALIZADA'}
        ).count()
        context['ordenes_finalizadas'] = finalizadas
        context['tasa_cumplimiento'] = f'{round((finalizadas / total) * 100) if total else 0}%'
        context['clientes_ip_duplicada'] = count_clientes_con_ip_duplicada()
        context['clientes_medidor_duplicado'] = count_clientes_con_medidor_duplicado()
        return render(request, 'dashboards/gerencia_dashboard.html', context)
    
    # AUDITOR: Auditoría y logs
    elif rol == 'AUDITOR':
        from ordenes_trabajo.models import OrdenTrabajo
        context['ultimas_ordenes'] = OrdenTrabajo.objects.select_related(
            'cliente', 'tecnico_responsable'
        ).order_by('-fecha_creacion')[:10]
        context['clientes_ip_duplicada'] = count_clientes_con_ip_duplicada()
        context['clientes_medidor_duplicado'] = count_clientes_con_medidor_duplicado()
        return render(request, 'dashboards/auditor_dashboard.html', context)
    
    # Default
    return render(request, 'dashboard.html', context)


# ========== VISTAS OPERATIVAS (Puntos 2, 8, 9, 11) ==========

def _contadores_pendientes_moreapp():
    """Contadores de la cola operativa MoreApp (excluye soft-deleted)."""
    from ordenes_trabajo.models import IntegracionMoreApp
    from django.utils import timezone
    from datetime import timedelta

    qs_activos = IntegracionMoreApp.objects.filter(eliminado=False)
    umbral_7d = timezone.now() - timedelta(days=7)
    # Críticas solo cuentan si aún requieren revisión operativa
    critica_qs = qs_activos.filter(
        descripcion_alerta__icontains='ALERTA_CRITICA',
        estado_revision__in=('PENDIENTE', 'CON_ADVERTENCIA'),
    )
    return {
        'PENDIENTE': qs_activos.filter(estado_revision='PENDIENTE').count(),
        'CON_ADVERTENCIA': qs_activos.filter(estado_revision='CON_ADVERTENCIA').count(),
        'REVISADO': qs_activos.filter(estado_revision='REVISADO').count(),
        'DESCARTADO': qs_activos.filter(estado_revision='DESCARTADO').count(),
        'CRITICA': critica_qs.count(),
        'envejecidos': qs_activos.filter(
            estado_revision='PENDIENTE', fecha_recepcion__lt=umbral_7d
        ).count(),
    }


@role_required(['ADMIN', 'ADMINISTRATIVO'])
def pendientes_operativos_view(request):
    """
    Punto 2: Cola formal de operaciones pendientes de revisión (MoreApp).
    Incluye indicadores de envejecimiento (Punto 11).
    """
    from ordenes_trabajo.models import IntegracionMoreApp
    from django.utils import timezone
    from datetime import timedelta
    from web.moreapp_avisos import marcar_aviso_moreapp_visto

    marcar_aviso_moreapp_visto(request)

    estado = request.GET.get('estado', 'PENDIENTE')
    if estado not in ('PENDIENTE', 'CON_ADVERTENCIA', 'REVISADO', 'DESCARTADO', 'CRITICA', 'TODOS'):
        estado = 'PENDIENTE'

    qs = (
        IntegracionMoreApp.objects.filter(eliminado=False)
        .select_related('procesado_por')
        .order_by('-fecha_recepcion')
    )
    if estado == 'CRITICA':
        qs = qs.filter(
            descripcion_alerta__icontains='ALERTA_CRITICA',
            estado_revision__in=('PENDIENTE', 'CON_ADVERTENCIA'),
        )
    elif estado != 'TODOS':
        qs = qs.filter(estado_revision=estado)

    ahora = timezone.now()
    umbral_7d = ahora - timedelta(days=7)
    contadores = _contadores_pendientes_moreapp()

    registros = list(qs[:200])
    for reg in registros:
        bloqueos = _extraer_bloqueos_operativos_registro(reg)
        reg.bloqueos_operativos = bloqueos
        reg.bloqueo_operativo_preview = bloqueos[0]['motivo'] if bloqueos else ''
        reg.es_alerta_critica = (
            'ALERTA_CRITICA' in str(reg.descripcion_alerta or '').upper()
            or any(b.get('es_critica') for b in bloqueos)
        )
        reg.alerta_preview = (reg.descripcion_alerta or '')[:160]
        reg.numero_cliente_display = _numero_cliente_desde_moreapp(reg)

    context = {
        'registros': registros,
        'estado_filtro': estado,
        'contadores': contadores,
        'ahora': ahora,
        'umbral_7d': umbral_7d,
    }
    return render(request, 'operacional/pendientes.html', context)


@role_required(['ADMIN', 'ADMINISTRATIVO'])
@require_POST
def moreapp_marcar_revision_view(request, pk):
    """
    Punto 8 y 9: Marca un registro MoreApp con un nuevo estado de revisión.
    Acepta: REVISADO, DESCARTADO, CON_ADVERTENCIA.
    """
    from ordenes_trabajo.models import IntegracionMoreApp
    from web.moreapp_avisos import invalidar_caches_aviso_moreapp

    ESTADOS_VALIDOS = {'REVISADO', 'DESCARTADO', 'CON_ADVERTENCIA', 'PENDIENTE'}
    nuevo_estado = request.POST.get('estado_revision', '').strip().upper()
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if nuevo_estado not in ESTADOS_VALIDOS:
        if es_ajax:
            return JsonResponse({'success': False, 'error': 'Estado no válido'}, status=400)
        messages.error(request, 'Estado de revisión no válido')
        return redirect('reportes_moreapp_detalle', pk=pk)

    registro = get_object_or_404(IntegracionMoreApp, pk=pk, eliminado=False)
    estado_anterior = registro.estado_revision
    registro.estado_revision = nuevo_estado
    registro.save(update_fields=['estado_revision'])
    invalidar_caches_aviso_moreapp()
    register_audit_event(
        AuditEvent(
            actor_id=getattr(request.user, 'id', None),
            action='MOREAPP_REVISION_UPDATE',
            entity='IntegracionMoreApp',
            entity_id=str(registro.pk),
            field_name='estado_revision',
            old_value=estado_anterior,
            new_value=nuevo_estado,
            reason='Cambio de estado de revisión operativa MoreApp',
        )
    )

    if not es_ajax:
        messages.success(request, f'Estado de revisión actualizado a: {registro.get_estado_revision_display()}')
        return redirect('reportes_moreapp_detalle', pk=pk)

    return JsonResponse({
        'success': True,
        'estado_revision': nuevo_estado,
        'estado_anterior': estado_anterior,
        'estado_revision_display': dict(IntegracionMoreApp.ESTADO_REVISION_CHOICES).get(nuevo_estado, nuevo_estado),
        'contadores': _contadores_pendientes_moreapp(),
    })


@role_required(['ADMIN', 'ADMINISTRATIVO'])
@require_POST
def moreapp_reprocesar_view(request, pk):
    """Reaplica las actualizaciones de inventario para un registro MoreApp."""
    from ordenes_trabajo.models import IntegracionMoreApp
    from integraciones.reader import reprocesar_registro_moreapp

    registro = get_object_or_404(IntegracionMoreApp, pk=pk, eliminado=False)
    resultado = reprocesar_registro_moreapp(registro)

    if resultado.get('success'):
        messages.success(request, resultado.get('message', 'Registro reprocesado.'))
    else:
        messages.warning(request, resultado.get('message', 'No se pudo actualizar inventario.'))

    return redirect('reportes_moreapp_detalle', pk=pk)


# ========== VISTAS DE INVENTARIO ==========

def _texto_sin_acentos(valor: str) -> str:
    import unicodedata
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    return ''.join(ch for ch in texto if not unicodedata.combining(ch)).casefold().strip()


def _ids_estado_por_busqueda(texto: str):
    """Resuelve nombres de estado (con/sin acentos) a IDs de EstadoInventario."""
    busq = _texto_sin_acentos(texto)
    if not busq:
        return []

    aliases = {
        'trayecto': 'en trayecto',
        'bodega': 'en bodega',
        'devuelto': 'devuelta',
        'sin conexion': 'sin conexion',
        'problemas': 'con problemas',
        'reparacion': 'en reparacion',
        'baja': 'dado de baja',
    }
    busq = aliases.get(busq, busq)

    exactos = []
    parciales = []
    for estado in EstadoInventario.objects.all().only('id', 'nombre'):
        nombre_n = _texto_sin_acentos(estado.nombre)
        if not nombre_n:
            continue
        if nombre_n == busq:
            exactos.append(estado.id)
        elif len(busq) >= 3 and (busq in nombre_n or nombre_n.startswith(busq)):
            parciales.append(estado.id)
    return exactos or parciales


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR', 'TECNICO'])
def inventario_list_view(request):
    """Listado de equipos en inventario con filtros"""
    from django.core.paginator import Paginator
    from types import SimpleNamespace
    
    from usuarios.models import Usuario
    
    tipo = request.GET.get('tipo', 'medidor')
    if tipo == 'todos':
        tipo = 'medidor'
    page_num = request.GET.get('page', '1')
    per_page_raw = request.GET.get('per_page', '50')
    busqueda = request.GET.get('q', '').strip()
    campo_busqueda = request.GET.get('campo', 'all').strip()
    estado_filtro = request.GET.get('estado', '').strip()
    ubicacion_filtro = request.GET.get('ubicacion', '')
    proyecto_filtro = request.GET.get('proyecto', '').strip()
    caja_filtro = request.GET.get('caja', '').strip()
    tipo_medidor_filtro = request.GET.get('tipo_medidor', '').strip()

    # Si buscan por texto de estado, resolver a IDs (soporta Sin Conexion / Sin Conexión)
    estado_ids_busqueda = []
    if busqueda and campo_busqueda == 'estado':
        estado_ids_busqueda = _ids_estado_por_busqueda(busqueda)
        if len(estado_ids_busqueda) == 1 and not estado_filtro:
            estado_filtro = str(estado_ids_busqueda[0])

    # Tamaño de página permitido (optimizado)
    per_page_options = [10, 25, 50, 100]
    try:
        per_page = int(per_page_raw)
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in per_page_options:
        per_page = 50
    
    def _equipo_contiene_valor(equipo_row, valor: str) -> bool:
        return valor in ' '.join([
            str(getattr(equipo_row, 'tipo_label', '') or ''),
            str(getattr(equipo_row, 'identificador', '') or ''),
            str(getattr(equipo_row, 'descripcion', '') or ''),
            str(getattr(equipo_row, 'tecnico_display', '') or ''),
            str(getattr(equipo_row, 'estado_nombre', '') or ''),
            str(getattr(equipo_row, 'cliente_numero', '') or ''),
            str(getattr(equipo_row, 'proyecto', '') or ''),
        ]).lower()

    def _normalizar_equipo(tipo_equipo, equipo):
        if tipo_equipo == 'medidor':
            return SimpleNamespace(
                id=equipo.id,
                tipo='medidor',
                tipo_label='Medidor',
                identificador=equipo.serie,
                descripcion=' | '.join(filter(None, [equipo.marca, equipo.caja, equipo.get_tipo_medidor_display()])),
                tecnico_display=getattr(getattr(equipo, 'entregado_a', None), 'nombre_interno', '') or getattr(equipo, 'entregado_a_otro', '') or '',
                estado_nombre=getattr(getattr(equipo, 'estado_inventario', None), 'nombre', '') or '',
                estado_inventario=getattr(equipo, 'estado_inventario', None),
                cliente_numero=getattr(getattr(equipo, 'cliente', None), 'numero_cliente', '') or getattr(equipo, 'cliente_otro', '') or '',
                proyecto=getattr(equipo, 'proyecto', '') or '',
                fecha_recepcion=equipo.fecha_recepcion,
            )

        if tipo_equipo == 'sim':
            return SimpleNamespace(
                id=equipo.id,
                tipo='sim',
                tipo_label='SIM',
                identificador=equipo.imei or '-',
                descripcion=' | '.join(filter(None, [equipo.operador, equipo.abonado, equipo.direccion_ip, equipo.apn])),
                tecnico_display=getattr(getattr(equipo, 'en_custodia_de', None), 'nombre_interno', '') or getattr(equipo, 'entregado_a_otro', '') or getattr(equipo, 'entregado_a_nombre', '') or '',
                estado_nombre=getattr(getattr(equipo, 'estado_inventario', None), 'nombre', '') or '',
                estado_inventario=getattr(equipo, 'estado_inventario', None),
                cliente_numero=getattr(getattr(equipo, 'cliente', None), 'numero_cliente', '') or getattr(equipo, 'cliente_otro', '') or '',
                proyecto=getattr(equipo, 'proyecto', '') or '',
                fecha_recepcion=equipo.fecha_recepcion,
            )

        return SimpleNamespace(
            id=equipo.id,
            tipo='modem',
            tipo_label='Módem',
            identificador=equipo.serie,
            descripcion=' | '.join(filter(None, [equipo.marca, equipo.modelo, equipo.imei, equipo.caja])),
            tecnico_display=getattr(equipo, 'tecnico_responsable', '') or getattr(getattr(equipo, 'entregado_a', None), 'nombre_interno', '') or getattr(equipo, 'entregado_a_otro', '') or '',
            estado_nombre=getattr(getattr(equipo, 'estado_inventario', None), 'nombre', '') or '',
            estado_inventario=getattr(equipo, 'estado_inventario', None),
            cliente_numero=getattr(getattr(equipo, 'cliente', None), 'numero_cliente', '') or getattr(equipo, 'cliente_otro', '') or '',
            proyecto=getattr(equipo, 'proyecto', '') or '',
            fecha_recepcion=equipo.fecha_recepcion,
        )

    # Obtener datos base (excluye soft-deleted)
    if tipo == 'medidor':
        equipos = Medidor.objects.filter(eliminado=False).select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).order_by('serie')
        titulo = 'Medidores'
    elif tipo == 'sim':
        equipos = SimCard.objects.filter(eliminado=False).select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'en_custodia_de', 'medidor'
        ).order_by('imei')
        titulo = 'SIM Cards'
    elif tipo == 'modem':
        equipos = Modem.objects.filter(eliminado=False).select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).order_by('-id')
        titulo = 'Módems'
    elif tipo == 'todos':
        medidores_qs = Medidor.objects.filter(eliminado=False).select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).order_by('-id')
        sims_qs = SimCard.objects.filter(eliminado=False).select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'en_custodia_de', 'medidor'
        ).order_by('-id')
        modems_qs = Modem.objects.filter(eliminado=False).select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).order_by('-id')
        titulo = 'Inventario Consolidado'
    else:
        equipos = Medidor.objects.filter(eliminado=False).select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).order_by('-id')
        titulo = 'Medidores'
        tipo = 'medidor'
    
    # TECNICO: Solo ve equipos asignados a él
    if request.user.rol == 'TECNICO':
        if tipo == 'sim':
            # SimCard usa 'en_custodia_de' en lugar de 'entregado_a'
            equipos = equipos.filter(en_custodia_de=request.user)
        elif tipo == 'todos':
            medidores_qs = medidores_qs.filter(entregado_a=request.user)
            sims_qs = sims_qs.filter(en_custodia_de=request.user)
            modems_qs = modems_qs.filter(entregado_a=request.user)
        else:
            # Medidor y Modem usan 'entregado_a'
            equipos = equipos.filter(entregado_a=request.user)
    
    # Aplicar filtros
    if estado_filtro and tipo != 'todos':
        if str(estado_filtro).isdigit():
            equipos = equipos.filter(estado_inventario_id=int(estado_filtro))
        else:
            ids_estado = _ids_estado_por_busqueda(estado_filtro)
            equipos = equipos.filter(estado_inventario_id__in=ids_estado) if ids_estado else equipos.none()
    elif estado_ids_busqueda and tipo != 'todos' and campo_busqueda == 'estado':
        equipos = equipos.filter(estado_inventario_id__in=estado_ids_busqueda)
    
    if ubicacion_filtro and tipo != 'todos':
        equipos = equipos.filter(ubicacion_actual_id=ubicacion_filtro)

    if proyecto_filtro and tipo != 'todos':
        equipos = equipos.filter(proyecto__icontains=proyecto_filtro)

    if caja_filtro and tipo in ('medidor', 'modem'):
        equipos = equipos.filter(caja__icontains=caja_filtro)

    if tipo == 'medidor' and tipo_medidor_filtro:
        equipos = equipos.filter(tipo_medidor=tipo_medidor_filtro)

    if tipo == 'todos':
        if estado_filtro:
            if str(estado_filtro).isdigit():
                estado_q = Q(estado_inventario_id=int(estado_filtro))
            else:
                ids_estado = _ids_estado_por_busqueda(estado_filtro)
                estado_q = Q(estado_inventario_id__in=ids_estado) if ids_estado else Q(pk__in=[])
            medidores_qs = medidores_qs.filter(estado_q)
            sims_qs = sims_qs.filter(estado_q)
            modems_qs = modems_qs.filter(estado_q)
        elif estado_ids_busqueda:
            medidores_qs = medidores_qs.filter(estado_inventario_id__in=estado_ids_busqueda)
            sims_qs = sims_qs.filter(estado_inventario_id__in=estado_ids_busqueda)
            modems_qs = modems_qs.filter(estado_inventario_id__in=estado_ids_busqueda)

        if ubicacion_filtro:
            medidores_qs = medidores_qs.filter(ubicacion_actual_id=ubicacion_filtro)
            sims_qs = sims_qs.filter(ubicacion_actual_id=ubicacion_filtro)
            modems_qs = modems_qs.filter(ubicacion_actual_id=ubicacion_filtro)

        if proyecto_filtro:
            medidores_qs = medidores_qs.filter(proyecto__icontains=proyecto_filtro)
            sims_qs = sims_qs.filter(proyecto__icontains=proyecto_filtro)
            modems_qs = modems_qs.filter(proyecto__icontains=proyecto_filtro)

        if caja_filtro:
            medidores_qs = medidores_qs.filter(caja__icontains=caja_filtro)
            modems_qs = modems_qs.filter(caja__icontains=caja_filtro)

        if tipo_medidor_filtro:
            medidores_qs = medidores_qs.filter(tipo_medidor=tipo_medidor_filtro)

        equipos = [
            *(_normalizar_equipo('medidor', equipo) for equipo in medidores_qs),
            *(_normalizar_equipo('sim', equipo) for equipo in sims_qs),
            *(_normalizar_equipo('modem', equipo) for equipo in modems_qs),
        ]
        equipos.sort(key=lambda item: item.id, reverse=True)

    # Búsqueda global por servidor (evita filtrar solo el bloque cargado)
    # Si campo=estado, el filtro ya se resolvió arriba por IDs (con/sin acentos).
    if busqueda and campo_busqueda != 'estado':
        if tipo == 'todos':
            filtro = busqueda.lower()
            if campo_busqueda == 'tipo':
                equipos = [equipo for equipo in equipos if filtro in (equipo.tipo_label or '').lower()]
            elif campo_busqueda == 'identificador':
                equipos = [equipo for equipo in equipos if filtro in (equipo.identificador or '').lower()]
            elif campo_busqueda == 'descripcion':
                equipos = [equipo for equipo in equipos if filtro in (equipo.descripcion or '').lower()]
            elif campo_busqueda == 'tecnico':
                equipos = [equipo for equipo in equipos if filtro in (equipo.tecnico_display or '').lower()]
            elif campo_busqueda == 'cliente':
                equipos = [equipo for equipo in equipos if filtro in (equipo.cliente_numero or '').lower()]
            elif campo_busqueda == 'proyecto':
                equipos = [equipo for equipo in equipos if filtro in (equipo.proyecto or '').lower()]
            else:
                equipos = [equipo for equipo in equipos if _equipo_contiene_valor(equipo, filtro)]
        elif tipo == 'medidor':
            campos_por_tipo = {
                'serie': 'serie__icontains',
                'marca': 'marca__icontains',
                'caja': 'caja__icontains',
                'tipo_medidor': 'tipo_medidor__icontains',
                'entregado_a': 'entregado_a__nombre_interno__icontains',
                'proyecto': 'proyecto__icontains',
                'cliente': 'cliente__numero_cliente__icontains',
            }
            campos_all = [
                'serie__icontains',
                'marca__icontains',
                'caja__icontains',
                'tipo_medidor__icontains',
                'entregado_a__nombre_interno__icontains',
                'proyecto__icontains',
                'estado_inventario__nombre__icontains',
                'cliente__numero_cliente__icontains',
            ]
        elif tipo == 'sim':
            campos_por_tipo = {
                'imei': 'imei__icontains',
                'operador': 'operador__icontains',
                'abonado': 'abonado__icontains',
                'direccion_ip': 'direccion_ip__icontains',
                # La custodia real vive en en_custodia_de; el texto del Excel en entregado_a_nombre.
                'entregado_a': [
                    'en_custodia_de__nombre_interno__icontains',
                    'entregado_a_nombre__icontains',
                    'entregado_a_otro__icontains',
                ],
                'proyecto': 'proyecto__icontains',
                'cliente': 'cliente__numero_cliente__icontains',
            }
            campos_all = [
                'imei__icontains',
                'operador__icontains',
                'abonado__icontains',
                'direccion_ip__icontains',
                'ip_fija__icontains',
                'en_custodia_de__nombre_interno__icontains',
                'entregado_a_nombre__icontains',
                'entregado_a_otro__icontains',
                'proyecto__icontains',
                'estado_inventario__nombre__icontains',
                'cliente__numero_cliente__icontains',
            ]
        else:
            campos_por_tipo = {
                'marca': 'marca__icontains',
                'modelo': 'modelo__icontains',
                'imei': 'imei__icontains',
                'serie': 'serie__icontains',
                'caja': 'caja__icontains',
                # El asignado real puede estar en entregado_a (FK) y no en el texto del Excel.
                'tecnico': [
                    'tecnico_responsable__icontains',
                    'entregado_a__nombre_interno__icontains',
                    'entregado_a_otro__icontains',
                ],
                'cliente': 'cliente__numero_cliente__icontains',
                'proyecto': 'proyecto__icontains',
            }
            campos_all = [
                'marca__icontains',
                'modelo__icontains',
                'imei__icontains',
                'serie__icontains',
                'caja__icontains',
                'tecnico_responsable__icontains',
                'entregado_a__nombre_interno__icontains',
                'entregado_a_otro__icontains',
                'estado_inventario__nombre__icontains',
                'cliente__numero_cliente__icontains',
                'proyecto__icontains',
            ]

        if tipo != 'todos':
            if tipo == 'medidor' and campo_busqueda == 'modulo':
                val = busqueda.lower()
                if val in {'si', 'sí', 'true', '1', 'yes'}:
                    equipos = equipos.filter(modulo=True)
                elif val in {'no', 'false', '0'}:
                    equipos = equipos.filter(modulo=False)
                else:
                    equipos = equipos.none()
            elif campo_busqueda in campos_por_tipo:
                lookups = campos_por_tipo[campo_busqueda]
                if isinstance(lookups, (list, tuple)):
                    q_campo = Q()
                    for lookup in lookups:
                        q_campo |= Q(**{lookup: busqueda})
                    equipos = equipos.filter(q_campo)
                else:
                    equipos = equipos.filter(**{lookups: busqueda})
            else:
                query = Q()
                for lookup in campos_all:
                    query |= Q(**{lookup: busqueda})
                ids_estado = _ids_estado_por_busqueda(busqueda)
                if ids_estado:
                    query |= Q(estado_inventario_id__in=ids_estado)
                if tipo == 'medidor':
                    val = busqueda.lower()
                    if val in {'si', 'sí', 'true', '1', 'yes'}:
                        query |= Q(modulo=True)
                    elif val in {'no', 'false', '0'}:
                        query |= Q(modulo=False)
                equipos = equipos.filter(query)

    # count() en QuerySet evita materializar todo el inventario en memoria
    if hasattr(equipos, 'count') and not isinstance(equipos, list):
        total_filtrado = equipos.count()
    else:
        total_filtrado = len(equipos)
    paginador = Paginator(equipos, per_page)
    page_obj = paginador.get_page(page_num)
    equipos = page_obj.object_list

    # Compatibilidad: evitar que el template acceda a atributos que aun no existen
    # en algunas bases/productivos donde no se aplicaron migraciones recientes.
    if tipo != 'todos':
        for equipo in equipos:
            if tipo == 'medidor':
                equipo.tecnico_display = (
                    getattr(getattr(equipo, 'entregado_a', None), 'nombre_interno', '')
                    or getattr(equipo, 'entregado_a_otro', '')
                    or getattr(equipo, 'entregado_a_info', '')
                    or ''
                )
                equipo.cliente_display = (
                    getattr(getattr(equipo, 'cliente', None), 'numero_cliente', '')
                    or getattr(equipo, 'cliente_otro', '')
                    or ''
                )
            elif tipo == 'sim':
                equipo.tecnico_display = (
                    getattr(getattr(equipo, 'en_custodia_de', None), 'nombre_interno', '')
                    or getattr(equipo, 'entregado_a_otro', '')
                    or getattr(equipo, 'entregado_a_nombre', '')
                    or ''
                )
                equipo.cliente_display = (
                    getattr(getattr(equipo, 'cliente', None), 'numero_cliente', '')
                    or getattr(equipo, 'cliente_otro', '')
                    or ''
                )
            else:
                equipo.tecnico_display = (
                    getattr(equipo, 'tecnico_responsable', '')
                    or getattr(getattr(equipo, 'entregado_a', None), 'nombre_interno', '')
                    or getattr(equipo, 'entregado_a_otro', '')
                    or ''
                )
                equipo.cliente_display = (
                    getattr(getattr(equipo, 'cliente', None), 'numero_cliente', '')
                    or getattr(equipo, 'cliente_otro', '')
                    or ''
                )

    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()
    
    # Obtener opciones para filtros (solo estados de negocio definidos)
    if tipo in ('medidor', 'modem'):
        estados_permitidos = ['En bodega', 'En Trayecto', 'Instalado', 'Retirado', 'En reparación', 'Dado de baja', 'En peaje']
        estados_disponibles = list(EstadoInventario.objects.filter(nombre__in=estados_permitidos))
        estados_disponibles.sort(key=lambda e: estados_permitidos.index(e.nombre) if e.nombre in estados_permitidos else 99)
    elif tipo == 'sim':
        estados_permitidos = [
            'En bodega', 'En Trayecto', 'Instalado', 'Retirado',
            'Devuelta', 'Sin Conexión', 'Con Problemas',
            'En reparación', 'Dado de baja',
        ]
        ids_usados = SimCard.objects.exclude(estado_inventario_id__isnull=True).values_list(
            'estado_inventario_id', flat=True
        ).distinct()
        estados_disponibles = list(
            EstadoInventario.objects.filter(
                Q(nombre__in=estados_permitidos) | Q(id__in=ids_usados)
            ).distinct()
        )
        estados_disponibles.sort(
            key=lambda e: estados_permitidos.index(e.nombre) if e.nombre in estados_permitidos else 99
        )
    else:
        estados_permitidos = ['En bodega', 'En Trayecto', 'Instalado', 'Retirado', 'En reparación', 'Dado de baja']
        estados_disponibles = list(EstadoInventario.objects.filter(nombre__in=estados_permitidos))
        estados_disponibles.sort(key=lambda e: estados_permitidos.index(e.nombre) if e.nombre in estados_permitidos else 99)
    from web.perf_cache import cache_get_or_set, TTL_MEDIO

    ubicaciones_disponibles = Ubicacion.objects.all()
    usuarios = Usuario.objects.filter(rol='TECNICO', is_active=True).order_by('nombre_interno')
    # Cliente/medidor se eligen por autocomplete (APIs); no cargar miles de opciones al HTML.

    def _proyectos_lista():
        return sorted(set(
            list(Medidor.objects.exclude(proyecto='').exclude(proyecto__isnull=True)
                 .values_list('proyecto', flat=True).distinct()[:200])
            + list(SimCard.objects.exclude(proyecto='').exclude(proyecto__isnull=True)
                   .values_list('proyecto', flat=True).distinct()[:200])
            + list(Modem.objects.exclude(proyecto='').exclude(proyecto__isnull=True)
                   .values_list('proyecto', flat=True).distinct()[:200])
        ))

    proyectos_disponibles = cache_get_or_set('inventario:proyectos', _proyectos_lista, TTL_MEDIO)

    sim_resumen = None
    if tipo == 'sim':
        base_sim = SimCard.objects.filter(eliminado=False)
        total_sim = base_sim.count()
        por_estado = list(
            base_sim.values('estado_inventario_id', 'estado_inventario__nombre')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        sim_resumen = {
            'total': total_sim,
            'con_ip': base_sim.exclude(Q(direccion_ip='') | Q(direccion_ip__isnull=True)).count(),
            'con_abonado': base_sim.exclude(Q(abonado='') | Q(abonado__isnull=True)).count(),
            'con_entregado': base_sim.exclude(Q(entregado_a_nombre='') | Q(entregado_a_nombre__isnull=True)).count(),
            'con_cliente': base_sim.filter(cliente_id__isnull=False).count(),
            'por_estado': por_estado,
        }
    
    context = {
        'equipos': equipos,
        'tipo': tipo,
        'titulo': titulo,
        'estados_disponibles': estados_disponibles,
        'ubicaciones_disponibles': ubicaciones_disponibles,
        'usuarios': usuarios,
        'estado_seleccionado': str(estado_filtro).strip() if estado_filtro else '',
        'ubicacion_seleccionada': ubicacion_filtro,
        'proyecto_seleccionado': proyecto_filtro,
        'caja_seleccionada': caja_filtro,
        'tipo_medidor_seleccionado': tipo_medidor_filtro,
        'proyectos_disponibles': proyectos_disponibles,
        'tipo_medidor_choices': Medidor.TIPO_MEDIDOR_CHOICES,
        'total_medidores_directos': Medidor.objects.filter(tipo_medidor='DIRECTO', eliminado=False).count(),
        'total_medidores_indirectos': Medidor.objects.filter(tipo_medidor='INDIRECTO', eliminado=False).count(),
        'sim_resumen': sim_resumen,
        'busqueda': busqueda,
        'campo_busqueda': campo_busqueda,
        'total_filtrado': total_filtrado,
        'page_obj': page_obj,
        'query_string': query_string,
        'per_page': per_page,
        'per_page_options': per_page_options,
    }
    return render(request, 'inventario/list.html', context)



@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR', 'TECNICO'])
@require_http_methods(["GET"])
def inventario_obtener_datos_view(request, pk):
    """Obtiene datos de un equipo en formato JSON"""
    
    tipo = request.GET.get('tipo', 'medidor')
    
    try:
        # Obtener el equipo según tipo (solo activos; los eliminados no se consultan)
        if tipo == 'medidor':
            equipo = get_object_or_404(Medidor, pk=pk, eliminado=False)
        elif tipo == 'sim':
            equipo = get_object_or_404(SimCard, pk=pk, eliminado=False)
        elif tipo == 'modem':
            equipo = get_object_or_404(Modem, pk=pk, eliminado=False)
        else:
            return JsonResponse({
                'success': False,
                'message': 'Tipo de equipo no válido'
            })
        
        # Si es TECNICO, verificar que el equipo sea suyo
        if request.user.rol == 'TECNICO':
            if tipo == 'sim':
                # SimCard usa 'en_custodia_de'
                if equipo.en_custodia_de != request.user:
                    return JsonResponse({
                        'success': False,
                        'message': 'No tienes permiso para ver este equipo'
                    }, status=403)
            else:
                # Medidor y Modem usan 'entregado_a'
                if equipo.entregado_a != request.user:
                    return JsonResponse({
                        'success': False,
                        'message': 'No tienes permiso para ver este equipo'
                    }, status=403)
        
        # Preparar datos según tipo
        if tipo == 'sim':
            datos = {
                'id': equipo.id,
                'tipo': tipo,
                'imei': getattr(equipo, 'imei', '') or '',
                'operador': getattr(equipo, 'operador', '') or '',
                'abonado': getattr(equipo, 'abonado', '') or '',
                'direccion_ip': getattr(equipo, 'direccion_ip', '') or '',
                'apn': getattr(equipo, 'apn', '') or '',
                'fecha_recepcion': equipo.fecha_recepcion.strftime('%Y-%m-%d') if equipo.fecha_recepcion else '',
                'entregado_a_nombre': getattr(equipo, 'entregado_a_nombre', '') or '',
                'en_custodia_de_id': getattr(equipo, 'en_custodia_de_id', '') or '',
                'entregado_a_valor': str(getattr(equipo, 'en_custodia_de_id', '') or '') or ('CERTELEC' if getattr(equipo, 'entregado_a_otro', '') == 'Certelec' else ''),
                'fecha_entrega': equipo.fecha_entrega.strftime('%Y-%m-%d') if equipo.fecha_entrega else '',
                'estado_id': getattr(equipo, 'estado_inventario_id', '') or '',
                'cliente_id': getattr(equipo, 'cliente_id', '') or '',
                'cliente_numero': equipo.cliente.numero_cliente if getattr(equipo, 'cliente', None) else '',
                'cliente_label': (
                    f"{equipo.cliente.numero_cliente} - {equipo.cliente.direccion}"
                    if getattr(equipo, 'cliente', None) else ''
                ),
                'cliente_otro': getattr(equipo, 'cliente_otro', '') or '',
                'medidor_id': getattr(equipo, 'medidor_id', '') or '',
                'medidor_label': (
                    f"{equipo.medidor.serie} - {equipo.medidor.marca or 'S/M'}"
                    if getattr(equipo, 'medidor', None) else ''
                ),
                'medidor_otro': getattr(equipo, 'medidor_otro', '') or '',
                'proyecto': getattr(equipo, 'proyecto', '') or '',
            }
        elif tipo == 'modem':
            # Para módems: devolver campos VERDE (solo lectura) y AMARILLO (editables)
            datos = {
                'id': equipo.id,
                'tipo': tipo,
                # VERDE (solo lectura) - incluye IP y Puerto como datos importantes
                'marca': getattr(equipo, 'marca', '') or '',
                'modelo': getattr(equipo, 'modelo', '') or '',
                'imei': getattr(equipo, 'imei', '') or '',
                'serie': getattr(equipo, 'serie', '') or '',
                'ip': getattr(equipo, 'ip', '') or '',
                'puerto': getattr(equipo, 'puerto', '') or '',
                'fecha_recepcion': equipo.fecha_recepcion.strftime('%Y-%m-%d') if equipo.fecha_recepcion else '',
                'fecha_entrega': equipo.fecha_entrega.strftime('%Y-%m-%d') if equipo.fecha_entrega else '',
                'caja': getattr(equipo, 'caja', '') or '',
                'tecnico_responsable': getattr(equipo, 'tecnico_responsable', '') or '',
                # AMARILLO (editables)
                'estado_id': getattr(equipo, 'estado_inventario_id', '') or '',
                'cliente_id': getattr(equipo, 'cliente_id', '') or '',
                'cliente_label': (
                    f"{equipo.cliente.numero_cliente} - {equipo.cliente.direccion}"
                    if getattr(equipo, 'cliente', None) else ''
                ),
                'cliente_otro': getattr(equipo, 'cliente_otro', '') or '',
                'medidor_id': getattr(equipo, 'medidor_id', '') or '',
                'medidor_label': (
                    f"{equipo.medidor.serie} - {equipo.medidor.marca or 'S/M'}"
                    if getattr(equipo, 'medidor', None) else ''
                ),
                'medidor_otro': getattr(equipo, 'medidor_otro', '') or '',
                'observaciones': getattr(equipo, 'observaciones', '') or '',
                'marca_secundaria': getattr(equipo, 'marca_secundaria', '') or '',
                'retirado': getattr(equipo, 'retirado', '') or '',
                'serie_secundaria': getattr(equipo, 'serie_secundaria', '') or '',
                'irregularidad': getattr(equipo, 'irregularidad', '') or '',
                'proyecto': getattr(equipo, 'proyecto', '') or '',
                'entregado_a_id': getattr(equipo, 'entregado_a_id', '') or '',
                'entregado_a_valor': str(getattr(equipo, 'entregado_a_id', '') or '') or ('CERTELEC' if getattr(equipo, 'entregado_a_otro', '') == 'Certelec' else ''),
            }
        else:
            # Para Medidor
            datos = {
                'id': equipo.id,
                'tipo': tipo,
                'fecha_recepcion': equipo.fecha_recepcion.strftime('%Y-%m-%d') if equipo.fecha_recepcion else '',
                'bodega': getattr(equipo, 'bodega', '') or '',
                'marca': getattr(equipo, 'marca', '') or '',
                'caja': getattr(equipo, 'caja', '') or '',
                'serie': getattr(equipo, 'serie', '') or '',
                'modulo': 'SI' if getattr(equipo, 'modulo', None) is True else ('NO' if getattr(equipo, 'modulo', None) is False else ''),
                'entregado_a_info': getattr(equipo, 'entregado_a_info', '') or '',
                'observaciones': getattr(equipo, 'observaciones', '') or '',
                'cliente_numero': equipo.cliente.numero_cliente if getattr(equipo, 'cliente', None) else '',
                'cliente_label': (
                    f"{equipo.cliente.numero_cliente} - {equipo.cliente.direccion}"
                    if getattr(equipo, 'cliente', None) else ''
                ),
                'cliente_otro': getattr(equipo, 'cliente_otro', '') or '',
                'fecha_entrega': equipo.fecha_entrega.strftime('%Y-%m-%d') if equipo.fecha_entrega else '',
                'estado_id': getattr(equipo, 'estado_inventario_id', '') or '',
                'entregado_a_id': getattr(equipo, 'entregado_a_id', '') or '',
                'entregado_a_valor': str(getattr(equipo, 'entregado_a_id', '') or '') or ('CERTELEC' if getattr(equipo, 'entregado_a_otro', '') == 'Certelec' else ''),
                'cliente_id': getattr(equipo, 'cliente_id', '') or '',
                'proyecto': getattr(equipo, 'proyecto', '') or '',
                'tipo_medidor': getattr(equipo, 'tipo_medidor', '') or '',
            }
        
        return JsonResponse({
            'success': True,
            'data': datos
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al obtener datos: {str(e)}'
        })


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO'])
@require_http_methods(["POST"])
def inventario_modificar_view(request, pk):
    """Modifica datos de un equipo en inventario"""
    
    from usuarios.models import Usuario
    
    tipo = request.POST.get('tipo', 'medidor')
    
    try:
        # Obtener el equipo según tipo (solo activos; los eliminados no se editan)
        if tipo == 'medidor':
            equipo = get_object_or_404(Medidor, pk=pk, eliminado=False)
        elif tipo == 'sim':
            equipo = get_object_or_404(SimCard, pk=pk, eliminado=False)
        elif tipo == 'modem':
            equipo = get_object_or_404(Modem, pk=pk, eliminado=False)
        else:
            return JsonResponse({
                'success': False,
                'message': 'Tipo de equipo no válido'
            })
        
        # Si es TECNICO, verificar que el equipo sea suyo
        if request.user.rol == 'TECNICO':
            if tipo == 'sim':
                # SimCard usa 'en_custodia_de'
                if equipo.en_custodia_de != request.user:
                    return JsonResponse({
                        'success': False,
                        'message': 'No tienes permiso para modificar este equipo'
                    }, status=403)
            else:
                # Medidor y Modem usan 'entregado_a'
                if equipo.entregado_a != request.user:
                    return JsonResponse({
                        'success': False,
                        'message': 'No tienes permiso para modificar este equipo'
                    }, status=403)

        def _resolver_cliente(valor_selector, valor_otro):
            valor_selector = (valor_selector or '').strip()
            valor_otro = (valor_otro or '').strip()
            if valor_selector == 'OTRO':
                return None, valor_otro
            if valor_selector:
                try:
                    return Cliente.objects.get(pk=int(valor_selector)), ''
                except (ValueError, TypeError, Cliente.DoesNotExist):
                    return None, valor_otro
            return None, valor_otro

        def _resolver_medidor(valor_selector, valor_otro):
            valor_selector = (valor_selector or '').strip()
            valor_otro = (valor_otro or '').strip()
            if valor_selector == 'OTRO':
                return None, valor_otro
            if valor_selector:
                try:
                    return Medidor.objects.get(pk=int(valor_selector), eliminado=False), ''
                except (ValueError, TypeError, Medidor.DoesNotExist):
                    return None, valor_otro
            return None, valor_otro

        def _resolver_responsable(valor_selector):
            valor_selector = (valor_selector or '').strip()
            if valor_selector == 'CERTELEC':
                return None, 'Certelec'
            if valor_selector:
                try:
                    return Usuario.objects.get(pk=int(valor_selector)), ''
                except (ValueError, TypeError, Usuario.DoesNotExist):
                    return None, ''
            return None, ''

        # Snapshot para detectar qué cambió
        if tipo == 'medidor':
            before = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'entregado_a_id': equipo.entregado_a_id,
                'entregado_a_otro': equipo.entregado_a_otro,
                'cliente_id': equipo.cliente_id,
                'cliente_otro': equipo.cliente_otro,
                'proyecto': equipo.proyecto,
                'tipo_medidor': equipo.tipo_medidor,
            }
        elif tipo == 'sim':
            before = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'en_custodia_de_id': equipo.en_custodia_de_id,
                'entregado_a_otro': equipo.entregado_a_otro,
                'cliente_id': equipo.cliente_id,
                'cliente_otro': equipo.cliente_otro,
                'medidor_id': equipo.medidor_id,
                'medidor_otro': equipo.medidor_otro,
                'proyecto': equipo.proyecto,
            }
        else:
            before = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'entregado_a_id': equipo.entregado_a_id,
                'entregado_a_otro': equipo.entregado_a_otro,
                'cliente_id': equipo.cliente_id,
                'cliente_otro': equipo.cliente_otro,
                'medidor_id': equipo.medidor_id,
                'medidor_otro': equipo.medidor_otro,
                'ip': equipo.ip,
                'puerto': equipo.puerto,
                'marca_secundaria': equipo.marca_secundaria,
                'observaciones': equipo.observaciones,
                'retirado': equipo.retirado,
                'serie_secundaria': equipo.serie_secundaria,
                'irregularidad': equipo.irregularidad,
                'proyecto': equipo.proyecto,
            }
        
        # Actualizar campos según tipo
        if tipo == 'sim':
            # Para SIM Card - campos verdes que puede modificar el administrativo
            fecha_entrega = request.POST.get('fecha_entrega', '').strip()
            estado_id = request.POST.get('estado_sim', '').strip() or request.POST.get('estado', '').strip()
            cliente_id = request.POST.get('cliente', '').strip()
            cliente_texto = request.POST.get('cliente_otro', '').strip() or request.POST.get('cliente_texto', '').strip()
            en_custodia_de_id = request.POST.get('entregado_a_id', '').strip()
            medidor_id = request.POST.get('medidor', '').strip()
            medidor_otro = request.POST.get('medidor_otro', '').strip()
            proyecto = request.POST.get('proyecto', '').strip()
            cliente_obj, cliente_manual = _resolver_cliente(cliente_id, cliente_texto)
            medidor_obj, medidor_manual = _resolver_medidor(medidor_id, medidor_otro)
            custodia_obj, custodia_manual = _resolver_responsable(en_custodia_de_id)
            
            if fecha_entrega:
                equipo.fecha_entrega = fecha_entrega
            
            if estado_id:
                try:
                    estado_obj = EstadoInventario.objects.get(pk=int(estado_id))
                    equipo.estado_inventario = estado_obj
                except (ValueError, TypeError, EstadoInventario.DoesNotExist):
                    pass
            
            if cliente_obj or cliente_manual or cliente_id == 'OTRO':
                equipo.cliente = cliente_obj
                equipo.cliente_otro = cliente_manual
            else:
                equipo.cliente = None
                equipo.cliente_otro = ''
            
            if en_custodia_de_id:
                equipo.en_custodia_de = custodia_obj
                equipo.entregado_a_otro = custodia_manual
            else:
                equipo.en_custodia_de = None
                equipo.entregado_a_otro = ''

            if medidor_obj or medidor_manual or medidor_id == 'OTRO':
                equipo.medidor = medidor_obj
                equipo.medidor_otro = medidor_manual
            else:
                equipo.medidor = None
                equipo.medidor_otro = ''

            if custodia_obj or custodia_manual:
                equipo.estado_inventario = _obtener_estado_inventario(
                    'En Trayecto',
                    'Equipo entregado a tecnico o tercero y en traslado operativo',
                )
            equipo.proyecto = proyecto
        elif tipo == 'modem':
            # Para Módems - solo campos AMARILLO (editables por administrativo)
            cliente_id = request.POST.get('cliente', '').strip()
            cliente_otro = request.POST.get('cliente_otro', '').strip()
            medidor_id = request.POST.get('medidor', '').strip()
            medidor_otro = request.POST.get('medidor_otro', '').strip()
            ip = request.POST.get('ip', '').strip()
            puerto = request.POST.get('puerto', '').strip()
            marca_secundaria = request.POST.get('marca_secundaria', '').strip()
            observaciones = request.POST.get('observaciones', '').strip()
            entregado_a_id_modem = request.POST.get('entregado_a_id', '').strip()
            retirado = request.POST.get('retirado', '').strip()
            serie_secundaria = request.POST.get('serie_secundaria', '').strip()
            irregularidad = request.POST.get('irregularidad', '').strip()
            proyecto = request.POST.get('proyecto', '').strip()
            cliente_obj, cliente_manual = _resolver_cliente(cliente_id, cliente_otro)
            medidor_obj, medidor_manual = _resolver_medidor(medidor_id, medidor_otro)
            entregado_a_obj_modem, entregado_a_manual_modem = _resolver_responsable(entregado_a_id_modem)

            fecha_entrega = request.POST.get('fecha_entrega', '').strip()
            if fecha_entrega:
                equipo.fecha_entrega = fecha_entrega
            else:
                equipo.fecha_entrega = None
            
            if cliente_obj or cliente_manual or cliente_id == 'OTRO':
                equipo.cliente = cliente_obj
                equipo.cliente_otro = cliente_manual
            else:
                equipo.cliente = None
                equipo.cliente_otro = ''
            
            if medidor_obj or medidor_manual or medidor_id == 'OTRO':
                equipo.medidor = medidor_obj
                equipo.medidor_otro = medidor_manual
            else:
                equipo.medidor = None
                equipo.medidor_otro = ''

            # Campos azules editables
            if entregado_a_id_modem:
                equipo.entregado_a = entregado_a_obj_modem
                equipo.entregado_a_otro = entregado_a_manual_modem
            else:
                equipo.entregado_a = None
                equipo.entregado_a_otro = ''
            equipo.ip = ip
            equipo.puerto = puerto
            equipo.marca_secundaria = marca_secundaria
            equipo.observaciones = observaciones
            equipo.retirado = retirado
            equipo.serie_secundaria = serie_secundaria
            equipo.irregularidad = irregularidad
            equipo.proyecto = proyecto

            estado_modem = request.POST.get('estado_modem', '').strip()
            if estado_modem:
                try:
                    estado_obj = EstadoInventario.objects.get(pk=int(estado_modem))
                    equipo.estado_inventario = estado_obj
                except (ValueError, TypeError, EstadoInventario.DoesNotExist):
                    pass
            if entregado_a_obj_modem or entregado_a_manual_modem:
                equipo.estado_inventario = _obtener_estado_inventario(
                    'En Trayecto',
                    'Equipo entregado a tecnico o tercero y en traslado operativo',
                )
        else:
            # Para Medidor - todos los campos editables
            fecha_entrega = request.POST.get('fecha_entrega', '').strip()
            estado_id = request.POST.get('estado_medidor', '').strip()
            entregado_a_id = request.POST.get('entregado_a', '').strip()
            cliente_id = request.POST.get('cliente', '').strip()
            cliente_texto = request.POST.get('cliente_otro', '').strip() or request.POST.get('cliente_texto', '').strip()
            proyecto = request.POST.get('proyecto', '').strip()
            tipo_medidor = request.POST.get('tipo_medidor', '').strip().upper()
            cliente_obj, cliente_manual = _resolver_cliente(cliente_id, cliente_texto)
            entregado_a_obj, entregado_a_manual = _resolver_responsable(entregado_a_id)

            if tipo_medidor not in {'DIRECTO', 'INDIRECTO'}:
                return JsonResponse({
                    'success': False,
                    'message': 'El tipo de medidor es obligatorio (DIRECTO o INDIRECTO)'
                }, status=400)
            
            if fecha_entrega:
                equipo.fecha_entrega = fecha_entrega
            
            if estado_id:
                try:
                    estado_obj = EstadoInventario.objects.get(pk=int(estado_id))
                    equipo.estado_inventario = estado_obj
                except (ValueError, TypeError, EstadoInventario.DoesNotExist):
                    pass
            
            if entregado_a_id:
                equipo.entregado_a = entregado_a_obj
                equipo.entregado_a_otro = entregado_a_manual
            else:
                equipo.entregado_a = None
                equipo.entregado_a_otro = ''
            
            if cliente_obj or cliente_manual or cliente_id == 'OTRO':
                equipo.cliente = cliente_obj
                equipo.cliente_otro = cliente_manual
            else:
                equipo.cliente = None
                equipo.cliente_otro = ''
            if entregado_a_obj or entregado_a_manual:
                equipo.estado_inventario = _obtener_estado_inventario(
                    'En Trayecto',
                    'Equipo entregado a tecnico o tercero y en traslado operativo',
                )
            equipo.proyecto = proyecto
            equipo.tipo_medidor = tipo_medidor
        
        # Guardar cambios
        equipo.save()

        # Detectar cambios y registrar Kardex
        if tipo == 'medidor':
            after = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'entregado_a_id': equipo.entregado_a_id,
                'entregado_a_otro': equipo.entregado_a_otro,
                'cliente_id': equipo.cliente_id,
                'cliente_otro': equipo.cliente_otro,
                'proyecto': equipo.proyecto,
                'tipo_medidor': equipo.tipo_medidor,
            }
            etiquetas = {
                'fecha_entrega': 'Fecha Entrega',
                'estado_id': 'Estado',
                'entregado_a_id': 'Entregado A',
                'entregado_a_otro': 'Entregado A',
                'cliente_id': 'Cliente',
                'cliente_otro': 'Cliente',
                'proyecto': 'Proyecto',
                'tipo_medidor': 'Tipo Medidor',
            }
            tipo_item = 'MEDIDOR'
            identificador = equipo.serie
        elif tipo == 'sim':
            after = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'en_custodia_de_id': equipo.en_custodia_de_id,
                'entregado_a_otro': equipo.entregado_a_otro,
                'cliente_id': equipo.cliente_id,
                'cliente_otro': equipo.cliente_otro,
                'medidor_id': equipo.medidor_id,
                'medidor_otro': equipo.medidor_otro,
                'proyecto': equipo.proyecto,
            }
            etiquetas = {
                'fecha_entrega': 'Fecha Entrega',
                'estado_id': 'Estado',
                'en_custodia_de_id': 'Entregado A',
                'entregado_a_otro': 'Entregado A',
                'cliente_id': 'Cliente',
                'cliente_otro': 'Cliente',
                'medidor_id': 'Medidor',
                'medidor_otro': 'Medidor',
                'proyecto': 'Proyecto',
            }
            tipo_item = 'SIM'
            identificador = equipo.imei or equipo.abonado or str(equipo.pk)
        else:
            after = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'entregado_a_id': equipo.entregado_a_id,
                'entregado_a_otro': equipo.entregado_a_otro,
                'cliente_id': equipo.cliente_id,
                'cliente_otro': equipo.cliente_otro,
                'medidor_id': equipo.medidor_id,
                'medidor_otro': equipo.medidor_otro,
                'ip': equipo.ip,
                'puerto': equipo.puerto,
                'marca_secundaria': equipo.marca_secundaria,
                'observaciones': equipo.observaciones,
                'retirado': equipo.retirado,
                'serie_secundaria': equipo.serie_secundaria,
                'irregularidad': equipo.irregularidad,
                'proyecto': equipo.proyecto,
            }
            etiquetas = {
                'fecha_entrega': 'Fecha Entrega',
                'estado_id': 'Estado',
                'entregado_a_id': 'Entregado A',
                'entregado_a_otro': 'Entregado A',
                'cliente_id': 'Cliente',
                'cliente_otro': 'Cliente',
                'medidor_id': 'Medidor',
                'medidor_otro': 'Medidor',
                'ip': 'IP',
                'puerto': 'Puerto',
                'marca_secundaria': 'Marca',
                'observaciones': 'Obs',
                'retirado': 'Retirado',
                'serie_secundaria': 'Serie',
                'irregularidad': 'Irregularidad',
                'proyecto': 'Proyecto',
            }
            tipo_item = 'MODEM'
            identificador = equipo.serie

        campos_cambiados = [etiquetas[k] for k in etiquetas.keys() if before.get(k) != after.get(k)]
        if campos_cambiados:
            observacion = f'Modificación {tipo_item} {identificador}. Campos: {", ".join(campos_cambiados)}'
            _registrar_movimiento_inventario(equipo, tipo_item, request.user, observacion)
            audit_field_changes(
                actor_id=getattr(request.user, 'id', None),
                action='INVENTORY_UPDATE',
                entity=tipo_item,
                entity_id=str(equipo.pk),
                before=before,
                after=after,
                reason=f'Modificación inventario {tipo_item} {identificador}',
            )
        
        return JsonResponse({
            'success': True,
            'message': f'{tipo.capitalize()} modificado exitosamente'
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error al modificar: {str(e)}'
        })


@login_required
@admin_or_administrativo
@require_http_methods(["POST"])
def inventario_crear_view(request):
    """Crea un equipo individual en inventario y registra movimiento de recepción."""

    from django.db import IntegrityError

    tipo = request.POST.get('tipo', 'medidor').strip().lower()

    try:
        estado_id = request.POST.get('estado_id', '').strip()
        estado_obj = None
        if estado_id:
            try:
                estado_obj = EstadoInventario.objects.get(pk=int(estado_id))
            except (ValueError, TypeError, EstadoInventario.DoesNotExist):
                estado_obj = None

        if tipo == 'medidor':
            serie = request.POST.get('serie', '').strip()
            tipo_medidor = request.POST.get('tipo_medidor', '').strip().upper()
            if not serie:
                return JsonResponse({'success': False, 'message': 'La serie del medidor es obligatoria'})
            if tipo_medidor not in {'DIRECTO', 'INDIRECTO'}:
                return JsonResponse({'success': False, 'message': 'El tipo de medidor es obligatorio (DIRECTO o INDIRECTO)'})

            equipo = Medidor.objects.create(
                serie=serie,
                marca=request.POST.get('marca', '').strip(),
                caja=request.POST.get('caja', '').strip() or None,
                fecha_recepcion=request.POST.get('fecha_recepcion', '').strip() or None,
                estado_inventario=estado_obj,
                proyecto=request.POST.get('proyecto', '').strip(),
                tipo_medidor=tipo_medidor,
            )
            tipo_item = 'MEDIDOR'
            identificador = equipo.serie

        elif tipo == 'sim':
            imei = request.POST.get('imei', '').strip()
            if not imei:
                return JsonResponse({'success': False, 'message': 'El IMEI de la SIM es obligatorio'})

            equipo = SimCard.objects.create(
                imei=imei,
                operador=request.POST.get('operador', '').strip(),
                abonado=request.POST.get('abonado', '').strip(),
                direccion_ip=request.POST.get('direccion_ip', '').strip(),
                apn=request.POST.get('apn', '').strip(),
                fecha_recepcion=request.POST.get('fecha_recepcion', '').strip() or None,
                estado_inventario=estado_obj,
                proyecto=request.POST.get('proyecto', '').strip(),
            )
            tipo_item = 'SIM'
            identificador = equipo.imei or str(equipo.pk)

        elif tipo == 'modem':
            serie = request.POST.get('serie', '').strip()
            if not serie:
                return JsonResponse({'success': False, 'message': 'La serie del módem es obligatoria'})

            equipo = Modem.objects.create(
                serie=serie,
                marca=request.POST.get('marca', '').strip(),
                modelo=request.POST.get('modelo', '').strip(),
                imei=request.POST.get('imei', '').strip() or None,
                caja=request.POST.get('caja', '').strip() or None,
                fecha_recepcion=request.POST.get('fecha_recepcion', '').strip() or None,
                estado_inventario=estado_obj,
                proyecto=request.POST.get('proyecto', '').strip(),
            )
            tipo_item = 'MODEM'
            identificador = equipo.serie
        else:
            return JsonResponse({'success': False, 'message': 'Tipo de equipo no válido'})

        _registrar_movimiento_inventario(
            equipo,
            tipo_item,
            request.user,
            f'Alta manual de {tipo_item} {identificador}',
            tipo_movimiento='RECEPCION',
        )

        payload = {
            'success': True,
            'message': f'{tipo.capitalize()} creado correctamente',
            'tipo': tipo,
            'identificador': identificador,
        }
        if tipo == 'medidor':
            payload['serie'] = equipo.serie
            payload['marca'] = equipo.marca or ''
            payload['tipo_medidor'] = equipo.tipo_medidor or ''
            payload['tipo_medidor_display'] = equipo.get_tipo_medidor_display() if hasattr(equipo, 'get_tipo_medidor_display') else ''
        return JsonResponse(payload)

    except IntegrityError as exc:
        return JsonResponse({'success': False, 'message': f'Dato duplicado: {exc}'})
    except Exception as exc:
        return JsonResponse({'success': False, 'message': f'Error al crear equipo: {exc}'})


@login_required
@admin_or_administrativo
@require_http_methods(["POST"])
def inventario_modificar_masivo_view(request):
    """
    Edición múltiple unificada: combina cambios de campos (estado, cliente, proyecto,
    tipo medidor, etc.) con trazabilidad completa.
    """
    from usuarios.models import Usuario

    tipo = request.POST.get('tipo', 'medidor').strip().lower()
    ids_raw = request.POST.get('ids', '').strip()
    if not ids_raw:
        return JsonResponse({'success': False, 'message': 'Marca al menos un equipo en la lista antes de continuar.'})

    try:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    except Exception:
        ids = []

    if not ids:
        return JsonResponse({'success': False, 'message': 'La selección de equipos no es válida. Vuelve a marcarlos e intenta de nuevo.'})

    if tipo == 'medidor':
        queryset = Medidor.objects.filter(pk__in=ids, eliminado=False)
        tipo_item = 'MEDIDOR'
    elif tipo == 'sim':
        queryset = SimCard.objects.filter(pk__in=ids, eliminado=False)
        tipo_item = 'SIM'
    elif tipo == 'modem':
        queryset = Modem.objects.filter(pk__in=ids, eliminado=False)
        tipo_item = 'MODEM'
    else:
        return JsonResponse({'success': False, 'message': 'Tipo de equipo no reconocido.'})

    # --- Campos de edición ---
    estado_id = request.POST.get('estado_id', '').strip()
    estado_obj = None
    if estado_id:
        try:
            estado_obj = EstadoInventario.objects.get(pk=int(estado_id))
        except (ValueError, TypeError, EstadoInventario.DoesNotExist):
            pass

    cliente_texto = request.POST.get('cliente_texto', '').strip()
    cliente_id = request.POST.get('cliente_id', '').strip()
    entregado_a_id = request.POST.get('entregado_a_id', '').strip()
    entregado_a_nombre_bulk = request.POST.get('entregado_a_nombre', '').strip()
    medidor_id = request.POST.get('medidor_id', '').strip()
    proyecto = request.POST.get('proyecto', '').strip()
    tipo_medidor = request.POST.get('tipo_medidor', '').strip().upper()
    observacion = request.POST.get('observacion', '').strip()

    cliente_obj = None
    if cliente_texto:
        cliente_obj = Cliente.objects.filter(numero_cliente=cliente_texto, activo=True).first()
        if not cliente_obj:
            cliente_obj = Cliente.objects.create(
                numero_cliente=cliente_texto,
                direccion=f'Cliente {cliente_texto}',
                comuna='Por definir'
            )
    elif cliente_id:
        try:
            cliente_obj = Cliente.objects.get(pk=int(cliente_id))
        except (ValueError, TypeError, Cliente.DoesNotExist):
            pass

    entregado_obj = None
    if entregado_a_id:
        try:
            entregado_obj = Usuario.objects.get(pk=int(entregado_a_id))
        except (ValueError, TypeError, Usuario.DoesNotExist):
            pass

    medidor_obj = None
    if medidor_id:
        try:
            medidor_obj = Medidor.objects.get(pk=int(medidor_id), eliminado=False)
        except (ValueError, TypeError, Medidor.DoesNotExist):
            pass

    actualizados = 0
    sin_cambios = 0

    for equipo in queryset:
        campos = []

        # Cambio de estado
        if estado_obj and getattr(equipo, 'estado_inventario_id', None) != estado_obj.id:
            equipo.estado_inventario = estado_obj
            campos.append('Estado')

        # Cambios por tipo de equipo
        if tipo == 'medidor':
            if entregado_obj and equipo.entregado_a_id != entregado_obj.id:
                equipo.entregado_a = entregado_obj
                campos.append('Entregado A')
            if cliente_obj and equipo.cliente_id != cliente_obj.id:
                equipo.cliente = cliente_obj
                campos.append('Cliente')
            if proyecto and equipo.proyecto != proyecto:
                equipo.proyecto = proyecto
                campos.append('Proyecto')
            if tipo_medidor in {'DIRECTO', 'INDIRECTO'} and equipo.tipo_medidor != tipo_medidor:
                equipo.tipo_medidor = tipo_medidor
                campos.append('Tipo Medidor')

        elif tipo == 'sim':
            if entregado_obj and equipo.en_custodia_de_id != entregado_obj.id:
                equipo.en_custodia_de = entregado_obj
                campos.append('Entregado A')
            if cliente_obj and equipo.cliente_id != cliente_obj.id:
                equipo.cliente = cliente_obj
                campos.append('Cliente')
            if medidor_obj and equipo.medidor_id != medidor_obj.id:
                equipo.medidor = medidor_obj
                campos.append('Medidor')
            if proyecto and equipo.proyecto != proyecto:
                equipo.proyecto = proyecto
                campos.append('Proyecto')

        elif tipo == 'modem':
            if entregado_obj and equipo.entregado_a_id != entregado_obj.id:
                equipo.entregado_a = entregado_obj
                campos.append('Entregado A')
            if cliente_obj and equipo.cliente_id != cliente_obj.id:
                equipo.cliente = cliente_obj
                campos.append('Cliente')
            if medidor_obj and equipo.medidor_id != medidor_obj.id:
                equipo.medidor = medidor_obj
                campos.append('Medidor')
            if proyecto and equipo.proyecto != proyecto:
                equipo.proyecto = proyecto
                campos.append('Proyecto')

        if not campos:
            sin_cambios += 1
            continue

        equipo.save()

        if tipo_item == 'MEDIDOR':
            identificador = equipo.serie
        elif tipo_item == 'SIM':
            identificador = equipo.imei or equipo.abonado or str(equipo.pk)
        else:
            identificador = equipo.serie

        detalle = observacion or f'Edición múltiple {tipo_item}'
        _registrar_movimiento_inventario(
            equipo, tipo_item, request.user,
            f'Edición múltiple {tipo_item} {identificador}. Campos: {", ".join(campos)}. {detalle}'
        )
        actualizados += 1

    return JsonResponse({
        'success': True,
        'message': (
            f'Se actualizaron {actualizados} equipo(s).'
            + (f' {sin_cambios} ya tenían esos mismos datos.' if sin_cambios else '')
        ).strip(),
        'actualizados': actualizados,
        'sin_cambios': sin_cambios,
    })


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO'])
@require_http_methods(["GET"])
def inventario_exportar_view(request):
    """Exporta equipos a archivo Excel"""
    
    tipo = request.GET.get('tipo', 'medidor')
    modo = (request.GET.get('modo') or 'resumen').strip().lower()
    search = (request.GET.get('search') or request.GET.get('q') or '').strip()
    search_field = (request.GET.get('search_field') or request.GET.get('campo') or 'all').strip()
    limit_raw = (request.GET.get('limit') or '-1').strip()
    proyecto_filtro = (request.GET.get('proyecto') or '').strip()
    caja_filtro = (request.GET.get('caja') or '').strip()
    tipo_medidor_filtro = (request.GET.get('tipo_medidor') or '').strip()
    estado_filtro = (request.GET.get('estado') or '').strip()
    
    # Obtener datos base (solo activos: los soft-eliminados no se exportan)
    if tipo == 'medidor':
        equipos = Medidor.objects.filter(eliminado=False).select_related('entregado_a', 'estado_inventario', 'cliente', 'en_custodia_de', 'ubicacion_actual').order_by('serie')
        tipo_nombre = 'MEDIDORES'
        nombre_seccion = 'Medidores'
    elif tipo == 'sim':
        equipos = SimCard.objects.filter(eliminado=False).select_related('estado_inventario', 'cliente', 'medidor', 'ubicacion_actual', 'en_custodia_de').order_by('imei')
        tipo_nombre = 'SIM'
        nombre_seccion = 'SIM-Cards'
    elif tipo == 'modem':
        equipos = Modem.objects.filter(eliminado=False).select_related('cliente', 'medidor', 'entregado_a', 'estado_inventario', 'en_custodia_de', 'ubicacion_actual').order_by('serie')
        tipo_nombre = 'MODEMS'
        nombre_seccion = 'Modems'
    else:
        equipos = Medidor.objects.filter(eliminado=False).select_related('entregado_a', 'estado_inventario', 'cliente', 'en_custodia_de', 'ubicacion_actual').order_by('serie')
        tipo_nombre = 'MEDIDORES'
        nombre_seccion = 'Medidores'
    
    # Si es TECNICO, filtrar solo su equipo
    if request.user.rol == 'TECNICO':
        if tipo == 'sim':
            # SimCard usa 'en_custodia_de'
            equipos = equipos.filter(en_custodia_de=request.user)
        else:
            # Medidor y Modem usan 'entregado_a'
            equipos = equipos.filter(entregado_a=request.user)

    if proyecto_filtro:
        equipos = equipos.filter(proyecto__icontains=proyecto_filtro)

    if caja_filtro and tipo in ('medidor', 'modem'):
        equipos = equipos.filter(caja__icontains=caja_filtro)

    if tipo == 'medidor' and tipo_medidor_filtro:
        equipos = equipos.filter(tipo_medidor=tipo_medidor_filtro)

    if estado_filtro:
        if estado_filtro.isdigit():
            equipos = equipos.filter(estado_inventario_id=int(estado_filtro))
        else:
            equipos = equipos.filter(estado_inventario__nombre__icontains=estado_filtro)
    
    # Aplicar búsqueda (según filtros visibles en la tabla)
    if search:
        named_field_map = {
            'medidor': {
                'serie': 'serie',
                'marca': 'marca',
                'caja': 'caja',
                'tipo_medidor': 'tipo_medidor',
                'entregado_a': 'entregado_a__nombre_interno',
                'proyecto': 'proyecto',
                'estado': 'estado_inventario__nombre',
                'cliente': 'cliente__numero_cliente',
            },
            'sim': {
                'imei': 'imei',
                'operador': 'operador',
                'abonado': 'abonado',
                'direccion_ip': 'direccion_ip',
                'entregado_a': ['en_custodia_de__nombre_interno', 'entregado_a_nombre', 'entregado_a_otro'],
                'proyecto': 'proyecto',
                'estado': 'estado_inventario__nombre',
                'cliente': 'cliente__numero_cliente',
            },
            'modem': {
                'marca': 'marca',
                'modelo': 'modelo',
                'imei': 'imei',
                'serie': 'serie',
                'caja': 'caja',
                'tecnico': ['tecnico_responsable', 'entregado_a__nombre_interno', 'entregado_a_otro'],
                'entregado_a': ['tecnico_responsable', 'entregado_a__nombre_interno', 'entregado_a_otro'],
                'estado': 'estado_inventario__nombre',
                'cliente': 'cliente__numero_cliente',
                'proyecto': 'proyecto',
            },
        }
        if search_field == 'all':
            if tipo == 'medidor':
                equipos = equipos.filter(
                    Q(serie__icontains=search)
                    | Q(marca__icontains=search)
                    | Q(caja__icontains=search)
                    | Q(tipo_medidor__icontains=search)
                    | Q(entregado_a__nombre_interno__icontains=search)
                    | Q(entregado_a_info__icontains=search)
                    | Q(estado_inventario__nombre__icontains=search)
                    | Q(cliente__numero_cliente__icontains=search)
                    | Q(proyecto__icontains=search)
                )
            elif tipo == 'sim':
                equipos = equipos.filter(
                    Q(imei__icontains=search)
                    | Q(operador__icontains=search)
                    | Q(abonado__icontains=search)
                    | Q(en_custodia_de__nombre_interno__icontains=search)
                    | Q(entregado_a_nombre__icontains=search)
                    | Q(entregado_a_otro__icontains=search)
                    | Q(estado_inventario__nombre__icontains=search)
                    | Q(cliente__numero_cliente__icontains=search)
                    | Q(proyecto__icontains=search)
                )
            else:
                equipos = equipos.filter(
                    Q(marca__icontains=search)
                    | Q(modelo__icontains=search)
                    | Q(imei__icontains=search)
                    | Q(serie__icontains=search)
                    | Q(caja__icontains=search)
                    | Q(tecnico_responsable__icontains=search)
                    | Q(entregado_a__nombre_interno__icontains=search)
                    | Q(entregado_a_otro__icontains=search)
                    | Q(estado_inventario__nombre__icontains=search)
                    | Q(cliente__numero_cliente__icontains=search)
                    | Q(proyecto__icontains=search)
                )
        else:
            field_map = {
                'medidor': {
                    '1': 'serie',
                    '2': 'marca',
                    '3': 'caja',
                    '5': 'tipo_medidor',
                    '8': 'entregado_a__nombre_interno',
                    '9': 'proyecto',
                    '10': 'estado_inventario__nombre',
                    '11': 'cliente__numero_cliente',
                },
                'sim': {
                    '1': 'imei',
                    '2': 'operador',
                    '3': 'abonado',
                    '7': ['en_custodia_de__nombre_interno', 'entregado_a_nombre', 'entregado_a_otro'],
                    '9': 'proyecto',
                    '10': 'estado_inventario__nombre',
                    '11': 'cliente__numero_cliente',
                },
                'modem': {
                    '1': 'marca',
                    '2': 'modelo',
                    '3': 'imei',
                    '4': 'serie',
                    '7': 'caja',
                    '8': ['tecnico_responsable', 'entregado_a__nombre_interno', 'entregado_a_otro'],
                    '9': 'estado_inventario__nombre',
                    '10': 'cliente__numero_cliente',
                    '11': 'proyecto',
                },
            }
            # Aceptar claves numéricas (legacy) y nombres de campo de la lista
            field_map[tipo].update(named_field_map.get(tipo, {}))

            if tipo == 'medidor' and search_field in ('4', 'modulo'):
                val = search.lower()
                if val in ['si', 'sí', 'true', '1', 'yes']:
                    equipos = equipos.filter(modulo=True)
                elif val in ['no', 'false', '0']:
                    equipos = equipos.filter(modulo=False)
                else:
                    equipos = equipos.none()
            else:
                campo = field_map.get(tipo, {}).get(search_field)
                if isinstance(campo, (list, tuple)):
                    q_campo = Q()
                    for c in campo:
                        q_campo |= Q(**{f'{c}__icontains': search})
                    equipos = equipos.filter(q_campo)
                elif campo:
                    equipos = equipos.filter(**{f'{campo}__icontains': search})

    # Aplicar cantidad visible (selector Mostrar)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = -1
    if limit != -1:
        equipos = equipos[:limit]
    
    # Generar archivo Excel
    if modo == 'completo':
        wb = exportar_equipos_excel_completo(equipos, tipo_nombre)
        sufijo_archivo = 'completo'
    else:
        wb = exportar_equipos_excel(equipos, tipo_nombre)
        sufijo_archivo = 'resumen'
    
    # Preparar respuesta HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    from web.services.export_filenames import nombre_exportacion_con_fecha
    filename = nombre_exportacion_con_fecha(f'{nombre_seccion}-{sufijo_archivo}.xlsx')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
@admin_or_administrativo
@require_http_methods(["POST"])
def inventario_importar_view(request):
    """Importa equipos desde archivo Excel"""
    
    tipo = request.POST.get('tipo', 'medidor')
    archivo = request.FILES.get('archivo')
    
    if not archivo:
        return JsonResponse({
            'success': False,
            'message': 'No se seleccionó ningún archivo'
        })
    
    try:
        # Mapear tipo a nombre de equipos
        if tipo == 'medidor':
            tipo_nombre = 'MEDIDORES'
        elif tipo == 'sim':
            tipo_nombre = 'SIM'
        elif tipo == 'modem':
            tipo_nombre = 'MODEMS'
        else:
            tipo_nombre = 'MEDIDORES'
        
        # Realizar importación
        importacion = importar_equipos_excel(archivo, request.user, tipo_nombre)
        
        # Obtener resumen de errores si hay fallidas
        errores_resumen = []
        if importacion.fallidas > 0:
            from collections import Counter
            errores = importacion.errores.all()[:100]  # Limitar a 100 para análisis
            
            # Agrupar errores similares
            motivos = [error.motivo for error in errores]
            contador_errores = Counter(motivos)
            
            # Tomar los 5 errores más comunes
            for motivo, count in contador_errores.most_common(5):
                errores_resumen.append({
                    'motivo': motivo[:150],  # Limitar longitud
                    'count': count
                })
        
        return JsonResponse({
            'success': importacion.estado == 'COMPLETADO',
            'message': importacion.observaciones,
            'exitosas': importacion.exitosas,
            'fallidas': importacion.fallidas,
            'importacion_id': importacion.id,
            'errores_resumen': errores_resumen,
            'warnings': list(getattr(importacion, 'warnings', []) or [])[:40],
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error durante la importación: {str(e)}'
        })


@login_required
@admin_or_administrativo
def registro_errores_view(request):
    """Vista resumen del registro de errores de importaciones."""
    q = request.GET.get('q', '').strip()

    importaciones = ImportacionExcel.objects.filter(
        fallidas__gt=0
    ).order_by('-fecha_hora')

    if q:
        importaciones = importaciones.filter(
            Q(archivo_original__icontains=q)
            | Q(usuario_nombre__icontains=q)
            | Q(observaciones__icontains=q)
        )

    context = {
        'importaciones': importaciones,
        'q': q,
        'total_importaciones': importaciones.count(),
        'total_filas_fallidas': sum(i.fallidas for i in importaciones),
    }

    return render(request, 'importaciones/registro_errores.html', context)


@login_required
@admin_or_administrativo
def importacion_errores_view(request, pk):
    """Vista detallada de errores de una importación"""
    importacion = get_object_or_404(ImportacionExcel, pk=pk)
    
    # Obtener todos los errores asociados
    errores = importacion.errores.all().order_by('numero_fila')
    
    context = {
        'importacion': importacion,
        'errores': errores,
        'total_errores': errores.count(),
    }
    
    return render(request, 'importaciones/errores.html', context)


@login_required
@admin_or_administrativo
def importacion_corregir_fila_view(request, importacion_id, error_id):
    """AJAX: Obtener detalles de error para edición o procesar corrección"""
    if request.method == 'GET':
        error = get_object_or_404(ImportacionExcelError, pk=error_id, importacion_id=importacion_id)
        
        return JsonResponse({
            'numero_fila': error.numero_fila,
            'motivo': error.motivo,
            'data_cruda': error.data_cruda,
            'error_id': error.id,
        })
    
    elif request.method == 'POST':
        # Procesar reintentos de datos corregidos
        error = get_object_or_404(ImportacionExcelError, pk=error_id, importacion_id=importacion_id)
        importacion = error.importacion
        
        try:
            datos_raw = request.POST.get('datos_corregidos', '').strip()
            datos_corregidos = _parsear_datos_crudos_para_correccion(datos_raw)
            
            # Determinar el tipo de equipo y procesar
            tipo_equipo = importacion.tipo
            
            if tipo_equipo == 'EQUIPOS':
                # Determinar el tipo específico (MEDIDORES, SIM, MODEMS)
                tipo_especifico = _inferir_tipo_equipo_desde_datos(datos_corregidos)
                resultado = _procesar_datos_corregidos(
                    datos_corregidos, 
                    request.user,
                    tipo_especifico
                )
                
                if resultado['success']:
                    # Marcar error como resuelto
                    error.motivo = f"✓ Corregido por {request.user.nombre_interno} el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    error.save()
                    
                    # Actualizar estadísticas de importación
                    importacion.fallidas = max(0, importacion.fallidas - 1)
                    importacion.exitosas += 1
                    importacion.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Dato corregido e importado: {resultado.get("detalle", "")}',
                        'reload': True
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': f'Error al procesar: {resultado.get("error", "Error desconocido")}'
                    })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Tipo de importación no soportado para corrección'
                })
        
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'message': f'Error en formato JSON: {str(e)}'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al corregir: {str(e)}'
            })


def _parsear_datos_crudos_para_correccion(datos_raw):
    """Convierte el contenido de data_cruda a una lista Python utilizable."""
    if not datos_raw:
        raise ValueError('No se recibieron datos para corregir')

    normalizado = datos_raw.encode('utf-8').decode('unicode_escape')
    normalizado = normalizado.replace('\r', ' ').replace('\n', ' ').strip()

    def reemplazar_datetime(match):
        year, month, day = match.groups()
        return f"'{int(day):02d}-{int(month):02d}-{year}'"

    normalizado = re.sub(
        r'datetime\.datetime\((\d+),\s*(\d+),\s*(\d+)(?:,\s*\d+,\s*\d+(?:,\s*\d+)?)?\)',
        reemplazar_datetime,
        normalizado,
    )

    try:
        datos = ast.literal_eval(normalizado)
    except Exception as exc:
        raise ValueError(f'No se pudo interpretar la fila corregida: {exc}')

    if not isinstance(datos, list):
        raise ValueError('La corrección debe resolverse como una lista de valores')

    return datos


def _inferir_tipo_equipo_desde_datos(datos):
    """Infiere MEDIDORES, SIM o MODEMS según la estructura de la fila."""
    if not isinstance(datos, list):
        return 'MEDIDORES'
    if len(datos) >= 18:
        return 'MODEMS'
    if len(datos) >= 11:
        primer = datos[0]
        segundo = datos[1] if len(datos) > 1 else None
        primer_str = str(primer).strip() if primer is not None else ''
        segundo_str = str(segundo).strip() if segundo is not None else ''
        if primer_str.isdigit() and (hasattr(segundo, 'date') or '-' in segundo_str or '/' in segundo_str):
            return 'MEDIDORES'
        return 'SIM'
    return 'MEDIDORES'


def _procesar_datos_corregidos(datos, usuario, tipo_equipo):
    """
    Procesa datos corregidos manualmente por el usuario.
    Datos debe ser una lista: [fecha_recepcion, bodega, marca, caja, serie, modulo, ...]
    """
    try:
        from datetime import datetime as dt
        
        if tipo_equipo == 'MEDIDORES':
            if not isinstance(datos, list) or len(datos) < 11:
                return {
                    'success': False,
                    'error': 'Se requieren 11 campos: #, fecha_recepcion, bodega, marca, caja, medidor, modulo, fecha_entrega, entregado_a, estado, cliente'
                }

            correlativo = datos[0]
            fecha_recepcion = datos[1]
            bodega_ref = datos[2]
            marca = datos[3]
            caja = str(datos[4]).strip() if datos[4] is not None else ''
            serie = str(datos[5]).strip() if datos[5] is not None else ''
            modulo = str(datos[6]).strip() if len(datos) > 6 and datos[6] is not None else ''
            fecha_entrega = datos[7] if len(datos) > 7 else None
            entregado_a_info = str(datos[8]).strip() if len(datos) > 8 and datos[8] is not None else ''
            estado_nombre = str(datos[9]).strip() if len(datos) > 9 and datos[9] is not None else ''
            cliente_numero = str(datos[10]).strip() if len(datos) > 10 and datos[10] is not None else ''
            
            # Validaciones
            if not all([fecha_recepcion, serie]):
                return {
                    'success': False,
                    'error': 'Faltan campos requeridos'
                }
            
            # Verificar duplicados (solo serie es identificador único)
            if Medidor.objects.filter(serie=serie).exists():
                return {
                    'success': False,
                    'error': f'Ya existe medidor con serie {serie}'
                }
            
            # Convertir fechas admitiendo dd-mm-yyyy, dd/mm/yyyy y datetime
            def parse_fecha(valor):
                if not valor:
                    return None
                if hasattr(valor, 'date'):
                    return valor.date()
                if isinstance(valor, str):
                    for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d'):
                        try:
                            return dt.strptime(valor.strip(), fmt).date()
                        except ValueError:
                            continue
                return None

            fecha_recepcion = parse_fecha(fecha_recepcion)
            fecha_entrega = parse_fecha(fecha_entrega)

            if not fecha_recepcion:
                return {
                    'success': False,
                    'error': 'La fecha de recepción no es válida'
                }
            
            # Obtener o crear ubicación
            bodega = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
            if not bodega:
                bodega = Ubicacion.objects.create(
                    tipo='BODEGA_DELCO',
                    nombre='Bodega Principal'
                )
            
            estado = EstadoInventario.objects.filter(nombre__iexact=estado_nombre).first() if estado_nombre else None
            if not estado:
                estado = EstadoInventario.objects.filter(nombre='BODEGA').first()
            if not estado:
                estado = EstadoInventario.objects.create(nombre='BODEGA')

            cliente_obj = None
            if cliente_numero:
                cliente_obj = Cliente.objects.filter(numero_cliente=cliente_numero).first()
                if not cliente_obj:
                    cliente_obj = Cliente.objects.create(
                        numero_cliente=cliente_numero,
                        direccion=f'Cliente {cliente_numero}',
                        comuna='Por definir'
                    )

            modulo_bool = None
            if modulo:
                modulo_bool = modulo.lower() in ('si', 'sí', 'true', '1', 'yes')
            
            # Crear medidor
            medidor = Medidor.objects.create(
                fecha_recepcion=fecha_recepcion,
                bodega=str(bodega_ref).strip() if bodega_ref else '',
                marca=str(marca).strip() if marca else '',
                caja=caja,
                serie=serie,
                modulo=modulo_bool,
                fecha_entrega=fecha_entrega,
                entregado_a_info=entregado_a_info,
                estado_inventario=estado,
                cliente=cliente_obj,
                ubicacion_actual=bodega
            )

            observaciones = []
            if correlativo:
                observaciones.append(f'Correlativo: {correlativo}')
            if modulo:
                observaciones.append(f'Modulo original: {modulo}')
            if observaciones:
                medidor.observaciones = ' | '.join(observaciones)
                medidor.save(update_fields=['observaciones'])
            
            return {
                'success': True,
                'detalle': f'Medidor serie {serie} caja {caja}'
            }
        
        elif tipo_equipo == 'SIM':
            # Similar para SIM
            if not isinstance(datos, list) or len(datos) < 3:
                return {
                    'success': False,
                    'error': 'Se requieren al menos 3 campos: msisdn, proveedor, serie_plastico'
                }
            
            msisdn = str(datos[0]).strip()
            proveedor = str(datos[1]).strip()
            plastico = str(datos[2]).strip()
            ip = str(datos[3]).strip() if len(datos) > 3 else ''
            
            if SimCard.objects.filter(msisdn=msisdn).exists():
                return {
                    'success': False,
                    'error': f'Ya existe SIM con msisdn {msisdn}'
                }
            
            bodega = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
            if not bodega:
                bodega = Ubicacion.objects.create(
                    tipo='BODEGA_DELCO',
                    nombre='Bodega Principal'
                )
            
            estado = EstadoInventario.objects.filter(nombre='BODEGA').first()
            if not estado:
                estado = EstadoInventario.objects.create(nombre='BODEGA')
            
            sim = SimCard.objects.create(
                msisdn=msisdn,
                proveedor=proveedor,
                serie_plastico=plastico,
                ip_fija=ip if ip else None,
                estado_inventario=estado,
                ubicacion_actual=bodega
            )
            
            return {
                'success': True,
                'detalle': f'SIM {msisdn}'
            }
        
        elif tipo_equipo == 'MODEMS':
            # Formato real de módems: 18 columnas (A-R)
            if not isinstance(datos, list) or len(datos) < 18:
                return {
                    'success': False,
                    'error': 'Se requieren 18 campos para módems según la plantilla A-R'
                }

            marca = str(datos[0]).strip() if datos[0] is not None else ''
            modelo = str(datos[1]).strip() if datos[1] is not None else ''
            imei = str(datos[2]).strip() if datos[2] is not None else ''
            serie = str(datos[3]).strip() if datos[3] is not None else ''
            fecha_recepcion = datos[4]
            fecha_entrega = datos[5]
            caja = str(datos[6]).strip() if datos[6] is not None else ''
            tecnico_responsable = str(datos[7]).strip() if datos[7] is not None else ''
            cliente_numero = str(datos[8]).strip() if datos[8] is not None else ''
            medidor_serie = str(datos[9]).strip() if datos[9] is not None else ''
            observaciones = str(datos[10]).strip() if datos[10] is not None else ''
            ip = str(datos[11]).strip() if datos[11] is not None else ''
            puerto = str(datos[12]).strip() if datos[12] is not None else ''
            marca_secundaria = str(datos[13]).strip() if datos[13] is not None else ''
            retirado = str(datos[14]).strip() if datos[14] is not None else ''
            serie_secundaria = str(datos[15]).strip() if datos[15] is not None else ''
            irregularidad = str(datos[16]).strip() if datos[16] is not None else ''
            proyecto = str(datos[17]).strip() if datos[17] is not None else ''
            
            if Modem.objects.filter(serie=serie).exists():
                return {
                    'success': False,
                    'error': f'Ya existe módem con serie {serie}'
                }

            def parse_fecha(valor):
                if not valor:
                    return None
                if hasattr(valor, 'date'):
                    return valor.date()
                if isinstance(valor, str):
                    for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d'):
                        try:
                            return dt.strptime(valor.strip(), fmt).date()
                        except ValueError:
                            continue
                return None

            fecha_recepcion = parse_fecha(fecha_recepcion)
            fecha_entrega = parse_fecha(fecha_entrega)
            
            bodega = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
            if not bodega:
                bodega = Ubicacion.objects.create(
                    tipo='BODEGA_DELCO',
                    nombre='Bodega Principal'
                )
            
            estado = EstadoInventario.objects.filter(nombre='BODEGA').first()
            if not estado:
                estado = EstadoInventario.objects.create(nombre='BODEGA')

            cliente_obj = None
            if cliente_numero:
                cliente_obj = Cliente.objects.filter(numero_cliente=cliente_numero).first()
                if not cliente_obj:
                    cliente_obj = Cliente.objects.create(
                        numero_cliente=cliente_numero,
                        direccion=f'Cliente {cliente_numero}',
                        comuna='Por definir'
                    )

            medidor_obj = None
            if medidor_serie:
                medidor_obj = Medidor.objects.filter(serie=medidor_serie).first()
            
            modem = Modem.objects.create(
                fecha_recepcion=fecha_recepcion,
                fecha_entrega=fecha_entrega,
                bodega='',
                marca=marca,
                modelo=modelo,
                imei=imei or None,
                caja=caja,
                serie=serie,
                tecnico_responsable=tecnico_responsable,
                cliente=cliente_obj,
                medidor=medidor_obj,
                observaciones=observaciones,
                ip=ip,
                puerto=puerto,
                marca_secundaria=marca_secundaria,
                retirado=retirado,
                serie_secundaria=serie_secundaria,
                irregularidad=irregularidad,
                proyecto=proyecto,
                estado_inventario=estado,
                ubicacion_actual=bodega
            )
            
            return {
                'success': True,
                'detalle': f'Módem serie {serie} marca {marca}'
            }

        else:
            return {
                'success': False,
                'error': 'Tipo de equipo no soportado'
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def profile_view(request):
    """Vista de perfil del usuario - retorna JSON con datos del usuario"""
    
    return JsonResponse({
        'rut': request.user.rut,
        'nombre_interno': request.user.nombre_interno,
        'nombre': request.user.nombre,
        'apellido': request.user.apellido,
        'email': request.user.email,
        'rol': request.user.rol,
        'is_active': request.user.is_active,
        'date_joined': (
            request.user.fecha_creacion.strftime('%d/%m/%Y %H:%M')
            if getattr(request.user, 'fecha_creacion', None)
            else ''
        ),
    })


@login_required
@role_required(['ADMIN'])
def usuarios_list_view(request):
    """Listar todos los usuarios activos y pasar roles para filtro select"""
    from usuarios.models import Usuario
    usuarios = Usuario.objects.filter(is_active=True).order_by('nombre_interno')
    roles_order = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'GERENCIA', 'AUDITOR']
    context = {
        'usuarios': usuarios,
        'roles_order': roles_order,
        'total_usuarios': usuarios.count(),
    }
    return render(request, 'usuarios/list.html', context)


@login_required
@role_required(['ADMIN'])
def usuario_crear_view(request):
    """Crear un nuevo usuario"""
    from usuarios.models import Usuario
    
    if request.method == "POST":
        rut = request.POST.get('rut', '').strip()
        nombre_interno = request.POST.get('nombre_interno', '').strip()
        email = request.POST.get('email', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        password = request.POST.get('password', '').strip()
        rol = request.POST.get('rol', 'ADMINISTRATIVO').strip()
        
        # Validaciones
        if not all([rut, nombre_interno, email, password, rol]):
            messages.error(request, "Todos los campos son obligatorios")
            return redirect('usuario_crear')
        
        if Usuario.objects.filter(rut=rut).exists():
            messages.error(request, f"Ya existe un usuario con RUT {rut}")
            return redirect('usuario_crear')
        
        if Usuario.objects.filter(email=email).exists():
            messages.error(request, f"Ya existe un usuario con email {email}")
            return redirect('usuario_crear')

        try:
            usuario = Usuario.objects.create_user(
                rut=rut,
                email=email,
                password=password,
                nombre_interno=nombre_interno,
                nombre=nombre,
                apellido=apellido,
                rol=rol,
                is_active=True
            )
            messages.success(request, f"Usuario {nombre_interno} ({rol}) creado correctamente")
            return redirect('usuarios_list')
        except Exception as e:
            messages.error(request, f"Error al crear usuario: {str(e)}")
            return redirect('usuario_crear')
    
    roles = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'GERENCIA', 'AUDITOR']
    context = {'roles': roles}
    return render(request, 'usuarios/crear.html', context)


@login_required
@role_required(['ADMIN'])
def usuario_editar_view(request, pk):
    """Editar un usuario"""
    from usuarios.models import Usuario
    
    try:
        usuario = Usuario.objects.get(pk=pk)
    except Usuario.DoesNotExist:
        messages.error(request, "Usuario no encontrado")
        return redirect('usuarios_list')
    
    if request.method == "POST":
        nombre_interno = request.POST.get('nombre_interno', '').strip()
        rol = request.POST.get('rol', usuario.rol).strip()
        nueva_contrasena = request.POST.get('nueva_contrasena', '').strip()
        confirmar_contrasena = request.POST.get('confirmar_contrasena', '').strip()
        # Cambiar contraseña solo si ambos campos están llenos y coinciden
        if nueva_contrasena or confirmar_contrasena:
            if nueva_contrasena != confirmar_contrasena:
                error_msg = "Las contraseñas no coinciden"
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return redirect('usuario_editar', pk=pk)
            usuario.set_password(nueva_contrasena)
        usuario.nombre_interno = nombre_interno
        usuario.rol = rol
        usuario.save()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'usuario': {
                    'id': usuario.id,
                    'nombre_interno': usuario.nombre_interno,
                    'nombre': usuario.nombre,
                    'apellido': usuario.apellido,
                    'email': usuario.email,
                    'rol': usuario.rol,
                }
            })
        messages.success(request, "Usuario actualizado correctamente")
        return redirect('usuarios_list')
    
    roles = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'GERENCIA', 'AUDITOR']
    context = {
        'usuario': usuario,
        'roles': roles,
    }
    return render(request, 'usuarios/editar.html', context)


@login_required
@role_required(['ADMIN'])
def usuario_reset_password_view(request, pk):
    """Restablecer contraseña de un usuario (solo ADMIN)"""
    from usuarios.models import Usuario
    
    try:
        usuario = Usuario.objects.get(pk=pk)
    except Usuario.DoesNotExist:
        messages.error(request, "Usuario no encontrado")
        return redirect('usuarios_list')
    
    # No permitir cambiar contraseña de admins
    if usuario.rol == 'ADMIN':
        messages.error(request, "No se puede cambiar la contraseña de administradores desde aquí")
        return redirect('usuario_editar', pk=pk)
    
    if request.method == "POST":
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        if not new_password:
            messages.error(request, "La contraseña no puede estar vacía")
            return redirect('usuario_editar', pk=pk)
        
        if new_password != confirm_password:
            messages.error(request, "Las contraseñas no coinciden")
            return redirect('usuario_editar', pk=pk)
        
        if len(new_password) < 6:
            messages.error(request, "La contraseña debe tener al menos 6 caracteres")
            return redirect('usuario_editar', pk=pk)
        
        usuario.set_password(new_password)
        usuario.save()
        
        messages.success(request, f"Contraseña de {usuario.nombre_interno} restablecida correctamente")
        return redirect('usuario_editar', pk=pk)
    
    return redirect('usuario_editar', pk=pk)


@login_required
def clientes_list_view(request):
    """Lista de clientes activos con paginación servidor (no carga todo el padrón en HTML)."""
    from django.core.paginator import Paginator
    from django.db.models import Count
    from web.services.filtros_export import es_sin_proyecto, queryset_clientes_filtrado

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
    try:
        per_page = int(request.GET.get('per_page') or 50)
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in (25, 50, 100, 200):
        per_page = 50

    base_activos = queryset_clientes_filtrado(request, aplicar_filtros=False)
    clientes_qs = queryset_clientes_filtrado(request, aplicar_filtros=True)

    # order_by() limpia el ordenamiento: si no, sus campos entran al GROUP BY
    # y cada grupo cuenta 1 (nunca se detectarían duplicados).
    numeros_duplicados = set(
        base_activos
        .order_by()
        .values('numero_cliente')
        .annotate(c=Count('id'))
        .filter(c__gt=1)
        .values_list('numero_cliente', flat=True)
    )

    def _valores_filtro(campo):
        """Valores únicos para combos (sin repetir por espacios/mayúsculas)."""
        unicos = {}
        for valor in (
            base_activos.exclude(**{f'{campo}__isnull': True})
            .exclude(**{campo: ''})
            .values_list(campo, flat=True)
            .iterator()
        ):
            if valor is None:
                continue
            texto = str(valor).strip()
            if not texto:
                continue
            # Ignorar valores basura frecuentes en imports
            if texto.casefold() in {'null', 'nulo', 'none', '-'}:
                continue
            # Proyecto: no listar variantes de "sin proyecto" (ya hay opción fija en el filtro)
            if campo == 'proyecto' and es_sin_proyecto(texto):
                continue
            clave = texto.casefold()
            if clave not in unicos:
                unicos[clave] = texto
        return sorted(unicos.values(), key=lambda item: item.casefold())

    comunas_disponibles = _valores_filtro('comuna')
    sectores_disponibles = _valores_filtro('sector')
    tipos_suministro_disponibles = _valores_filtro('tipo_suministro')
    proyectos_disponibles = _valores_filtro('proyecto')
    marcas_disponibles = _valores_filtro('meter_manufacturer_id')
    empresas_disponibles = _valores_filtro('empresa')

    total_fichas = clientes_qs.count()
    total_clientes = clientes_qs.values('numero_cliente').distinct().count()
    page_obj = Paginator(clientes_qs, per_page).get_page(request.GET.get('page') or 1)
    ultima_importacion_clientes = ImportacionExcel.objects.filter(tipo='CLIENTES').order_by('-id').first()

    query_params = request.GET.copy()
    query_params.pop('page', None)

    from web.services.dashboard_metrics import ALARMAS_CLIENTES_LABELS
    alarma_label = ALARMAS_CLIENTES_LABELS.get(alarma, '')

    context = {
        'clientes': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_params.urlencode(),
        'q': q,
        'numero_cliente_seleccionado': numero_cliente_filtro,
        'comuna_seleccionada': comuna_filtro,
        'sector_seleccionado': sector_filtro,
        'tipo_suministro_seleccionado': tipo_suministro_filtro,
        'proyecto_seleccionado': proyecto_filtro,
        'marca_seleccionada': marca_filtro,
        'serie_seleccionada': serie_filtro,
        'empresa_seleccionada': empresa_filtro,
        'ip_seleccionada': ip_filtro,
        'nombre_seleccionado': nombre_filtro,
        'comunas_disponibles': comunas_disponibles,
        'sectores_disponibles': sectores_disponibles,
        'tipos_suministro_disponibles': tipos_suministro_disponibles,
        'proyectos_disponibles': proyectos_disponibles,
        'marcas_disponibles': marcas_disponibles,
        'empresas_disponibles': empresas_disponibles,
        'solo_duplicados': solo_duplicados,
        'alarma': alarma,
        'alarma_label': alarma_label,
        'per_page': per_page,
        'total_clientes': total_clientes,
        'total_fichas': total_fichas,
        'numeros_duplicados': numeros_duplicados,
        'numeros_duplicados_json': json.dumps(sorted(numeros_duplicados)),
        'total_numeros_duplicados': len(numeros_duplicados),
        'ultima_importacion_total_filas': ultima_importacion_clientes.total_filas if ultima_importacion_clientes else None,
        'puede_editar': request.user.rol in ['ADMIN', 'ADMINISTRATIVO'],
        'paginacion_servidor': True,
        'estado_restriccion_choices': Cliente.ESTADO_RESTRICCION_CHOICES,
    }
    return render(request, 'clientes/list.html', context)


@login_required
def clientes_exportar_view(request):
    """Exportar clientes a Excel (respeta filtros activos salvo padrón completo)."""
    from web.services.filtros_export import queryset_clientes_filtrado
    from web.services.export_filenames import nombre_exportacion_con_fecha

    modo = (request.GET.get('modo') or 'filtrado').strip().lower()
    if modo in ('completo_padron', 'padron', 'todos', 'full'):
        clientes = queryset_clientes_filtrado(request, aplicar_filtros=False)
        filename = 'clientes_padron_completo.xlsx'
    elif modo in ('completo', 'historial'):
        from importaciones.utils import exportar_clientes_excel_completo
        clientes = queryset_clientes_filtrado(request, aplicar_filtros=True)
        wb = exportar_clientes_excel_completo(clientes)
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = nombre_exportacion_con_fecha('clientes_completos.xlsx')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response
    else:
        clientes = queryset_clientes_filtrado(request, aplicar_filtros=True)
        filename = 'clientes_filtrado.xlsx'

    wb = exportar_clientes_excel(clientes)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = nombre_exportacion_con_fecha(filename)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO'])
def clientes_importar_view(request):
    """Importar clientes desde archivo Excel."""
    archivo = request.FILES.get('archivo')
    modo_importacion = (request.POST.get('modo_importacion', 'incremental') or 'incremental').strip().lower()
    sincronizar_completo = modo_importacion in ('sync', 'sincronizar', 'completo', 'full')
    if not archivo:
        return JsonResponse({'success': False, 'message': 'No se seleccionó ningún archivo'})

    filename = getattr(archivo, 'name', '')
    if not filename.lower().endswith('.xlsx'):
        return JsonResponse({'success': False, 'message': 'Solo se aceptan archivos Excel .xlsx'})

    try:
        importacion = importar_clientes_excel(archivo, request.user, sincronizar_completo=sincronizar_completo)
        errores = list(importacion.errores.values_list('motivo', flat=True).distinct()[:30])
        advertencias = list(dict.fromkeys(getattr(importacion, 'warnings', [])))[:40]
        warning_summary = getattr(importacion, 'warning_summary', {}) or {}
        clientes_unicos_archivo = int(warning_summary.get('clientes_unicos_detectados') or 0)
        clientes_unicos_sistema = (
            Cliente.objects.filter(activo=True)
            .exclude(numero_cliente__in=['', '0'])
            .values('numero_cliente')
            .distinct()
            .count()
        )

        if importacion.estado == 'COMPLETADO':
            message = (
                f'Importación completada: {clientes_unicos_archivo} clientes en el archivo '
                f'({importacion.exitosas} filas correctas'
                f'{f", {importacion.fallidas} con error" if importacion.fallidas else ""}). '
                f'En el sistema hay {clientes_unicos_sistema} clientes.'
            )
        else:
            message = (
                f'Importación con problemas: {importacion.exitosas} filas correctas '
                f'y {importacion.fallidas} con error. '
                f'Clientes en archivo: {clientes_unicos_archivo}. '
                f'En el sistema: {clientes_unicos_sistema}.'
            )

        return JsonResponse({
            'success': importacion.estado == 'COMPLETADO',
            'message': message,
            'details': importacion.observaciones,
            'modo_importacion': 'sincronizacion_completa' if sincronizar_completo else 'incremental',
            'errors': errores,
            'warnings': advertencias,
            'warning_summary': warning_summary,
            'exitosas': importacion.exitosas,
            'fallidas': importacion.fallidas,
            'total_filas': importacion.total_filas,
            'clientes_unicos_archivo': clientes_unicos_archivo,
            'clientes_unicos_sistema': clientes_unicos_sistema,
            'importacion_id': importacion.id,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error durante la importación: {str(e)}'})


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO'])
def cliente_crear_view(request):
    """Crear cliente (roles ADMIN y ADMINISTRATIVO)."""
    if request.method == 'POST':
        numero_cliente = request.POST.get('numero_cliente', '').strip()
        comuna = request.POST.get('comuna', '').strip()
        tipo_suministro = request.POST.get('tipo_suministro', '').strip()
        sector = request.POST.get('sector', '').strip()
        customer_name = request.POST.get('customer_name', '').strip()
        installation_address = request.POST.get('installation_address', '').strip()
        # Dirección base se deriva de la instalación (ya no se pide por separado).
        direccion = installation_address
        proyecto = request.POST.get('proyecto', '').strip()
        medidor_opcion = request.POST.get('medidor_opcion', '').strip().lower()
        if medidor_opcion not in {'crear_medidor', 'sin_medidor', 'asignar_lista'}:
            # Compatibilidad: si viene serie sin opción, asumir asignación.
            if request.POST.get('meter_serial_n_1', '').strip():
                medidor_opcion = 'asignar_lista'
            else:
                medidor_opcion = ''
        sin_medidor = medidor_opcion == 'sin_medidor'
        meter_manufacturer_id = request.POST.get('meter_manufacturer_id', '').strip()
        meter_serial_n_1 = '' if sin_medidor else request.POST.get('meter_serial_n_1', '').strip()
        ultimo_acceso = request.POST.get('ultimo_acceso', '').strip()
        ultimo_perfil_carga = request.POST.get('ultimo_perfil_carga', '').strip()
        ultimo_reset = request.POST.get('ultimo_reset', '').strip()
        ultimo_registro_facturacion = request.POST.get('ultimo_registro_facturacion', '').strip()
        note = request.POST.get('note', '').strip()
        ip = normalize_ip_value(request.POST.get('ip', '').strip()) or ''
        puerto = request.POST.get('puerto', '').strip()
        modem = request.POST.get('modem', '').strip()
        fecha_registro = request.POST.get('fecha_registro', '').strip()
        estado_restriccion = (request.POST.get('estado_restriccion') or '').strip().upper()
        justificacion_restriccion = (request.POST.get('justificacion_restriccion') or '').strip()
        codigos_ok = {c for c, _ in Cliente.ESTADO_RESTRICCION_CHOICES}
        if estado_restriccion and estado_restriccion not in codigos_ok:
            estado_restriccion = ''

        proyecto_final = proyecto or 'SIN PROYECTO'
        ultimo_perfil_carga_final = ultimo_perfil_carga or 'SIN PERFIL'
        meter_exists_other_active = bool(
            meter_serial_n_1
            and Cliente.objects.filter(meter_serial_n_1__iexact=meter_serial_n_1, activo=True).exists()
        )
        modem_assigned_other_active = bool(
            modem
            and Cliente.objects.filter(modem__iexact=modem, activo=True).exists()
        )
        ip_assigned_other_active = bool(
            ip
            and Cliente.objects.filter(ip__iexact=ip, activo=True).exists()
        )
        modem_estado = None
        if modem:
            modem_obj = Modem.objects.filter(serie__iexact=modem).select_related('estado_inventario').first()
            if modem_obj and modem_obj.estado_inventario:
                modem_estado = modem_obj.estado_inventario.nombre

        validation_issues = merge_issues(
            validate_ip_format(ip),
            validate_ip_port_coherence(ip, puerto),
            validate_ip_duplicate_on_active_clients(ip, ip_assigned_other_active),
            validate_ip_restricted_status(estado_restriccion, justificacion_restriccion, ip),
            validate_restriccion_con_justificacion(estado_restriccion, justificacion_restriccion),
            validate_meter_uniqueness(meter_serial_n_1, meter_exists_other_active),
            validate_meter_required_fields(meter_serial_n_1, meter_manufacturer_id),
            validate_modem_assignment(modem, modem_assigned_other_active),
            validate_modem_inventory_status(modem_estado),
        )

        blocking_errors = [issue for issue in validation_issues if issue.severity == 'error']
        if blocking_errors:
            for issue in blocking_errors:
                messages.error(request, issue.message)
            return redirect('cliente_crear')

        for issue in validation_issues:
            if issue.severity == 'warning':
                messages.warning(request, issue.message)

        campos_obligatorios = [
            numero_cliente,
            comuna,
            tipo_suministro,
            sector,
            customer_name,
            installation_address,
        ]
        if not sin_medidor:
            campos_obligatorios.append(meter_serial_n_1)

        if not medidor_opcion or not all(campos_obligatorios):
            if not medidor_opcion or (not sin_medidor and not meter_serial_n_1):
                messages.error(
                    request,
                    'El medidor es obligatorio. Elige uno de la lista, créalo con el popup o selecciona “Sin medidor”.',
                )
            else:
                messages.error(request, 'Faltan campos obligatorios: asegúrate de completar todos los datos requeridos.')
            return redirect('cliente_crear')

        if sin_medidor:
            duplicado_sin_medidor = Cliente.objects.filter(
                numero_cliente=numero_cliente,
                activo=True,
            ).filter(
                models.Q(meter_serial_n_1__isnull=True) | models.Q(meter_serial_n_1=''),
            ).exists()
            if duplicado_sin_medidor:
                messages.error(
                    request,
                    f'Ya existe un cliente activo con número {numero_cliente} sin medidor.',
                )
                return redirect('cliente_crear')
        elif Cliente.objects.filter(
            numero_cliente=numero_cliente,
            meter_serial_n_1__iexact=meter_serial_n_1,
            activo=True,
        ).exists():
            messages.error(request, f'Ya existe un cliente activo con numero {numero_cliente} y la misma serie {meter_serial_n_1}.')
            return redirect('cliente_crear')

        cliente_duplicado_serie_distinta = False
        if meter_serial_n_1:
            cliente_duplicado_serie_distinta = Cliente.objects.filter(
                numero_cliente=numero_cliente,
                activo=True,
            ).exclude(
                meter_serial_n_1__iexact=meter_serial_n_1,
            ).exists()
        elif not sin_medidor:
            cliente_duplicado_serie_distinta = Cliente.objects.filter(
                numero_cliente=numero_cliente,
                activo=True,
            ).exists()

        ip_duplicada_serie_distinta = False
        if ip:
            if meter_serial_n_1 and Cliente.objects.filter(
                ip__iexact=ip,
                meter_serial_n_1__iexact=meter_serial_n_1,
                activo=True,
            ).exists():
                messages.error(request, f'La IP {ip} ya está asignada a un cliente activo con la misma serie {meter_serial_n_1}.')
                return redirect('cliente_crear')

            if meter_serial_n_1:
                ip_duplicada_serie_distinta = Cliente.objects.filter(
                    ip__iexact=ip,
                    activo=True,
                ).exclude(
                    meter_serial_n_1__iexact=meter_serial_n_1,
                ).exists()
            else:
                ip_duplicada_serie_distinta = Cliente.objects.filter(
                    ip__iexact=ip,
                    activo=True,
                ).exists()

        medidor_obj = None
        if meter_serial_n_1:
            medidor_obj = Medidor.objects.filter(serie=meter_serial_n_1).first()
            if not medidor_obj:
                messages.error(request, f'No existe un medidor con serie {meter_serial_n_1}. Créalo con el popup de medidor.')
                return redirect('cliente_crear')
            if Cliente.objects.filter(medidor_actual=medidor_obj, activo=True).exists():
                messages.error(request, f'El medidor {meter_serial_n_1} ya está asignado a otro cliente o está duplicado.')
                return redirect('cliente_crear')
            if not meter_manufacturer_id and medidor_obj.marca:
                meter_manufacturer_id = medidor_obj.marca

        nuevo_cliente = Cliente.objects.create(
            numero_cliente=numero_cliente,
            direccion=direccion,
            comuna=comuna,
            tipo_suministro=tipo_suministro,
            pod=None,
            sector=sector,
            city=None,
            customer_name=customer_name,
            installation_address=installation_address,
            proyecto=proyecto_final,
            meter_manufacturer_id=meter_manufacturer_id or None,
            meter_serial_n_1=meter_serial_n_1 or None,
            client_type=None,
            ultimo_acceso=ultimo_acceso,
            ultimo_perfil_carga=ultimo_perfil_carga_final,
            ultimo_perfil_instrumentacion=None,
            ultimo_reset=ultimo_reset or None,
            ultimo_registro_facturacion=ultimo_registro_facturacion or None,
            note=note or None,
            trabajo=None,
            ip=ip or None,
            puerto=puerto or None,
            modem=modem or None,
            fecha_registro=fecha_registro or None,
            medidor_actual=medidor_obj,
            estado_telemetria='SIN_MEDIDOR' if sin_medidor else 'OPERATIVO',
            estado_restriccion=estado_restriccion,
            justificacion_restriccion=justificacion_restriccion if estado_restriccion else '',
            activo=True,
        )
        from clientes.proyecto_historial import registrar_cambio_proyecto
        registrar_cambio_proyecto(
            nuevo_cliente,
            proyecto_final,
            usuario=request.user,
            motivo='Alta de cliente',
            actualizar_campo=True,
        )
        register_audit_event(
            AuditEvent(
                actor_id=getattr(request.user, 'id', None),
                action='CLIENT_CREATE',
                entity='Cliente',
                entity_id=str(nuevo_cliente.id),
                field_name='numero_cliente',
                old_value=None,
                new_value=numero_cliente,
                reason='Alta de cliente desde gestión manual',
            )
        )
        audit_field_changes(
            actor_id=getattr(request.user, 'id', None),
            action='CLIENT_CREATE_FIELD',
            entity='Cliente',
            entity_id=str(nuevo_cliente.id),
            before={'meter_serial_n_1': None, 'ip': None, 'puerto': None, 'modem': None},
            after={
                'meter_serial_n_1': meter_serial_n_1 or None,
                'ip': ip or None,
                'puerto': puerto or None,
                'modem': modem or None,
            },
            reason='Equipos y conectividad en alta de cliente',
        )
        if cliente_duplicado_serie_distinta:
            serie_msg = meter_serial_n_1 or 'sin medidor'
            messages.warning(
                request,
                f'Cliente duplicado detectado: el numero {numero_cliente} ya existía con otra serie. '
                f'Se creó el cliente con serie distinta ({serie_msg}).'
            )
        if ip_duplicada_serie_distinta:
            serie_msg = meter_serial_n_1 or 'sin medidor'
            messages.warning(
                request,
                f'IP duplicada detectada: la IP {ip} ya existía con otra serie de medidor. '
                f'Se creó el cliente con serie distinta ({serie_msg}).'
            )
        messages.success(request, f'Cliente {numero_cliente} creado correctamente.')
        return redirect('clientes_list')

    estados_permitidos = ['En bodega', 'En Trayecto', 'Instalado', 'Retirado', 'En reparación', 'Dado de baja', 'En peaje']
    estados_disponibles = list(EstadoInventario.objects.filter(nombre__in=estados_permitidos))
    estados_disponibles.sort(
        key=lambda e: estados_permitidos.index(e.nombre) if e.nombre in estados_permitidos else 99
    )

    asignados_ids = set(
        Cliente.objects.filter(activo=True, medidor_actual_id__isnull=False)
        .values_list('medidor_actual_id', flat=True)
    )
    # La tabla se llena por búsqueda (API); no cargar miles de filas en el HTML.
    medidores_libres = []

    from web.services.filtros_export import es_sin_proyecto
    proyectos_disponibles = sorted({
        (p or '').strip()
        for p in Cliente.objects.filter(activo=True)
        .exclude(proyecto__isnull=True)
        .exclude(proyecto='')
        .values_list('proyecto', flat=True)
        if (p or '').strip()
        and not es_sin_proyecto(p)
    }, key=lambda x: x.casefold())

    return render(request, 'clientes/crear.html', {
        'tipo_medidor_choices': Medidor.TIPO_MEDIDOR_CHOICES,
        'estados_disponibles': estados_disponibles,
        'medidores_libres': medidores_libres,
        'medidores_asignados_count': len(asignados_ids),
        'estado_restriccion_choices': Cliente.ESTADO_RESTRICCION_CHOICES,
        'proyectos_disponibles': proyectos_disponibles,
    })


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO'])
def cliente_editar_view(request, pk):
    """Editar cliente (roles ADMIN y ADMINISTRATIVO). Soporta modal AJAX sin salir del listado."""
    cliente = get_object_or_404(Cliente, pk=pk, activo=True)

    def _quiere_json():
        if request.GET.get('format') == 'json' or request.POST.get('ajax') == '1':
            return True
        accept = (request.headers.get('Accept') or '').lower()
        if 'application/json' in accept:
            return True
        return (request.headers.get('X-Requested-With') or '') == 'XMLHttpRequest'

    if request.method == 'GET' and _quiere_json():
        return JsonResponse({
            'success': True,
            'cliente': {
                'id': cliente.id,
                'numero_cliente': cliente.numero_cliente or '',
                'sector': cliente.sector or '',
                'tipo_suministro': cliente.tipo_suministro or '',
                'comuna': cliente.comuna or '',
                'customer_name': cliente.customer_name or '',
                'installation_address': cliente.installation_address or '',
                'proyecto': cliente.proyecto or '',
                'meter_manufacturer_id': cliente.meter_manufacturer_id or '',
                'meter_serial_n_1': cliente.meter_serial_n_1 or '',
                'estado_restriccion': cliente.estado_restriccion or '',
                'justificacion_restriccion': cliente.justificacion_restriccion or '',
            },
        })

    if request.method == 'POST':
        numero_cliente = request.POST.get('numero_cliente', '').strip()
        sector = request.POST.get('sector', '').strip()
        tipo_suministro = request.POST.get('tipo_suministro', '').strip()
        comuna = request.POST.get('comuna', '').strip()
        customer_name = request.POST.get('customer_name', '').strip()
        installation_address = request.POST.get('installation_address', '').strip()
        proyecto = request.POST.get('proyecto', '').strip()
        meter_manufacturer_id = request.POST.get('meter_manufacturer_id', '').strip()
        meter_serial_n_1 = request.POST.get('meter_serial_n_1', '').strip()
        estado_restriccion = (request.POST.get('estado_restriccion') or '').strip().upper()
        justificacion_restriccion = (request.POST.get('justificacion_restriccion') or '').strip()
        next_url = (request.POST.get('next') or '').strip()

        codigos_ok = {c for c, _ in Cliente.ESTADO_RESTRICCION_CHOICES}
        if estado_restriccion and estado_restriccion not in codigos_ok:
            estado_restriccion = ''

        before_values = {
            'numero_cliente': cliente.numero_cliente,
            'sector': cliente.sector,
            'tipo_suministro': cliente.tipo_suministro,
            'comuna': cliente.comuna,
            'customer_name': cliente.customer_name,
            'installation_address': cliente.installation_address,
            'meter_manufacturer_id': cliente.meter_manufacturer_id,
            'proyecto': cliente.proyecto,
            'meter_serial_n_1': cliente.meter_serial_n_1,
            'estado_restriccion': cliente.estado_restriccion or '',
            'justificacion_restriccion': cliente.justificacion_restriccion or '',
        }

        # Si no envían número de cliente en edición, se conserva el actual.
        numero_cliente_final = numero_cliente or cliente.numero_cliente

        def _responder_error(mensaje):
            if _quiere_json():
                return JsonResponse({'success': False, 'message': mensaje}, status=400)
            messages.error(request, mensaje)
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('clientes_list')

        restriccion_issues = validate_restriccion_con_justificacion(
            estado_restriccion,
            justificacion_restriccion,
        )
        if restriccion_issues:
            return _responder_error(restriccion_issues[0].message)

        if Cliente.objects.filter(
            numero_cliente=numero_cliente_final,
            meter_serial_n_1__iexact=meter_serial_n_1,
            activo=True,
        ).exclude(pk=pk).exists():
            return _responder_error(
                f'Ya existe un cliente activo con numero {numero_cliente_final} y la misma serie {meter_serial_n_1}.'
            )

        if meter_serial_n_1 and Cliente.objects.filter(
            meter_serial_n_1__iexact=meter_serial_n_1,
            activo=True,
        ).exclude(pk=pk).exists():
            return _responder_error(
                f'El número de serie {meter_serial_n_1} ya está asignado a otro cliente activo.'
            )

        cliente.numero_cliente = numero_cliente_final
        cliente.sector = sector or None
        cliente.tipo_suministro = tipo_suministro or None
        cliente.comuna = comuna or None
        cliente.customer_name = customer_name or None
        cliente.installation_address = installation_address or None
        cliente.meter_manufacturer_id = meter_manufacturer_id or None
        # proyecto se actualiza vía historial (no sobrescribir aquí)
        cliente.meter_serial_n_1 = meter_serial_n_1 or None
        cliente.estado_restriccion = estado_restriccion
        cliente.justificacion_restriccion = justificacion_restriccion if estado_restriccion else ''
        cliente.save()

        from clientes.proyecto_historial import registrar_cambio_proyecto
        registrar_cambio_proyecto(
            cliente,
            proyecto,
            usuario=request.user,
            motivo='Edición desde gestión de clientes',
            actualizar_campo=True,
        )

        after_values = {
            'numero_cliente': cliente.numero_cliente,
            'sector': cliente.sector,
            'tipo_suministro': cliente.tipo_suministro,
            'comuna': cliente.comuna,
            'customer_name': cliente.customer_name,
            'installation_address': cliente.installation_address,
            'meter_manufacturer_id': cliente.meter_manufacturer_id,
            'proyecto': cliente.proyecto,
            'meter_serial_n_1': cliente.meter_serial_n_1,
            'estado_restriccion': cliente.estado_restriccion or '',
            'justificacion_restriccion': cliente.justificacion_restriccion or '',
        }
        for field_name, old_value in before_values.items():
            new_value = after_values.get(field_name)
            if old_value != new_value:
                register_audit_event(
                    AuditEvent(
                        actor_id=getattr(request.user, 'id', None),
                        action='CLIENT_UPDATE',
                        entity='Cliente',
                        entity_id=str(cliente.id),
                        field_name=field_name,
                        old_value=old_value,
                        new_value=new_value,
                        reason='Edición desde gestión de clientes',
                    )
                )

        mensaje_ok = f'Cliente {numero_cliente_final} actualizado correctamente.'
        if _quiere_json():
            return JsonResponse({
                'success': True,
                'message': mensaje_ok,
                'cliente': after_values,
                'cliente_id': cliente.id,
            })

        messages.success(request, mensaje_ok)
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('clientes_list')

    # GET HTML clásico: redirige al listado (edición es modal)
    return redirect('clientes_list')


@login_required
def cliente_historial_view(request, pk):
    """Ficha completa del cliente: datos ocultos del listado, OT y alertas operativas."""
    from ordenes_trabajo.models import OrdenTrabajo, IntegracionMoreApp
    from ordenes_trabajo.services import (
        count_visits_last_6_months,
        has_open_ot_for_cliente,
        should_flag_reincidence,
    )
    from web.models import AuditLog
    from web.services.filtros_export import es_sin_proyecto
    from clientes.models import ClienteProyectoHistorial
    from clientes.proyecto_historial import (
        asegurar_historial_inicial,
        estado_proyecto_ui,
    )

    cliente = get_object_or_404(Cliente, pk=pk, activo=True)
    asegurar_historial_inicial(cliente)
    proyectos_historial = list(
        ClienteProyectoHistorial.objects.filter(cliente=cliente)
        .select_related('cambiado_por')
        .order_by('-vigente', '-fecha_inicio', '-id')
    )
    for item in proyectos_historial:
        codigo, etiqueta = estado_proyecto_ui(item)
        item.estado_codigo = codigo
        item.estado_etiqueta = etiqueta
    numero = (cliente.numero_cliente or '').strip()

    ordenes = (
        OrdenTrabajo.objects.filter(cliente=cliente, eliminado=False)
        .select_related('tecnico_responsable')
        .order_by('-fecha_creacion')[:50]
    )
    ordenes_abiertas = OrdenTrabajo.objects.filter(
        cliente=cliente,
        eliminado=False,
        estado__in=OrdenTrabajo.ESTADOS_ABIERTOS,
    ).count()
    ordenes_con_alerta = OrdenTrabajo.objects.filter(
        cliente=cliente,
        eliminado=False,
        alerta_duplicado=True,
    ).count()
    visitas_6m = count_visits_last_6_months(cliente.pk)

    fichas_mismo_numero = list(
        Cliente.objects.filter(activo=True, numero_cliente=numero)
        .exclude(pk=cliente.pk)
        .order_by('meter_serial_n_1', 'id')[:20]
    )

    alertas = []
    if fichas_mismo_numero:
        alertas.append({
            'nivel': 'danger',
            'titulo': 'Número de cliente duplicado',
            'detalle': (
                f'Hay {len(fichas_mismo_numero)} ficha(s) activa(s) más con el mismo '
                f'Nº {numero}.'
            ),
        })

    if cliente.ip:
        otros_ip = Cliente.objects.filter(
            activo=True,
            ip__iexact=str(cliente.ip).strip(),
        ).exclude(pk=cliente.pk).exclude(ip__isnull=True).exclude(ip='')
        if otros_ip.exists():
            alertas.append({
                'nivel': 'danger',
                'titulo': 'IP duplicada',
                'detalle': (
                    f'La IP {cliente.ip} también está en: '
                    + ', '.join(otros_ip.values_list('numero_cliente', flat=True)[:5])
                ),
            })
        if not (cliente.puerto or '').strip():
            alertas.append({
                'nivel': 'warning',
                'titulo': 'IP sin puerto',
                'detalle': 'Hay IP registrada pero no hay puerto asociado.',
            })

    if cliente.meter_serial_n_1:
        otros_medidor = Cliente.objects.filter(
            activo=True,
            meter_serial_n_1__iexact=str(cliente.meter_serial_n_1).strip(),
        ).exclude(pk=cliente.pk)
        if otros_medidor.exists():
            alertas.append({
                'nivel': 'danger',
                'titulo': 'Serie de medidor duplicada',
                'detalle': (
                    f'La serie {cliente.meter_serial_n_1} también está en: '
                    + ', '.join(otros_medidor.values_list('numero_cliente', flat=True)[:5])
                ),
            })

    if has_open_ot_for_cliente(cliente.pk):
        alertas.append({
            'nivel': 'warning',
            'titulo': 'OT abierta',
            'detalle': f'El cliente tiene {ordenes_abiertas} orden(es) de trabajo abierta(s).',
        })

    if ordenes_con_alerta:
        alertas.append({
            'nivel': 'warning',
            'titulo': 'OT con alerta de duplicado',
            'detalle': f'{ordenes_con_alerta} OT marcada(s) como posible trabajo duplicado.',
        })

    if should_flag_reincidence(visitas_6m):
        alertas.append({
            'nivel': 'warning',
            'titulo': 'Reincidencia de visitas',
            'detalle': (
                f'Más de 2 visitas en los últimos 6 meses ({visitas_6m} registros OT).'
            ),
        })

    if cliente.estado_stb == 'PENDIENTE':
        alertas.append({
            'nivel': 'warning',
            'titulo': 'Pendiente STB',
            'detalle': 'Cliente pendiente de actualización en StarBeat (STB).',
        })
    if cliente.estado_sci4 == 'PENDIENTE':
        alertas.append({
            'nivel': 'warning',
            'titulo': 'Pendiente SCi4',
            'detalle': 'Cliente pendiente de actualización en SCi4.',
        })
    if cliente.estado_telemetria in ('SIN_COMUNICACION', 'NO_COMUNICA', 'SIN_MEDIDOR'):
        alertas.append({
            'nivel': 'warning',
            'titulo': 'Estado de telemetría',
            'detalle': f'Telemetría: {cliente.get_estado_telemetria_display()}.',
        })
    if cliente.sim_estado in ('SIN_DATOS', 'DANADA', 'SIN_COBERTURA', 'SIN_IP'):
        alertas.append({
            'nivel': 'warning',
            'titulo': 'Estado de SIM',
            'detalle': f'SIM: {cliente.get_sim_estado_display()}.',
        })

    if (cliente.estado_restriccion or '').strip():
        from web.services.validators import (
            ESTADOS_IP_RESTRINGIDA,
            ESTADOS_VISITA_RESTRINGIDA,
        )
        estado_r = cliente.estado_restriccion
        es_ip = estado_r in ESTADOS_IP_RESTRINGIDA
        titulo = 'IP restringida' if es_ip else 'Antecedente de visita'
        detalle = cliente.get_estado_restriccion_display()
        motivo = (cliente.justificacion_restriccion or '').strip()
        if motivo:
            detalle = f'{detalle}. Justificación: {motivo}'
        else:
            detalle = f'{detalle}. Sin justificación registrada.'
        alertas.append({
            'nivel': 'danger' if es_ip else 'warning',
            'titulo': titulo,
            'detalle': detalle,
        })
    else:
        from web.services.validators import detect_antecedentes_visita_texto
        legacy = detect_antecedentes_visita_texto(cliente.trabajo, cliente.note)
        if legacy:
            alertas.append({
                'nivel': 'warning',
                'titulo': 'Antecedente de visita (notas)',
                'detalle': 'Detectado en trabajo/nota: ' + ', '.join(legacy),
            })

    if not alertas:
        alertas.append({
            'nivel': 'success',
            'titulo': 'Sin alertas detectadas',
            'detalle': 'No se encontraron inconsistencias operativas automáticas en esta ficha.',
        })

    moreapp_regs = []
    if numero:
        moreapp_qs = (
            IntegracionMoreApp.objects.filter(eliminado=False)
            .filter(
                models.Q(datos_procesados__cliente_codigo=numero)
                | models.Q(datos_procesados__cliente_codigo=str(numero))
            )
            .order_by('-fecha_recepcion')[:20]
        )
        moreapp_regs = list(moreapp_qs)
        if len(moreapp_regs) < 20:
            # Fallback por payload crudo / campos legacy (solo activos)
            vistos = {r.pk for r in moreapp_regs}
            for reg in IntegracionMoreApp.objects.filter(eliminado=False).order_by('-fecha_recepcion')[:200]:
                if reg.pk in vistos:
                    continue
                data = reg.datos_procesados or {}
                raw = (reg.datos_recibidos or {}).get('data') or {}
                candidatos = [
                    data.get('cliente'),
                    data.get('numero_cliente'),
                    data.get('codigo_cliente'),
                    data.get('cliente_codigo'),
                    raw.get('cliente'),
                ]
                buscar = raw.get('buscarCliente') or {}
                if isinstance(buscar, dict):
                    candidatos.append(buscar.get('CLIENTE1'))
                mant = raw.get('clienteParaMantenimiento') or {}
                if isinstance(mant, dict):
                    candidatos.append(mant.get('NROCLIENTE'))
                if any(str(c).strip() == numero for c in candidatos if c is not None):
                    moreapp_regs.append(reg)
                    vistos.add(reg.pk)
                if len(moreapp_regs) >= 20:
                    break

    auditoria = AuditLog.objects.filter(
        entity='Cliente',
        entity_id=str(cliente.pk),
    ).order_by('-created_at')[:40]

    context = {
        'cliente': cliente,
        'ordenes': ordenes,
        'ordenes_abiertas': ordenes_abiertas,
        'ordenes_con_alerta': ordenes_con_alerta,
        'visitas_6m': visitas_6m,
        'alertas': alertas,
        'tiene_alertas_criticas': any(a['nivel'] == 'danger' for a in alertas),
        'fichas_mismo_numero': fichas_mismo_numero,
        'moreapp_regs': moreapp_regs,
        'auditoria': auditoria,
        'proyectos_historial': proyectos_historial,
        'puede_editar': request.user.rol in ['ADMIN', 'ADMINISTRATIVO'],
        'estado_restriccion_choices': Cliente.ESTADO_RESTRICCION_CHOICES,
        'proyectos_disponibles': sorted({
            (p or '').strip()
            for p in Cliente.objects.filter(activo=True)
            .exclude(proyecto__isnull=True)
            .exclude(proyecto='')
            .values_list('proyecto', flat=True)
            if (p or '').strip() and not es_sin_proyecto(p)
        }, key=lambda x: x.casefold()),
    }
    return render(request, 'clientes/historial.html', context)


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO'])
def cliente_eliminar_view(request, pk):
    """Soft-delete de cliente + snapshot en movimientos."""
    from web.services.eliminaciones import ENTIDAD_CLIENTE, registrar_eliminacion

    if request.method != 'POST':
        return redirect('clientes_list')

    cliente = get_object_or_404(Cliente, pk=pk, activo=True)
    cliente_numero = cliente.numero_cliente
    motivo = request.POST.get('motivo', '').strip()
    _, creado = registrar_eliminacion(
        ENTIDAD_CLIENTE,
        cliente,
        request.user,
        motivo=motivo or 'Eliminación lógica individual desde gestión',
    )
    if creado:
        messages.success(
            request,
            f'Cliente {cliente_numero} eliminado. Quedó registrado en Movimientos.',
        )
    else:
        messages.warning(request, f'El cliente {cliente_numero} ya estaba eliminado.')
    return redirect('clientes_list')


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO'])
@require_POST
def clientes_eliminar_masivo_view(request):
    """Soft-delete masivo de clientes + snapshot en movimientos."""
    from web.services.eliminaciones import ENTIDAD_CLIENTE, registrar_eliminacion

    ids = request.POST.getlist('cliente_ids')
    if not ids:
        messages.warning(request, 'No se seleccionaron clientes para eliminar.')
        return redirect('clientes_list')

    clientes = list(Cliente.objects.filter(pk__in=ids, activo=True))
    total = 0
    numeros = []
    for cliente in clientes:
        _, creado = registrar_eliminacion(
            ENTIDAD_CLIENTE,
            cliente,
            request.user,
            motivo='Eliminación lógica masiva desde gestión',
        )
        if creado:
            total += 1
            if len(numeros) < 10:
                numeros.append(cliente.numero_cliente)

    if total == 0:
        messages.warning(request, 'No se encontraron clientes activos para eliminar.')
    else:
        extra = ''
        if total > 10:
            extra = f' y {total - 10} más'
        numeros_txt = ', '.join(numeros)
        messages.success(
            request,
            f'Se eliminaron {total} clientes. Quedaron en Movimientos. {numeros_txt}{extra}'.strip()
        )
    return redirect('clientes_list')


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO'])
@require_http_methods(["POST"])
def clientes_modificar_masivo_view(request):
    """Edición masiva de campos de ficha (solo campos no vacíos)."""
    ids_raw = request.POST.get('ids', '') or request.POST.get('cliente_ids', '')
    if isinstance(ids_raw, list):
        ids = [int(x) for x in ids_raw if str(x).strip().isdigit()]
    else:
        ids = [int(x) for x in str(ids_raw).replace(' ', '').split(',') if x.isdigit()]

    if not ids:
        return JsonResponse({'success': False, 'message': 'No hay clientes seleccionados.', 'actualizados': 0, 'omitidos': 0})

    sector = (request.POST.get('sector') or '').strip()
    comuna = (request.POST.get('comuna') or '').strip()
    tipo_suministro = (request.POST.get('tipo_suministro') or '').strip()
    proyecto = (request.POST.get('proyecto') or '').strip()

    if not any([sector, comuna, tipo_suministro, proyecto]):
        return JsonResponse({
            'success': False,
            'message': 'Completa al menos un campo para aplicar cambios.',
            'actualizados': 0,
            'omitidos': len(ids),
        })

    actualizados = 0
    omitidos = 0
    from clientes.proyecto_historial import registrar_cambio_proyecto

    for cliente in Cliente.objects.filter(pk__in=ids, activo=True):
        changed = False
        if sector and (cliente.sector or '') != sector:
            cliente.sector = sector
            changed = True
        if comuna and (cliente.comuna or '') != comuna:
            cliente.comuna = comuna
            changed = True
        if tipo_suministro and (cliente.tipo_suministro or '') != tipo_suministro:
            cliente.tipo_suministro = tipo_suministro
            changed = True

        proyecto_cambio = False
        if proyecto and (cliente.proyecto or '') != proyecto:
            before_proy = cliente.proyecto
            proyecto_cambio = registrar_cambio_proyecto(
                cliente,
                proyecto,
                usuario=request.user,
                motivo='Cambio de proyecto (edición masiva)',
                actualizar_campo=True,
            )
            if proyecto_cambio:
                changed = True
                register_audit_event(
                    AuditEvent(
                        actor_id=getattr(request.user, 'id', None),
                        action='CLIENT_UPDATE',
                        entity='Cliente',
                        entity_id=str(cliente.id),
                        field_name='proyecto',
                        old_value=before_proy,
                        new_value=cliente.proyecto,
                        reason='Cambio de proyecto (edición masiva)',
                    )
                )

        if changed:
            # Si solo cambió proyecto, registrar_cambio_proyecto ya guardó.
            # Si también hay sector/comuna/tipo, persistir esos campos.
            if sector or comuna or tipo_suministro:
                update_fields = ['fecha_actualizacion']
                if sector:
                    update_fields.append('sector')
                if comuna:
                    update_fields.append('comuna')
                if tipo_suministro:
                    update_fields.append('tipo_suministro')
                cliente.save(update_fields=update_fields)
            actualizados += 1
        else:
            omitidos += 1

    omitidos += max(0, len(ids) - actualizados - omitidos)
    return JsonResponse({
        'success': True,
        'message': f'Se actualizaron {actualizados} cliente(s). {omitidos} sin cambios.',
        'actualizados': actualizados,
        'omitidos': omitidos,
    })


@login_required
@require_http_methods(["POST"])
def update_profile_view(request):
    """Actualizar perfil del usuario"""
    try:
        data = json.loads(request.body)
        nombre_interno = data.get('nombre_interno', '').strip()
        current_password = data.get('current_password', '').strip()
        new_password = data.get('new_password', '').strip()
        
        if not nombre_interno:
            return JsonResponse({'success': False, 'message': 'El nombre de usuario no puede estar vacío'})
        
        # Si se intenta cambiar contraseña
        if new_password:
            # Verificar contraseña actual
            if not request.user.check_password(current_password):
                return JsonResponse({'success': False, 'message': 'Contraseña actual incorrecta'})
            # Cambiar contraseña
            request.user.set_password(new_password)
        
        request.user.nombre_interno = nombre_interno
        request.user.save()
        
        return JsonResponse({'success': True, 'message': 'Perfil actualizado correctamente'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Error en el formato de datos'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# =============================================================================
# VISTAS DE MOVIMIENTOS DE INVENTARIO
# =============================================================================

@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def movimientos_list_view(request):
    """
    Listar todos los movimientos de inventario con filtros
    
    Según TDR: Visualizar entregas, recepciones, instalaciones, retiros, cambios
    """
    from inventario.models import MovimientoInventario
    from django.db.models import Q, Count
    from django.core.paginator import Paginator
    
    # Obtener parámetros de filtrado
    tipo_filtro = request.GET.get('tipo', '')
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    responsable_id = request.GET.get('responsable', '')
    origen_id = request.GET.get('origen', '')
    destino_id = request.GET.get('destino', '')
    origen_sistema = request.GET.get('origen_sistema', '')
    entidad_eliminada = request.GET.get('entidad_eliminada', '')
    busqueda = request.GET.get('q', '')
    
    # Query base
    from django.db.models import Prefetch
    from inventario.models import MovimientoItem
    from web.services.movimientos_display import enriquecer_movimiento_ubicaciones

    movimientos = MovimientoInventario.objects.all().select_related(
        'origen', 'destino', 'responsable'
    ).prefetch_related(
        Prefetch(
            'items',
            queryset=MovimientoItem.objects.select_related(
                'medidor__cliente',
                'simcard__cliente',
                'modem__cliente',
            ),
        )
    ).order_by('-fecha_hora')
    
    # Aplicar filtros
    if tipo_filtro:
        movimientos = movimientos.filter(tipo=tipo_filtro)

    if entidad_eliminada:
        movimientos = movimientos.filter(
            tipo='ELIMINACION',
            entidad_eliminada=entidad_eliminada,
        )
    
    if fecha_desde:
        try:
            from django.utils import timezone as _tz
            fecha_desde_dt = _tz.make_aware(
                datetime.strptime(fecha_desde, '%Y-%m-%d'),
                _tz.get_current_timezone(),
            )
            movimientos = movimientos.filter(fecha_hora__gte=fecha_desde_dt)
        except ValueError:
            pass

    if fecha_hasta:
        try:
            from django.utils import timezone as _tz
            from datetime import time as _time
            fecha_hasta_dt = _tz.make_aware(
                datetime.combine(
                    datetime.strptime(fecha_hasta, '%Y-%m-%d').date(),
                    _time.max,
                ),
                _tz.get_current_timezone(),
            )
            movimientos = movimientos.filter(fecha_hora__lte=fecha_hasta_dt)
        except ValueError:
            pass
    
    if responsable_id:
        movimientos = movimientos.filter(responsable_id=responsable_id)
    
    if origen_id:
        movimientos = movimientos.filter(origen_id=origen_id)
    
    if destino_id:
        movimientos = movimientos.filter(destino_id=destino_id)

    if origen_sistema:
        movimientos = movimientos.filter(origen_sistema=origen_sistema)
    
    if busqueda:
        movimientos = movimientos.filter(
            Q(observacion__icontains=busqueda) |
            Q(referencia_ot__icontains=busqueda) |
            Q(responsable__nombre_interno__icontains=busqueda) |
            Q(identificador_entidad__icontains=busqueda) |
            Q(entidad_id__icontains=busqueda)
        )
    
    # Anotar cantidad de items por movimiento
    movimientos = movimientos.annotate(total_items=Count('items'))
    
    # Estadísticas rápidas
    total_movimientos = movimientos.count()
    por_tipo = MovimientoInventario.objects.values('tipo').annotate(
        cantidad=Count('id')
    ).order_by('tipo')
    
    # Obtener listas para filtros
    responsables = request.user.__class__.objects.filter(
        is_active=True, rol__in=['TECNICO', 'ADMINISTRATIVO', 'ADMIN']
    ).order_by('nombre_interno')
    ubicaciones = Ubicacion.objects.all().order_by('nombre')
    
    # Paginacion del listado para navegar todo el historico manteniendo filtros.
    page_number = request.GET.get('page')
    paginator = Paginator(movimientos, 50)
    page_obj = paginator.get_page(page_number)

    movimientos_render = list(page_obj.object_list)
    submission_ids = set()
    for mov in movimientos_render:
        detalles = []
        for item in mov.items.all():
            if item.medidor:
                detalles.append(f'Medidor {item.medidor.serie}')
            elif item.simcard:
                identificador_sim = item.simcard.imei or item.simcard.abonado or item.simcard.id
                detalles.append(f'SIM {identificador_sim}')
            elif item.modem:
                detalles.append(f'Módem {item.modem.serie}')
            else:
                detalles.append(item.get_tipo_equipo_display())

        if detalles:
            mov.item_origen_display = ', '.join(detalles[:3])
            if len(detalles) > 3:
                mov.item_origen_display += f' (+{len(detalles) - 3} más)'
        elif mov.tipo == 'ELIMINACION' and mov.identificador_entidad:
            entidad_lbl = mov.get_entidad_eliminada_display() or mov.entidad_eliminada or 'Registro'
            mov.item_origen_display = f'{entidad_lbl}: {mov.identificador_entidad}'
        else:
            mov.item_origen_display = '-'

        enriquecer_movimiento_ubicaciones(mov)

        mov.moreapp_submission_id = ''
        mov.moreapp_registro_id = None
        if mov.origen_sistema == 'MOREAPP':
            sid = _extraer_submission_moreapp(mov.observacion or '')
            mov.moreapp_submission_id = sid
            if sid:
                submission_ids.add(sid)

    reporte_por_submission = {}
    if submission_ids:
        from ordenes_trabajo.models import IntegracionMoreApp
        for reporte in IntegracionMoreApp.objects.filter(
            eliminado=False,
            moreapp_submission_id__in=submission_ids,
        ).only('id', 'moreapp_submission_id'):
            reporte_por_submission[reporte.moreapp_submission_id] = reporte.id
        for mov in movimientos_render:
            if mov.moreapp_submission_id:
                mov.moreapp_registro_id = reporte_por_submission.get(mov.moreapp_submission_id)
    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()

    context = {
        'movimientos': movimientos_render,
        'page_obj': page_obj,
        'query_string': query_string,
        'total_movimientos': total_movimientos,
        'por_tipo': por_tipo,
        'responsables': responsables,
        'ubicaciones': ubicaciones,
        'tipo_filtro': tipo_filtro,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'responsable_id': responsable_id,
        'origen_id': origen_id,
        'destino_id': destino_id,
        'origen_sistema': origen_sistema,
        'entidad_eliminada': entidad_eliminada,
        'busqueda': busqueda,
        'tipos_movimiento': MovimientoInventario.TIPO_CHOICES,
        'origen_sistema_choices': MovimientoInventario.ORIGEN_SISTEMA_CHOICES,
        'entidades_eliminacion': MovimientoInventario.ENTIDAD_ELIMINADA_CHOICES,
        'ordenes_habilitadas': _ordenes_trabajo_habilitadas(),
        # Datos para gráfico (sobre TODOS los registros, no filtrados)
        'tipo_breakdown': list(
            MovimientoInventario.objects.values('tipo')
            .annotate(c=Count('id'))
            .order_by('-c')
        ),
        'origen_sistema_breakdown': list(
            MovimientoInventario.objects.values('origen_sistema')
            .annotate(c=Count('id'))
            .order_by('-c')
        ),
        'total_global': MovimientoInventario.objects.count(),
        'puede_ver_eliminaciones': request.user.rol in ['ADMIN', 'ADMINISTRATIVO', 'AUDITOR'],
    }
    
    return render(request, 'movimientos/list.html', context)


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def movimientos_detalle_view(request, movimiento_id):
    """
    Ver detalles completos de un movimiento específico
    
    Muestra todos los items involucrados y evidencias
    """
    from inventario.models import MovimientoInventario, MovimientoItem
    from web.services.movimientos_display import enriquecer_movimiento_ubicaciones
    
    movimiento = get_object_or_404(
        MovimientoInventario.objects.select_related(
            'origen', 'destino', 'responsable'
        ),
        id=movimiento_id
    )
    
    items = movimiento.items.all().select_related(
        'medidor__cliente', 'medidor__estado_inventario',
        'simcard__cliente', 'simcard__estado_inventario',
        'modem__cliente', 'modem__estado_inventario',
    )
    enriquecer_movimiento_ubicaciones(movimiento)

    items_detalle = []
    resumen_por_tipo = {
        'MEDIDOR': 0,
        'SIM': 0,
        'MODEM': 0,
    }

    for item in items:
        if item.medidor:
            resumen_por_tipo['MEDIDOR'] += 1
            items_detalle.append({
                'tipo': 'Medidor',
                'identificador': item.medidor.serie,
                'descripcion': ' | '.join(filter(None, [item.medidor.marca, item.medidor.caja, item.medidor.get_tipo_medidor_display()])),
                'cliente': getattr(getattr(item.medidor, 'cliente', None), 'customer_name', '') or getattr(getattr(item.medidor, 'cliente', None), 'numero_cliente', '') or '—',
                'estado': getattr(getattr(item.medidor, 'estado_inventario', None), 'nombre', '') or '—',
                'historial_tipo': 'MEDIDOR',
                'historial_id': item.medidor.id,
            })
        elif item.simcard:
            resumen_por_tipo['SIM'] += 1
            items_detalle.append({
                'tipo': 'SIM',
                'identificador': item.simcard.imei or item.simcard.abonado or str(item.simcard.id),
                'descripcion': ' | '.join(filter(None, [item.simcard.operador, item.simcard.abonado, item.simcard.direccion_ip])),
                'cliente': getattr(getattr(item.simcard, 'cliente', None), 'customer_name', '') or getattr(getattr(item.simcard, 'cliente', None), 'numero_cliente', '') or '—',
                'estado': getattr(getattr(item.simcard, 'estado_inventario', None), 'nombre', '') or '—',
                'historial_tipo': 'SIM',
                'historial_id': item.simcard.id,
            })
        elif item.modem:
            resumen_por_tipo['MODEM'] += 1
            items_detalle.append({
                'tipo': 'Módem',
                'identificador': item.modem.serie or item.modem.imei or str(item.modem.id),
                'descripcion': ' | '.join(filter(None, [item.modem.marca, item.modem.modelo, item.modem.imei])),
                'cliente': getattr(getattr(item.modem, 'cliente', None), 'customer_name', '') or getattr(getattr(item.modem, 'cliente', None), 'numero_cliente', '') or '—',
                'estado': getattr(getattr(item.modem, 'estado_inventario', None), 'nombre', '') or '—',
                'historial_tipo': 'MODEM',
                'historial_id': item.modem.id,
            })
        else:
            items_detalle.append({
                'tipo': item.get_tipo_equipo_display(),
                'identificador': '—',
                'descripcion': 'Ítem sin vínculo de equipo',
                'cliente': '—',
                'estado': '—',
                'historial_tipo': '',
                'historial_id': '',
            })
    
    snapshot_items = []
    if movimiento.tipo == 'ELIMINACION' and movimiento.datos_eliminacion:
        for clave, valor in movimiento.datos_eliminacion.items():
            if clave.startswith('_'):
                continue
            if isinstance(valor, (dict, list)):
                try:
                    valor_txt = json.dumps(valor, ensure_ascii=False, indent=2, default=str)
                except Exception:
                    valor_txt = str(valor)
            else:
                valor_txt = '' if valor is None else str(valor)
            if valor_txt == '':
                continue
            snapshot_items.append({'campo': clave, 'valor': valor_txt})

    moreapp_submission_id = ''
    moreapp_registro = None
    if movimiento.origen_sistema == 'MOREAPP':
        moreapp_submission_id = _extraer_submission_moreapp(movimiento.observacion or '')
        if moreapp_submission_id:
            from ordenes_trabajo.models import IntegracionMoreApp
            moreapp_registro = IntegracionMoreApp.objects.filter(
                eliminado=False,
                moreapp_submission_id=moreapp_submission_id,
            ).only('id', 'moreapp_submission_id', 'numero_correlativo', 'nombre_formulario').first()

    context = {
        'movimiento': movimiento,
        'items_detalle': items_detalle,
        'items_medidores_count': resumen_por_tipo['MEDIDOR'],
        'items_sims_count': resumen_por_tipo['SIM'],
        'items_modems_count': resumen_por_tipo['MODEM'],
        'total_items': items.count(),
        'ordenes_habilitadas': _ordenes_trabajo_habilitadas(),
        'snapshot_items': snapshot_items,
        'es_eliminacion': movimiento.tipo == 'ELIMINACION',
        'moreapp_submission_id': moreapp_submission_id,
        'moreapp_registro': moreapp_registro,
    }
    
    return render(request, 'movimientos/detalle.html', context)


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR'])
def movimientos_historial_equipo_view(request):
    """
    Ver historial completo de movimientos de un equipo específico
    
    Según TDR: "Trazabilidad histórica de cada equipo"
    """
    from inventario.models import MovimientoItem
    
    # Parámetros
    tipo_equipo = request.GET.get('tipo', '')  # MEDIDOR, SIM, MODEM
    equipo_id = request.GET.get('id', '')
    
    if not tipo_equipo or not equipo_id:
        messages.error(request, 'Debe especificar tipo de equipo e ID')
        return redirect('movimientos_list')
    
    # Obtener equipo
    equipo = None
    equipo_nombre = ''
    
    if tipo_equipo == 'MEDIDOR':
        equipo = get_object_or_404(Medidor, id=equipo_id)
        equipo_nombre = f"Medidor {equipo.serie}"
    elif tipo_equipo == 'SIM':
        equipo = get_object_or_404(SimCard, id=equipo_id)
        equipo_nombre = f"SIM {equipo.imei}"
    elif tipo_equipo == 'MODEM':
        equipo = get_object_or_404(Modem, id=equipo_id)
        equipo_nombre = f"Módem {equipo.imei}"
    else:
        messages.error(request, 'Tipo de equipo inválido')
        return redirect('movimientos_list')
    
    # Obtener movimientos del equipo
    if tipo_equipo == 'MEDIDOR':
        items = MovimientoItem.objects.filter(medidor=equipo)
    elif tipo_equipo == 'SIM':
        items = MovimientoItem.objects.filter(simcard=equipo)
    else:  # MODEM
        items = MovimientoItem.objects.filter(modem=equipo)
    
    items = items.select_related(
        'movimiento__origen',
        'movimiento__destino',
        'movimiento__responsable',
        'medidor__cliente',
        'simcard__cliente',
        'modem__cliente',
    ).order_by('-movimiento__fecha_hora')

    from web.services.movimientos_display import enriquecer_movimiento_ubicaciones
    items_list = list(items)
    for item in items_list:
        enriquecer_movimiento_ubicaciones(item.movimiento)
    items = items_list

    # Evaluar queryset y adjuntar reporte MoreApp a cada item para que el
    # template pueda acceder con item.reporte_moreapp sin templatetags extra.
    from ordenes_trabajo.models import IntegracionMoreApp
    import re as _re

    items_list = list(items)
    total_movimientos = len(items_list)

    # Recolectar todos los submission_id únicos de movimientos MOREAPP
    sid_map = {}  # submission_id → item.movimiento.id
    for item in items_list:
        mov = item.movimiento
        item.reporte_moreapp = None
        if mov.origen_sistema == 'MOREAPP' and mov.observacion:
            m = _re.search(r'submission:\s*([a-f0-9]+)', mov.observacion, _re.IGNORECASE)
            if m:
                sid_map.setdefault(m.group(1).strip(), []).append(item)

    # Consulta única para todos los submission_ids encontrados
    if sid_map:
        reportes = IntegracionMoreApp.objects.filter(
            eliminado=False,
            moreapp_submission_id__in=sid_map.keys(),
        ).only('id', 'moreapp_submission_id', 'estado_revision', 'estado_sincronizacion')
        for reporte in reportes:
            for item in sid_map.get(reporte.moreapp_submission_id, []):
                item.reporte_moreapp = reporte

    context = {
        'equipo': equipo,
        'equipo_nombre': equipo_nombre,
        'tipo_equipo': tipo_equipo,
        'items': items_list,
        'total_movimientos': total_movimientos,
        'ordenes_habilitadas': _ordenes_trabajo_habilitadas(),
    }

    return render(request, 'movimientos/historial.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def movimientos_importar_moreapp_webhook(request):
    """
    Webhook para recibir datos de MoreApp en TIEMPO REAL
    
    Este endpoint es llamado automáticamente por MoreApp cuando un 
    técnico completa un formulario en terreno.
    
    Según TDR punto 6: "La información registrada en MoreApp debe ser 
    incorporada automáticamente en la base de datos central"
    
    NO requiere polling ni descargas manuales - es instantáneo.
    """
    from inventario.models import MovimientoInventario, MovimientoItem, VerificacionMedidor
    from django.conf import settings
    from django.db.models import Q
    
    try:
        # Seguridad webhook: validar secreto compartido
        expected_secret = str(getattr(settings, 'MOREAPP_WEBHOOK_SECRET', '') or '').strip()
        if expected_secret:
            provided_secret = (request.headers.get('X-MoreApp-Secret', '') or '').strip()
            auth_header = (request.headers.get('Authorization', '') or '').strip()
            if not provided_secret and auth_header.lower().startswith('bearer '):
                provided_secret = auth_header[7:].strip()
            if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
                return JsonResponse({'success': False, 'error': 'Webhook no autorizado'}, status=403)

        # MODO DEBUG: Loguear todo lo que llega
        logger.info("="*80)
        logger.info("WEBHOOK RECIBIDO DE MOREAPP")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Body raw: {request.body.decode('utf-8')[:1000]}")  # Primeros 1000 caracteres
        logger.info("="*80)
        
        # Parsear datos JSON de MoreApp
        data = json.loads(request.body)
        form_name = data.get('form_name', data.get('formName', ''))
        submission_id = data.get('registrationId', data.get('submission_id', ''))

        # Modo principal: procesamiento en tiempo real del payload oficial MoreApp.
        if getattr(settings, 'MOREAPP_WEBHOOK_REALTIME_ENABLED', True):
            required_keys = {'id', 'info', 'meta', 'data'}
            if isinstance(data, dict) and required_keys.issubset(set(data.keys())):
                from integraciones.reader import procesar_payload_moreapp

                res = procesar_payload_moreapp(data, ruta_context='webhook')
                ok = res.get('resultado') in ('nuevo', 'duplicado')
                status = 200 if ok else 400
                return JsonResponse(
                    {
                        'success': ok,
                        'resultado': res.get('resultado'),
                        'submission_id': res.get('submission_id'),
                        'alerta': bool(res.get('alerta')),
                        'message': res.get('mensaje', ''),
                    },
                    status=status,
                )
        
        logger.info(f"Formulario: {form_name}")
        logger.info(f"Submission ID: {submission_id}")
        
        # DETECTAR TIPO DE FORMULARIO
        # Si es "Verificacion de Medidores", guardar en tabla temporal
        if 'verificacion' in form_name.lower() or 'medidor' in form_name.lower():
            logger.info("Detectado formulario de VERIFICACIÓN DE MEDIDORES")
            
            # Extraer campos del formulario
            verificacion = VerificacionMedidor.objects.create(
                submission_id=submission_id or f"temp-{datetime.now().timestamp()}",
                num_cliente=data.get('numCliente', data.get('num_cliente', '')),
                num_orden=data.get('numOrden', data.get('num_orden', '')),
                direccion=data.get('direccion', ''),
                comuna=data.get('comuna', ''),
                resultado_visita=data.get('resultadoDeVisita', data.get('resultado_visita', '')),
                estado_medidor=data.get('estadoDeMedidor', data.get('estado_medidor', '')),
                foto_fachada_url=data.get('fotoFachada', data.get('foto_fachada', '')),
                datos_completos=data
            )
            
            logger.info(f"✅ Verificación #{verificacion.id} guardada exitosamente")
            
            return JsonResponse({
                'success': True,
                'verificacion_id': verificacion.id,
                'message': 'Verificación guardada correctamente',
                'tipo': 'verificacion_medidor'
            })
        
        # Si no es verificación, procesar como movimiento de inventario normal
        logger.info("Procesando como MOVIMIENTO DE INVENTARIO")
        
        # Extraer información del formulario
        tipo_trabajo = data.get('tipo', 'ENTREGA')
        fecha_str = data.get('fecha', datetime.now().isoformat())
        responsable_rut = data.get('tecnico_rut', '')
        tecnico_nombre = (
            data.get('tecnico_nombre')
            or data.get('tecnico')
            or data.get('tecnico_responsable')
            or data.get('tecnicoResponsable')
            or ''
        )
        observacion = data.get('observaciones', '')
        ot_numero = data.get('numero_ot', '')
        origen_nombre = data.get('origen', 'BODEGA')
        destino_nombre = data.get('destino', 'TERRENO')
        
        # Validar tipo de movimiento
        tipos_validos = dict(MovimientoInventario.TIPO_CHOICES).keys()
        if tipo_trabajo not in tipos_validos:
            return JsonResponse({
                'success': False,
                'error': f'Tipo de movimiento inválido: {tipo_trabajo}'
            }, status=400)
        
        # Buscar responsable
        from usuarios.models import Usuario
        responsable = None
        if responsable_rut:
            try:
                responsable = Usuario.objects.get(rut=responsable_rut)
            except Usuario.DoesNotExist:
                logger.warning(f"RUT no encontrado: {responsable_rut}")

        # Fallback por nombre técnico recibido en registro MoreApp
        if not responsable and tecnico_nombre:
            nombre_norm = str(tecnico_nombre).strip()
            responsable = Usuario.objects.filter(rol='TECNICO', is_active=True, nombre_interno__iexact=nombre_norm).first()
            if not responsable:
                responsable = Usuario.objects.filter(rol='TECNICO', is_active=True, nombre_interno__icontains=nombre_norm).first()
            if not responsable:
                tokens = [t for t in nombre_norm.split() if len(t) >= 3]
                for token in tokens:
                    responsable = Usuario.objects.filter(rol='TECNICO', is_active=True, nombre__icontains=token).first()
                    if responsable:
                        break
                    responsable = Usuario.objects.filter(rol='TECNICO', is_active=True, apellido__icontains=token).first()
                    if responsable:
                        break
        
        # Si no hay responsable, usar el primero disponible o crear uno genérico
        if not responsable:
            responsable = Usuario.objects.filter(rol='TECNICO').first()
            if not responsable:
                # Fallback: usar primer admin
                responsable = Usuario.objects.filter(rol='ADMIN').first()
            if not responsable:
                return JsonResponse({
                    'success': False,
                    'error': 'No se encontró ningún usuario válido en el sistema'
                }, status=500)
        
        referencia_ot = str(ot_numero or '').strip()
        
        # Crear/obtener ubicaciones
        origen, _ = Ubicacion.objects.get_or_create(
            nombre=origen_nombre,
            defaults={'tipo': 'BODEGA'}
        )
        destino, _ = Ubicacion.objects.get_or_create(
            nombre=destino_nombre,
            defaults={'tipo': 'INSTALACION'}
        )
        
        # Crear movimiento
        movimiento = MovimientoInventario.objects.create(
            tipo=tipo_trabajo,
            origen_sistema='MOREAPP',
            origen=origen,
            destino=destino,
            responsable=responsable,
            referencia_ot=referencia_ot,
            observacion=f"Registrado desde MoreApp (webhook)\n{observacion}"
        )

        # Procesar equipos
        items_creados = 0
        errores_equipos = []
        equipos_data = data.get('equipos', [])
        
        for equipo_data in equipos_data:
            tipo_eq = equipo_data.get('tipo', 'MEDIDOR')
            identificador = equipo_data.get('identificador', '')
            
            if not identificador:
                continue
            
            # Buscar equipo en base de datos
            equipo_obj = None
            
            if tipo_eq == 'MEDIDOR':
                try:
                    equipo_obj = Medidor.objects.filter(serie__iexact=identificador).first()
                    if not equipo_obj:
                        raise Medidor.DoesNotExist
                except (Medidor.DoesNotExist, Exception):
                    errores_equipos.append(f"Medidor {identificador} no encontrado")
                    continue
            elif tipo_eq == 'SIM':
                try:
                    equipo_obj = SimCard.objects.filter(
                        Q(imei__iexact=identificador)
                        | Q(abonado__iexact=identificador)
                        | Q(direccion_ip__iexact=identificador)
                        | Q(ip_fija__iexact=identificador)
                    ).first()
                    if not equipo_obj:
                        raise SimCard.DoesNotExist
                except (SimCard.DoesNotExist, Exception):
                    errores_equipos.append(f"SIM {identificador} no encontrada")
                    continue
            elif tipo_eq == 'MODEM':
                try:
                    equipo_obj = Modem.objects.filter(
                        Q(serie__iexact=identificador)
                        | Q(imei__iexact=identificador)
                    ).first()
                    if not equipo_obj:
                        raise Modem.DoesNotExist
                except (Modem.DoesNotExist, Exception):
                    errores_equipos.append(f"Módem {identificador} no encontrado")
                    continue
            
            # Crear item si se encontró el equipo
            if equipo_obj:
                item_kwargs = {
                    'movimiento': movimiento,
                    'tipo_equipo': tipo_eq,
                    'cantidad': 1
                }
                
                if tipo_eq == 'MEDIDOR':
                    item_kwargs['medidor'] = equipo_obj
                elif tipo_eq == 'SIM':
                    item_kwargs['simcard'] = equipo_obj
                elif tipo_eq == 'MODEM':
                    item_kwargs['modem'] = equipo_obj
                
                MovimientoItem.objects.create(**item_kwargs)
                items_creados += 1
        
        # Respuesta exitosa
        logger.info(f"Movimiento #{movimiento.id} creado con {items_creados} items")
        
        payload = {
            'success': True,
            'movimiento_id': movimiento.id,
            'items_creados': items_creados,
            'errores': errores_equipos if errores_equipos else None,
            'message': 'Movimiento registrado exitosamente'
        }
        if errores_equipos:
            payload['message'] = f'Movimiento registrado con observaciones: {len(errores_equipos)} equipo(s) no encontrado(s)'
        return JsonResponse(payload)
        
    except json.JSONDecodeError:
        logger.error("Error al parsear JSON del webhook MoreApp")
        return JsonResponse({
            'success': False,
            'error': 'Formato JSON inválido'
        }, status=400)
    except Exception as e:
        logger.error(f"Error procesando webhook MoreApp: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': f'Error interno: {str(e)}'
        }, status=500)


@login_required
@role_required(['ADMIN'])
def usuario_eliminar_view(request, pk):
    from usuarios.models import Usuario
    from django.contrib import messages
    from django.db.models.deletion import ProtectedError
    if request.method == "POST":
        try:
            usuario = Usuario.objects.get(pk=pk)
        except Usuario.DoesNotExist:
            messages.error(request, "Usuario no encontrado")
            return redirect('usuarios_list')
        # No permitir que un usuario se elimine a sí mismo
        if usuario == request.user:
            messages.error(request, "No puedes eliminar tu propio perfil.")
            return redirect('usuarios_list')
        try:
            usuario.delete()
            messages.success(request, "Usuario eliminado correctamente.")
        except ProtectedError:
            # Mantiene trazabilidad histórica cuando el usuario tiene movimientos registrados.
            if usuario.is_active:
                usuario.is_active = False
                usuario.save(update_fields=['is_active'])
            movimientos_asociados = usuario.movimientos_registrados.count()
            messages.warning(
                request,
                f"El usuario no puede eliminarse porque tiene {movimientos_asociados} movimientos asociados. "
                "Fue desactivado para ocultarlo del listado."
            )
        return redirect('usuarios_list')
    return redirect('usuarios_list')


# ─────────────────────────────────────────────────────────────────────────────
# REPORTES — Integraciones MoreApp
# ─────────────────────────────────────────────────────────────────────────────

ROLES_REPORTES_LECTURA = ('ADMIN', 'ADMINISTRATIVO', 'AUDITOR', 'GERENCIA')
ROLES_REPORTES_GESTION = ('ADMIN', 'ADMINISTRATIVO')


def _ejecutar_autosync_moreapp_si_corresponde():
    """Ejecuta lectura automática MoreApp en intervalos para evitar depender solo del botón manual.

    Returns:
        dict | None: estadísticas de leer_carpetas() si corrió, o None si se omitió/falló.
    """
    if not getattr(settings, 'MOREAPP_AUTO_SYNC_ENABLED', True):
        return None

    from django.core.cache import cache
    from django.utils import timezone
    from integraciones.reader import leer_carpetas

    intervalo = int(getattr(settings, 'MOREAPP_AUTO_SYNC_INTERVAL_SECONDS', 300) or 300)
    if intervalo < 30:
        intervalo = 30

    key = 'moreapp:last_auto_sync_ts'
    ahora_ts = timezone.now().timestamp()
    ultimo_ts = cache.get(key)
    if ultimo_ts and (ahora_ts - float(ultimo_ts)) < intervalo:
        return None

    # Throttle simple para evitar múltiples ejecuciones simultáneas entre requests.
    cache.set(key, ahora_ts, timeout=intervalo)
    try:
        max_segundos = getattr(settings, 'MOREAPP_WEB_SYNC_MAX_SEGUNDOS', 30)
        max_archivos = getattr(settings, 'MOREAPP_WEB_SYNC_MAX_ARCHIVOS', 40)
        skip_dup = getattr(settings, 'MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS', True)
        stats = leer_carpetas(
            reprocesar_duplicados=not skip_dup,
            max_archivos=max_archivos,
            max_segundos=max_segundos,
        )
        # Siempre refrescar caches de pendientes/avisos tras un ciclo de sync
        # (aunque no haya "nuevos", puede haber reprocesos que cambien revisión).
        from web.moreapp_ops import registrar_resultado_sync

        registrar_resultado_sync(stats or {}, origen='auto')
        return stats
    except Exception:
        logger.exception('Fallo en autosincronización MoreApp')
        return None


def _categorias_advertencia_registro(registro):
    """Devuelve categorías de advertencia normalizadas para un registro MoreApp."""
    categorias = set()
    for bloqueo in _extraer_bloqueos_operativos_registro(registro):
        motivo = bloqueo.get('motivo', '').lower()
        origen = bloqueo.get('origen', '')
        if origen == 'alerta_critica' or 'alerta_critica' in motivo:
            categorias.add('critica')
        elif 'no encontrada' in motivo or 'no encontrado' in motivo:
            categorias.add('equipo')
        elif 'no se puede instalar' in motivo:
            categorias.add('regla')
        elif 'doble trabajo' in motivo or 'ya instalado' in motivo:
            categorias.add('doble')

    desc = str(getattr(registro, 'descripcion_alerta', '') or '')
    if 'ALERTA_CRITICA' in desc.upper():
        categorias.add('critica')

    # El flag alerta_doble_trabajo se usó históricamente también para bloqueos de regla.
    # Solo contar como "doble" si no hay categoría más específica o el texto lo dice.
    if 'critica' not in categorias:
        desc_l = desc.lower()
        if 'doble trabajo' in desc_l or 'ALERTA_ASIGNACION' in desc.upper():
            categorias.add('doble')
        elif registro.alerta_doble_trabajo and not categorias:
            categorias.add('doble')

    return categorias


def _fecha_desde_json_moreapp(registro):
    """Obtiene fecha/hora preferente desde JSON MoreApp (campo `date`), con fallback seguro."""
    datos_recibidos = registro.datos_recibidos if isinstance(registro.datos_recibidos, dict) else {}
    bloque_data = datos_recibidos.get('data', {}) if isinstance(datos_recibidos, dict) else {}
    bloque_meta = datos_recibidos.get('meta', {}) if isinstance(datos_recibidos, dict) else {}
    datos_procesados = registro.datos_procesados if isinstance(registro.datos_procesados, dict) else {}

    candidatas = [
        str(datos_recibidos.get('date', '')).strip(),
        str(bloque_data.get('date', '')).strip() if isinstance(bloque_data, dict) else '',
        str(bloque_meta.get('registrationDate', '')).strip() if isinstance(bloque_meta, dict) else '',
        str(datos_procesados.get('fecha_registro', '')).strip(),
        str(bloque_data.get('fecha', '')).strip() if isinstance(bloque_data, dict) else '',
        str(datos_procesados.get('fecha_trabajo', '')).strip(),
    ]

    from django.utils import timezone

    primer_dt_sin_hora = None

    for candidata in candidatas:
        if not candidata:
            continue

        for valor in (candidata, candidata.replace('Z', '+00:00')):
            try:
                dt = datetime.fromisoformat(valor)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                else:
                    dt = timezone.localtime(dt)

                if dt.hour != 0 or dt.minute != 0 or dt.second != 0 or dt.microsecond != 0:
                    return dt
                if primer_dt_sin_hora is None:
                    primer_dt_sin_hora = dt
            except ValueError:
                continue

        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(candidata, fmt)
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
                if dt.hour != 0 or dt.minute != 0:
                    return dt
                if primer_dt_sin_hora is None:
                    primer_dt_sin_hora = dt
            except ValueError:
                continue

    if primer_dt_sin_hora is not None:
        return primer_dt_sin_hora

    return registro.fecha_recepcion


def _tecnico_visible_moreapp(registro):
    """Devuelve el texto visible de técnico en listados MoreApp."""
    datos_procesados = registro.datos_procesados if isinstance(registro.datos_procesados, dict) else {}

    tecnico_responsable = str(datos_procesados.get('tecnico_responsable', '')).strip()
    if tecnico_responsable:
        return tecnico_responsable

    tecnico_certelec = str(datos_procesados.get('tecnico_certelec', '')).strip()
    if tecnico_certelec:
        return 'Certelec'

    return ''


def _calcular_adv_breakdown(model_class):
    """Cuenta registros con advertencia agrupados en categorías (cache 60s)."""
    from django.db.models import Q as _Q
    from web.perf_cache import cache_get_or_set, TTL_CORTO

    def _calc():
        adv_equipo = 0
        adv_regla = 0
        adv_doble = 0
        adv_critica = 0
        qs = model_class.objects.filter(
            eliminado=False,
            estado_revision__in=('PENDIENTE', 'CON_ADVERTENCIA'),
        ).filter(
            _Q(estado_revision='CON_ADVERTENCIA') | _Q(alerta_doble_trabajo=True)
        ).only('datos_procesados', 'descripcion_alerta', 'alerta_doble_trabajo')
        for reg in qs.iterator(chunk_size=500):
            cats = _categorias_advertencia_registro(reg)
            adv_equipo += int('equipo' in cats)
            adv_regla += int('regla' in cats)
            adv_doble += int('doble' in cats)
            adv_critica += int('critica' in cats)
        return [
            {'categoria': 'Sin equipo en inventario', 'count': adv_equipo},
            {'categoria': 'Bloqueo de regla operativa', 'count': adv_regla},
            {'categoria': 'Doble trabajo / conflicto', 'count': adv_doble},
            {'categoria': 'Alerta crítica (otro cliente)', 'count': adv_critica},
        ]

    return cache_get_or_set('moreapp:adv_breakdown', _calc, TTL_CORTO)


# ═══════════════════════════════════════════════════════════════════════════
# API DE BÚSQUEDA PARA ÓRDENES DE TRABAJO (Autocomplete)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def api_buscar_clientes(request):
    """API para buscar clientes por número, nombre, dirección o comuna (autocomplete)."""
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    try:
        qs = (
            Cliente.objects.filter(activo=True)
            .exclude(numero_cliente='0')
            .filter(
                Q(numero_cliente__icontains=query)
                | Q(customer_name__icontains=query)
                | Q(direccion__icontains=query)
                | Q(installation_address__icontains=query)
                | Q(comuna__icontains=query)
            )
            .order_by('numero_cliente')
            .values('id', 'numero_cliente', 'customer_name', 'direccion', 'installation_address', 'comuna')[:20]
        )
        results = []
        for row in qs:
            nombre = (row.get('customer_name') or '').strip()
            direccion = (row.get('installation_address') or row.get('direccion') or '').strip()
            partes = [row['numero_cliente']]
            if nombre:
                partes.append(nombre)
            elif direccion:
                partes.append(direccion)
            label = ' · '.join(partes)
            if row.get('comuna'):
                label = f"{label} ({row['comuna']})"
            results.append({
                'id': row['id'],
                'numero_cliente': row['numero_cliente'],
                'customer_name': nombre,
                'direccion': direccion,
                'comuna': row.get('comuna') or '',
                'label': label,
            })
        return JsonResponse({'results': results})
    except Exception as e:
        return JsonResponse({'results': [], 'error': str(e)}, status=400)


@login_required
def api_buscar_tecnicos(request):
    """API para buscar técnicos activos por nombre interno o nombre completo."""
    from usuarios.models import Usuario

    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    try:
        qs = (
            Usuario.objects.filter(rol='TECNICO', is_active=True)
            .filter(
                Q(nombre_interno__icontains=query)
                | Q(nombre__icontains=query)
                | Q(apellido__icontains=query)
                | Q(email__icontains=query)
            )
            .order_by('nombre_interno')[:20]
        )
        results = []
        for u in qs:
            completo = ' '.join(filter(None, [getattr(u, 'nombre', ''), getattr(u, 'apellido', '')])).strip()
            label = u.nombre_interno or completo or str(u.pk)
            if completo and completo.casefold() != (u.nombre_interno or '').casefold():
                label = f'{u.nombre_interno} · {completo}'
            results.append({
                'id': u.pk,
                'nombre_interno': u.nombre_interno or '',
                'nombre_completo': completo,
                'label': label,
            })
        return JsonResponse({'results': results})
    except Exception as e:
        return JsonResponse({'results': [], 'error': str(e)}, status=400)


@login_required
def api_buscar_medidores(request):
    """API para buscar medidores por serie, caja, marca o tipo (autocomplete).

    Query params:
      q: texto (mín. 2)
      libres=1: solo medidores sin cliente asignado (alta de cliente)
    """
    from django.db.models.functions import Lower

    query = request.GET.get('q', '').strip()
    solo_libres = str(request.GET.get('libres', '') or '').strip().lower() in {'1', 'true', 'si', 'sí', 'yes'}

    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    try:
        q_norm = query.lower()
        filtro = (
            Q(serie__icontains=query)
            | Q(caja__icontains=query)
            | Q(marca__icontains=query)
        )
        # Permitir buscar por tipo: "indirecto", "directo", INDIRECTO, DIRECTO
        if 'indirect' in q_norm:
            filtro |= Q(tipo_medidor='INDIRECTO')
        elif q_norm in {'directo', 'direct'} or query.upper() == 'DIRECTO':
            filtro |= Q(tipo_medidor='DIRECTO')
        if query.upper() in {'DIRECTO', 'INDIRECTO'}:
            filtro |= Q(tipo_medidor=query.upper())

        medidores = Medidor.objects.filter(eliminado=False).filter(filtro)

        if solo_libres:
            asignados_ids = list(
                Cliente.objects.filter(activo=True, medidor_actual_id__isnull=False)
                .values_list('medidor_actual_id', flat=True)
            )
            series_norm = [
                (s or '').strip().lower()
                for s in Cliente.objects.filter(activo=True)
                .exclude(Q(meter_serial_n_1__isnull=True) | Q(meter_serial_n_1=''))
                .values_list('meter_serial_n_1', flat=True)
                if (s or '').strip()
            ]
            medidores = medidores.exclude(id__in=asignados_ids)
            if series_norm:
                medidores = medidores.annotate(_serie_l=Lower('serie')).exclude(_serie_l__in=series_norm)

        medidores_list = list(
            medidores.select_related('entregado_a', 'en_custodia_de').order_by('serie')[:20]
        )

        results = []
        for med in medidores_list:
            custodia = (
                getattr(getattr(med, 'en_custodia_de', None), 'nombre_interno', None)
                or getattr(getattr(med, 'entregado_a', None), 'nombre_interno', None)
                or 'Bodega'
            )
            tipo_codigo = (getattr(med, 'tipo_medidor', '') or '').strip().upper()
            tipo_txt = med.get_tipo_medidor_display() if hasattr(med, 'get_tipo_medidor_display') else tipo_codigo
            if not tipo_txt and tipo_codigo:
                tipo_txt = 'Indirecto' if tipo_codigo == 'INDIRECTO' else ('Directo' if tipo_codigo == 'DIRECTO' else tipo_codigo)
            label = f"{med.serie} - {med.marca or 'S/M'}"
            if tipo_txt:
                label = f"{label} ({tipo_txt})"
            results.append({
                'id': med.id,
                'serie': med.serie,
                'caja': med.caja or '',
                'marca': med.marca or 'No especificada',
                'tipo_medidor': tipo_txt or '—',
                'tipo_medidor_codigo': tipo_codigo,
                'custodia': custodia,
                'label': label,
            })

        return JsonResponse({'results': results})
    except Exception as e:
        return JsonResponse({'results': [], 'error': str(e)}, status=400)


@login_required
def api_obtener_medidor(request, medidor_id):
    """API para obtener detalles completos de un medidor"""
    try:
        medidor = Medidor.objects.filter(eliminado=False).select_related(
            'en_custodia_de', 'entregado_a'
        ).get(id=medidor_id)
        custodia = (
            getattr(getattr(medidor, 'en_custodia_de', None), 'nombre_interno', None)
            or getattr(getattr(medidor, 'entregado_a', None), 'nombre_interno', None)
            or 'Bodega'
        )
        return JsonResponse({
            'id': medidor.id,
            'serie': medidor.serie,
            'caja': medidor.caja,
            'marca': medidor.marca or 'No especificada',
            'modelo': getattr(medidor, 'modelo', '') or 'No especificado',
            'tipo': medidor.get_tipo_medidor_display() if hasattr(medidor, 'get_tipo_medidor_display') else 'Estándar',
            'en_custodia': custodia,
        })
    except Medidor.DoesNotExist:
        return JsonResponse({'error': 'Medidor no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


_ORIGEN_BLOQUEO_META = {
    'pendiente_revision': {
        'label': 'Equipo no encontrado',
        'detalle': 'El identificador del informe no existe en inventario.',
        'badge': 'bg-warning text-dark',
        'icon': 'bi-search',
    },
    'regla_operativa': {
        'label': 'Regla operativa',
        'detalle': 'El cambio de estado fue bloqueado por una regla de negocio.',
        'badge': 'bg-danger',
        'icon': 'bi-shield-exclamation',
    },
    'doble_trabajo': {
        'label': 'Posible doble trabajo',
        'detalle': 'Conflicto de instalación o actividad reciente en el mismo cliente.',
        'badge': 'bg-warning text-dark',
        'icon': 'bi-people',
    },
    'alerta_critica': {
        'label': 'Alerta crítica',
        'detalle': 'Equipo ya asignado a otro cliente. No se reasignó automáticamente: corregir manualmente.',
        'badge': 'bg-danger',
        'icon': 'bi-exclamation-octagon-fill',
    },
    'alerta_operativa': {
        'label': 'Alerta operativa',
        'detalle': 'Inconsistencia detectada al cruzar datos del terreno con el sistema.',
        'badge': 'bg-secondary',
        'icon': 'bi-exclamation-triangle',
    },
}


def _url_inventario_bloqueo(tipo_equipo: str, identificador: str) -> str:
    tipo = str(tipo_equipo or '').upper().strip()
    ident = str(identificador or '').strip()
    if not ident:
        return ''
    if tipo == 'MEDIDOR':
        return f'/inventario/?tipo=medidor&campo=serie&q={quote_plus(ident)}'
    if tipo == 'MODEM':
        return f'/inventario/?tipo=modem&campo=serie&q={quote_plus(ident)}'
    if tipo == 'SIM':
        return f'/inventario/?tipo=sim&campo=direccion_ip&q={quote_plus(ident)}'
    return ''


def _clasificar_origen_alerta(motivo: str) -> str:
    texto = str(motivo or '').lower()
    if (
        'alerta_critica' in texto
        or 'ya asignado' in texto
        or 'no se reasign' in texto
        or 'corregir manualmente' in texto
        or 'sin cambios automáticos' in texto
        or 'sin reasignación automática' in texto
    ):
        return 'alerta_critica'
    if 'doble trabajo' in texto or 'ya instalado' in texto or 'otro cliente' in texto:
        return 'doble_trabajo'
    if 'no se puede instalar' in texto or 'bloqueo_operativo' in texto:
        return 'regla_operativa'
    if 'no encontrad' in texto:
        return 'pendiente_revision'
    return 'alerta_operativa'


def _enriquecer_bloqueo_operativo(item: dict) -> dict:
    origen = item.get('origen') or 'alerta_operativa'
    meta = _ORIGEN_BLOQUEO_META.get(origen, _ORIGEN_BLOQUEO_META['alerta_operativa'])
    tipo_equipo = str(item.get('tipo_equipo', '')).upper().strip()
    identificador = str(item.get('identificador', '')).strip()
    motivo = str(item.get('motivo', '')).strip()
    enriquecido = {
        **item,
        'origen': origen,
        'origen_label': meta['label'],
        'origen_detalle': meta['detalle'],
        'origen_badge': meta['badge'],
        'origen_icon': meta['icon'],
        'tipo_equipo': tipo_equipo,
        'identificador': identificador,
        'motivo': motivo,
        'inventario_url': _url_inventario_bloqueo(tipo_equipo, identificador),
        'es_critica': origen == 'alerta_critica',
    }
    return enriquecido


def _parsear_marcador_alerta(prefijo: str, cuerpo: str, origen: str) -> dict:
    contexto = ''
    texto = str(cuerpo or '').strip()
    if ' | CONTEXTO:' in texto:
        texto, contexto = texto.split(' | CONTEXTO:', 1)
        contexto = contexto.strip().strip('|').strip()

    motivo = texto
    tipo_equipo = ''
    identificador = ''
    if ':' in texto:
        cabecera, motivo = texto.split(':', 1)
        motivo = motivo.strip()
        partes = cabecera.strip().split(None, 1)
        if partes:
            tipo_equipo = partes[0].upper()
        if len(partes) > 1:
            identificador = partes[1].strip()

    if contexto:
        motivo = f'{motivo} (contexto: {contexto})'

    return {
        'origen': origen,
        'tipo_equipo': tipo_equipo,
        'identificador': identificador,
        'motivo': motivo or prefijo,
    }


def _parsear_parte_descripcion_alerta(parte: str) -> dict:
    texto = str(parte or '').strip()
    if not texto:
        return {}

    upper = texto.upper()
    if upper.startswith('ALERTA_CRITICA'):
        cuerpo = texto.split('|', 1)[1].strip() if '|' in texto else texto
        return _parsear_marcador_alerta('ALERTA_CRITICA', cuerpo, 'alerta_critica')

    if upper.startswith('BLOQUEO_OPERATIVO'):
        cuerpo = texto.split('|', 1)[1].strip() if '|' in texto else texto
        return _parsear_marcador_alerta('BLOQUEO_OPERATIVO', cuerpo, 'regla_operativa')

    if upper.startswith('ALERTA_ASIGNACION'):
        cuerpo = texto.split('|', 1)[1].strip() if '|' in texto else texto
        return _parsear_marcador_alerta('ALERTA_ASIGNACION', cuerpo, 'doble_trabajo')

    origen = _clasificar_origen_alerta(texto)
    return {
        'origen': origen,
        'tipo_equipo': '',
        'identificador': '',
        'motivo': texto,
    }


def _segmentar_descripcion_alerta(descripcion: str):
    """Parte descripcion_alerta por marcadores (no por cada '|')."""
    texto = str(descripcion or '').strip()
    if not texto:
        return []

    patron = re.compile(
        r'(?=(?:ALERTA_CRITICA|BLOQUEO_OPERATIVO|ALERTA_ASIGNACION|ERROR_SYNC)\s*\|)',
        re.IGNORECASE,
    )
    partes = [p.strip() for p in patron.split(texto) if p and p.strip()]
    if not partes:
        return [texto]
    return partes


def _numero_cliente_desde_moreapp(registro) -> str:
    """Extrae Nº cliente legible desde datos procesados o payload MoreApp."""
    datos = registro.datos_procesados if isinstance(getattr(registro, 'datos_procesados', None), dict) else {}
    for clave in ('cliente_codigo', 'nro_cliente', 'numero_cliente', 'codigo_cliente'):
        valor = str(datos.get(clave) or '').strip()
        if valor:
            return valor

    raw = registro.datos_recibidos if isinstance(getattr(registro, 'datos_recibidos', None), dict) else {}
    data = raw.get('data') if isinstance(raw.get('data'), dict) else {}
    candidatos = [
        data.get('cliente'),
        data.get('numero_cliente'),
    ]
    buscar = data.get('buscarCliente') if isinstance(data.get('buscarCliente'), dict) else {}
    candidatos.append(buscar.get('CLIENTE1'))
    mant = data.get('clienteParaMantenimiento') if isinstance(data.get('clienteParaMantenimiento'), dict) else {}
    candidatos.append(mant.get('NROCLIENTE'))
    for c in candidatos:
        valor = str(c or '').strip()
        if valor:
            return valor
    return ''


def _extraer_bloqueos_operativos_registro(registro):
    """Devuelve lista normalizada de bloqueos/alertas operativas (incluye históricos)."""
    bloqueos = []

    datos = registro.datos_procesados if isinstance(registro.datos_procesados, dict) else {}
    resultado_operativo = datos.get('resultado_operativo', {}) if isinstance(datos, dict) else {}
    pendientes = resultado_operativo.get('pendientes_revision', []) if isinstance(resultado_operativo, dict) else []

    for p in pendientes:
        if not isinstance(p, dict):
            continue
        motivo = str(p.get('motivo', '')).strip()
        if not motivo:
            continue
        origen = 'pendiente_revision'
        if str(motivo).upper().startswith('CRITICO:') or 'alerta_critica' in motivo.lower():
            origen = 'alerta_critica'
            motivo = motivo.split(':', 1)[-1].strip() if ':' in motivo else motivo
        bloqueos.append({
            'origen': origen,
            'tipo_equipo': str(p.get('tipo_equipo', '')).upper().strip(),
            'identificador': str(p.get('identificador', '')).strip(),
            'motivo': motivo,
        })

    descripcion = str(registro.descripcion_alerta or '').strip()
    if descripcion:
        for parte in _segmentar_descripcion_alerta(descripcion):
            parsed = _parsear_parte_descripcion_alerta(parte)
            if parsed:
                bloqueos.append(parsed)

    vistos = set()
    resultado = []
    for item in bloqueos:
        motivo_norm = re.sub(r'\s+', ' ', str(item.get('motivo', '') or '')).strip().strip('|').strip()
        # Para dedupe, ignorar el "contexto: ..." (submission) que puede variar por un "|"
        motivo_clave = re.split(r'\s*\(contexto:', motivo_norm, maxsplit=1)[0].strip().lower()
        key = (
            item.get('origen', ''),
            item.get('tipo_equipo', ''),
            item.get('identificador', ''),
            motivo_clave,
        )
        if not motivo_clave or key in vistos:
            continue
        vistos.add(key)
        item = {**item, 'motivo': motivo_norm}
        resultado.append(_enriquecer_bloqueo_operativo(item))
    return resultado


@login_required
def reportes_moreapp_list(request):
    """Lista de registros MoreApp con paginación servidor (no materializa todo el JSON)."""
    from django.core.paginator import Paginator
    from ordenes_trabajo.models import IntegracionMoreApp

    if request.user.rol not in ROLES_REPORTES_LECTURA:
        messages.error(request, 'No tienes permiso para acceder a Reportes.')
        return redirect('dashboard')

    # Autosync solo si MOREAPP_AUTO_SYNC_ENABLED=true (off por defecto en producción)
    _ejecutar_autosync_moreapp_si_corresponde()

    qs_base = IntegracionMoreApp.objects.filter(eliminado=False).order_by('-fecha_recepcion')

    estado = request.GET.get('estado', '')
    alerta = request.GET.get('alerta', '')
    bloqueo = request.GET.get('bloqueo', '')
    revision = request.GET.get('revision', '')
    q = request.GET.get('q', '')
    formulario = request.GET.get('formulario', '')
    kpi = request.GET.get('kpi', '')
    try:
        per_page = int(request.GET.get('per_page') or 50)
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in (25, 50, 100):
        per_page = 50

    qs = qs_base
    if estado:
        qs = qs.filter(estado_sincronizacion=estado)
    if alerta == '1':
        qs = qs.filter(alerta_doble_trabajo=True)
    if alerta == 'critica':
        qs = qs.filter(
            descripcion_alerta__icontains='ALERTA_CRITICA',
            estado_revision__in=('PENDIENTE', 'CON_ADVERTENCIA'),
        )
    if revision:
        qs = qs.filter(estado_revision=revision)
    if kpi == 'advertencia':
        qs = qs.filter(estado_revision='CON_ADVERTENCIA')
    if kpi == 'adv_critica':
        qs = qs.filter(
            descripcion_alerta__icontains='ALERTA_CRITICA',
            estado_revision__in=('PENDIENTE', 'CON_ADVERTENCIA'),
        )
    if q:
        qs = qs.filter(
            Q(nombre_formulario__icontains=q) |
            Q(moreapp_submission_id__icontains=q) |
            Q(datos_procesados__cliente_nombre__icontains=q) |
            Q(datos_procesados__cliente_codigo__icontains=q)
        )

    formularios = list(
        qs.values('nombre_formulario')
        .annotate(total=Count('id'))
        .order_by('nombre_formulario')
    )

    if formulario:
        qs = qs.filter(nombre_formulario=formulario)

    # Filtros que requieren parseo Python: reducen a IDs sin enriquecer todas las filas en HTML.
    # Los KPI de advertencia (equipo/regla/doble) usan la misma base que _calcular_adv_breakdown:
    # solo pendientes/con advertencia abiertas (no REVISADO ni cerrados).
    needs_python_filter = bloqueo == '1' or kpi in ('adv_equipo', 'adv_regla', 'adv_doble')
    if needs_python_filter:
        if kpi in ('adv_equipo', 'adv_regla', 'adv_doble'):
            qs = qs.filter(
                estado_revision__in=('PENDIENTE', 'CON_ADVERTENCIA'),
            ).filter(
                Q(estado_revision='CON_ADVERTENCIA') | Q(alerta_doble_trabajo=True)
            )
        matched_ids = []
        for reg in qs.only(
            'id', 'datos_procesados', 'descripcion_alerta', 'alerta_doble_trabajo',
        ).iterator(chunk_size=500):
            cats = _categorias_advertencia_registro(reg)
            if bloqueo == '1' and not _extraer_bloqueos_operativos_registro(reg):
                continue
            if kpi == 'adv_equipo' and 'equipo' not in cats:
                continue
            if kpi == 'adv_regla' and 'regla' not in cats:
                continue
            if kpi == 'adv_doble' and 'doble' not in cats:
                continue
            matched_ids.append(reg.pk)
        qs = IntegracionMoreApp.objects.filter(
            pk__in=matched_ids, eliminado=False
        ).order_by('-fecha_recepcion')

    total = qs.count()
    page_obj = Paginator(qs, per_page).get_page(request.GET.get('page') or 1)
    registros = list(page_obj.object_list)

    for reg in registros:
        bloqueos = _extraer_bloqueos_operativos_registro(reg)
        categorias_advertencia = _categorias_advertencia_registro(reg)
        reg.bloqueos_operativos = bloqueos
        reg.categorias_advertencia = categorias_advertencia
        reg.fecha_visible = _fecha_desde_json_moreapp(reg)
        reg.tecnico_visible = _tecnico_visible_moreapp(reg)
        reg.tiene_bloqueo_operativo = len(bloqueos) > 0
        reg.bloqueo_operativo_preview = bloqueos[0]['motivo'] if bloqueos else ''
        reg.es_alerta_critica = (
            'critica' in categorias_advertencia
            or 'ALERTA_CRITICA' in str(reg.descripcion_alerta or '').upper()
        )
        if bloqueos:
            primero = bloqueos[0]
            equipo_txt = ' '.join(
                filter(None, [primero.get('tipo_equipo'), primero.get('identificador')])
            ).strip()
            motivo = (primero.get('motivo') or '').strip()
            label = (primero.get('origen_label') or 'Advertencia').strip()
            preview = f'{label}: {equipo_txt + " — " if equipo_txt else ""}{motivo}'.strip()
            reg.alerta_preview = preview[:180]
        else:
            reg.alerta_preview = (reg.descripcion_alerta or '')[:180]
        reg.delete_url = f'/reportes/moreapp/{reg.pk}/eliminar/' if request.user.rol == 'ADMIN' else ''

    adv_breakdown = _calcular_adv_breakdown(IntegracionMoreApp)
    adv_counts = {
        'equipo': next((x['count'] for x in adv_breakdown if x['categoria'] == 'Sin equipo en inventario'), 0),
        'regla': next((x['count'] for x in adv_breakdown if x['categoria'] == 'Bloqueo de regla operativa'), 0),
        'doble': next((x['count'] for x in adv_breakdown if x['categoria'] == 'Doble trabajo / conflicto'), 0),
        'critica': next((x['count'] for x in adv_breakdown if x['categoria'] == 'Alerta crítica (otro cliente)'), 0),
    }

    from web.perf_cache import cache_get_or_set, TTL_CORTO

    def _kpis_moreapp():
        activos = IntegracionMoreApp.objects.filter(eliminado=False)
        return {
            'pendientes': activos.filter(estado_revision='PENDIENTE').count(),
            'con_advertencia': activos.filter(estado_revision='CON_ADVERTENCIA').count(),
            'alertas': activos.filter(alerta_doble_trabajo=True).count(),
            'errores': activos.filter(
                estado_sincronizacion__in=('ERROR_JSON', 'ERROR_LECTURA', 'ERROR')
            ).count(),
            'sinc_breakdown': list(
                activos.values('estado_sincronizacion')
                .annotate(c=Count('id'))
                .order_by('-c')
            ),
            'formula_breakdown': list(
                activos.values('nombre_formulario')
                .annotate(c=Count('id'))
                .order_by('-c')
            ),
        }

    kpis = cache_get_or_set('moreapp:list_kpis', _kpis_moreapp, TTL_CORTO)

    query_params = request.GET.copy()
    query_params.pop('page', None)

    moreapp_ops = None
    if request.user.rol in ROLES_REPORTES_GESTION:
        from web.moreapp_ops import construir_ops_status_moreapp
        moreapp_ops = construir_ops_status_moreapp()

    context = {
        'registros': registros,
        'page_obj': page_obj,
        'query_string': query_params.urlencode(),
        'per_page': per_page,
        'estado_actual': estado,
        'alerta_actual': alerta,
        'bloqueo_actual': bloqueo,
        'revision_actual': revision,
        'q': q,
        'formulario_actual': formulario,
        'kpi_actual': kpi,
        'formularios': formularios,
        'total': total,
        'puede_eliminar_reportes': request.user.rol == 'ADMIN',
        'adv_counts': adv_counts,
        'pendientes': kpis['pendientes'],
        'con_advertencia': kpis['con_advertencia'],
        'alertas': kpis['alertas'],
        'errores': kpis['errores'],
        'estados_choices': IntegracionMoreApp.ESTADO_CHOICES,
        'revision_choices': IntegracionMoreApp.ESTADO_REVISION_CHOICES,
        'moreapp_auto_refresh_seconds': int(getattr(settings, 'MOREAPP_AUTO_REFRESH_SECONDS', 300) or 300),
        'sinc_breakdown': kpis['sinc_breakdown'],
        'formula_breakdown': kpis['formula_breakdown'],
        'adv_breakdown': adv_breakdown,
        'moreapp_ops': moreapp_ops,
    }
    return render(request, 'reportes/integraciones_list.html', context)


@login_required
def reportes_moreapp_detalle(request, pk):
    """Detalle de un registro MoreApp individual."""
    from ordenes_trabajo.models import IntegracionMoreApp
    from inventario.models import MovimientoInventario

    if request.user.rol not in ROLES_REPORTES_LECTURA:
        messages.error(request, 'No tienes permiso para acceder a Reportes.')
        return redirect('dashboard')

    registro = get_object_or_404(IntegracionMoreApp, pk=pk, eliminado=False)
    datos_procesados = registro.datos_procesados if isinstance(registro.datos_procesados, dict) else {}
    resultado_operativo = datos_procesados.get('resultado_operativo', {}) if isinstance(datos_procesados, dict) else {}

    bloqueos_operativos = _extraer_bloqueos_operativos_registro(registro)
    pendientes_revision = [
        bloqueo for bloqueo in bloqueos_operativos
        if bloqueo.get('origen') == 'pendiente_revision'
    ]

    movimientos_operativos = list(
        MovimientoInventario.objects.filter(
            observacion__icontains=f'submission: {registro.moreapp_submission_id}'
        )
        .select_related('origen', 'destino', 'responsable')
        .prefetch_related('items__medidor', 'items__modem', 'items__simcard')
        .order_by('-fecha_hora')[:30]
    )

    for mov in movimientos_operativos:
        detalles = []
        for item in mov.items.all():
            if item.medidor:
                detalles.append(f'MEDIDOR {item.medidor.serie}')
            elif item.modem:
                detalles.append(f'MODEM {item.modem.serie}')
            elif item.simcard:
                sim_ident = item.simcard.direccion_ip or item.simcard.ip_fija or item.simcard.imei or item.simcard.abonado or item.simcard.pk
                detalles.append(f'SIM {sim_ident}')
            else:
                detalles.append(item.get_tipo_equipo_display())
        mov.detalle_items = ', '.join(detalles) if detalles else '-'

    if request.user.rol == 'ADMIN':
        registro_delete_url = f'/reportes/moreapp/{registro.pk}/eliminar/'
    else:
        registro_delete_url = ''

    # GPS + fotos (punto 6): enriquecer al vuelo si el registro aún no los tiene materializados
    from integraciones.moreapp_media import enriquecer_datos_media
    moreapp_geo = datos_procesados.get('geo') if isinstance(datos_procesados.get('geo'), dict) else {}
    moreapp_fotos = datos_procesados.get('fotos') if isinstance(datos_procesados.get('fotos'), list) else []
    if not moreapp_geo or not moreapp_fotos:
        payload = registro.datos_recibidos if isinstance(registro.datos_recibidos, dict) else {}
        enriquecidos = enriquecer_datos_media(
            datos_procesados,
            payload,
            ruta_carpeta=registro.ruta_carpeta or '',
            submission_id=registro.moreapp_submission_id or '',
        )
        moreapp_geo = enriquecidos.get('geo') or moreapp_geo or {}
        moreapp_fotos = enriquecidos.get('fotos') or moreapp_fotos or []
        # Persistir para no recalcular siempre
        if enriquecidos.get('geo') or enriquecidos.get('fotos'):
            registro.datos_procesados = {
                **datos_procesados,
                'geo': enriquecidos.get('geo') or datos_procesados.get('geo'),
                'fotos': enriquecidos.get('fotos') or [],
                'fotos_disponibles': enriquecidos.get('fotos_disponibles', 0),
                'fotos_total': enriquecidos.get('fotos_total', 0),
                'location': enriquecidos.get('location') or datos_procesados.get('location'),
            }
            try:
                registro.save(update_fields=['datos_procesados'])
            except Exception:
                pass

    return render(request, 'reportes/integracion_detalle.html', {
        'registro': registro,
        'registro_delete_url': registro_delete_url,
        'resultado_operativo': resultado_operativo,
        'pendientes_revision': pendientes_revision,
        'bloqueos_operativos': bloqueos_operativos,
        'movimientos_operativos': movimientos_operativos,
        'mostrar_panel_operativo': request.user.rol in ('ADMIN', 'ADMINISTRATIVO'),
        'es_alerta_critica': (
            'ALERTA_CRITICA' in str(registro.descripcion_alerta or '').upper()
            or any(b.get('es_critica') for b in bloqueos_operativos)
        ),
        'moreapp_geo': moreapp_geo,
        'moreapp_fotos': moreapp_fotos,
        'moreapp_fotos_disponibles': sum(1 for f in moreapp_fotos if f.get('disponible')),
    })


@login_required
def reportes_moreapp_sincronizar(request):
    """Dispara la sincronización manual desde el navegador."""
    from integraciones.reader import leer_carpetas

    if request.user.rol not in ROLES_REPORTES_GESTION:
        messages.error(request, 'No tienes permiso.')
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('reportes_moreapp_list')

    try:
        max_segundos = getattr(settings, 'MOREAPP_WEB_SYNC_MAX_SEGUNDOS', 35)
        max_archivos = getattr(settings, 'MOREAPP_WEB_SYNC_MAX_ARCHIVOS', 60)
        skip_dup = getattr(settings, 'MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS', True)
        stats = leer_carpetas(
            reprocesar_duplicados=not skip_dup,
            max_archivos=max_archivos,
            max_segundos=max_segundos,
        )
    except Exception as exc:
        logger.exception('Sincronización MoreApp falló de forma no controlada')
        messages.error(
            request,
            f'La sincronización falló: {exc}. Revisa el log del servidor e intenta de nuevo.',
        )
        return redirect('reportes_moreapp_list')

    if not isinstance(stats, dict):
        messages.warning(request, 'Sincronización finalizó sin estadísticas.')
        return redirect('reportes_moreapp_list')

    from web.moreapp_ops import registrar_resultado_sync
    registrar_resultado_sync(stats, origen='manual_web')

    detalle = stats.get('detalle', []) or []
    errores_detalle = [d for d in detalle if str(d.get('resultado', '')).lower() == 'error']
    bloqueos_detalle = [
        d for d in detalle
        if 'BLOQUEO_OPERATIVO' in str(d.get('mensaje', ''))
        or 'ALERTA_CRITICA' in str(d.get('mensaje', ''))
        or 'pendientes operativos' in str(d.get('mensaje', '')).lower()
    ]

    messages.success(
        request,
        f'Sincronización completada — Nuevos: {stats.get("nuevos", 0)} | '
        f'Duplicados: {stats.get("duplicados", 0)} | '
        f'Alertas: {stats.get("alertas", 0)} | '
        f'Errores: {stats.get("errores", 0)} | '
        f'Revisados: {stats.get("carpetas_revisadas", 0)}'
    )

    if stats.get('incompleto'):
        messages.warning(
            request,
            'Sincronización parcial por límite de tiempo/archivos del hosting'
            + (f' ({stats.get("motivo_corte")})' if stats.get('motivo_corte') else '')
            + '. Vuelve a pulsar Sincronizar para continuar con el resto.',
        )

    if errores_detalle:
        mensajes_error = '; '.join(str(e.get('mensaje', 'Error sin detalle')) for e in errores_detalle[:3])
        messages.error(
            request,
            f'Se detectaron errores en sincronización MoreApp ({len(errores_detalle)}). {mensajes_error}'
        )

    if bloqueos_detalle:
        mensajes_bloqueo = '; '.join(str(b.get('mensaje', 'Bloqueo operativo')) for b in bloqueos_detalle[:3])
        messages.warning(
            request,
            f'Se detectaron alertas/bloqueos ({len(bloqueos_detalle)}). {mensajes_bloqueo}'
        )

    return redirect('reportes_moreapp_list')


@login_required
@role_required(['ADMIN'])
def reportes_moreapp_eliminar(request, pk):
    """Soft-delete MoreApp: no reaparece en sync; snapshot en movimientos."""
    from ordenes_trabajo.models import IntegracionMoreApp
    from web.services.eliminaciones import ENTIDAD_MOREAPP, registrar_eliminacion
    from web.moreapp_avisos import invalidar_caches_aviso_moreapp

    if request.method != 'POST':
        return redirect('reportes_moreapp_list')

    registro = get_object_or_404(IntegracionMoreApp, pk=pk, eliminado=False)
    identificador = registro.moreapp_submission_id
    motivo = request.POST.get('motivo', '').strip()
    _, creado = registrar_eliminacion(
        ENTIDAD_MOREAPP,
        registro,
        request.user,
        motivo=motivo,
    )
    if creado:
        invalidar_caches_aviso_moreapp()
        messages.success(
            request,
            f'Registro MoreApp {identificador} eliminado. Quedó en Movimientos y no se reimportará.',
        )
    else:
        messages.warning(request, f'El registro MoreApp {identificador} ya estaba eliminado.')

    destino = request.POST.get('next', '').strip()
    if destino:
        return redirect(destino)
    return redirect('reportes_moreapp_list')


@login_required
@role_required(['ADMIN'])
@require_POST
def reportes_moreapp_eliminar_masivo(request):
    """Soft-delete masivo MoreApp + snapshot en movimientos."""
    from ordenes_trabajo.models import IntegracionMoreApp
    from web.services.eliminaciones import ENTIDAD_MOREAPP, registrar_eliminacion
    from web.moreapp_avisos import invalidar_caches_aviso_moreapp

    ids = []
    for raw in request.POST.getlist('ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue

    if not ids:
        messages.warning(request, 'No seleccionaste ningún registro para eliminar.')
        destino = request.POST.get('next', '').strip()
        return redirect(destino or 'reportes_moreapp_list')

    registros = list(IntegracionMoreApp.objects.filter(pk__in=ids, eliminado=False))
    total = 0
    for registro in registros:
        _, creado = registrar_eliminacion(
            ENTIDAD_MOREAPP,
            registro,
            request.user,
            motivo='Eliminación masiva desde reportes MoreApp',
        )
        if creado:
            total += 1

    if total == 0:
        messages.warning(request, 'Los registros seleccionados ya no existen o ya estaban eliminados.')
    else:
        invalidar_caches_aviso_moreapp()
        messages.success(
            request,
            f'Se eliminaron {total} registro(s) MoreApp. Quedaron en Movimientos y no se reimportarán.',
        )

    destino = request.POST.get('next', '').strip()
    if destino:
        return redirect(destino)
    return redirect('reportes_moreapp_list')


def _entity_ids_por_referencia_auditoria(referencia: str):
    """Resuelve correlativo MoreApp, Nº cliente o ID interno a entity_id de auditoría."""
    valor = (referencia or '').strip()
    if not valor:
        return []

    ids = {valor}

    try:
        from ordenes_trabajo.models import IntegracionMoreApp
        if valor.isdigit():
            for pk in IntegracionMoreApp.objects.filter(
                numero_correlativo=int(valor)
            ).values_list('pk', flat=True)[:50]:
                ids.add(str(pk))
    except Exception:
        pass

    try:
        from clientes.models import Cliente
        for pk in Cliente.objects.filter(numero_cliente=valor).values_list('pk', flat=True)[:50]:
            ids.add(str(pk))
    except Exception:
        pass

    return list(ids)


def _enriquecer_referencia_auditoria(registros):
    """Agrega referencia_label legible (corr. MoreApp, Nº cliente, etc.)."""
    from ordenes_trabajo.models import IntegracionMoreApp
    from clientes.models import Cliente

    more_ids = [
        int(r.entity_id)
        for r in registros
        if r.entity == 'IntegracionMoreApp' and str(r.entity_id).isdigit()
    ]
    cliente_ids = [
        int(r.entity_id)
        for r in registros
        if r.entity == 'Cliente' and str(r.entity_id).isdigit()
    ]

    more_map = {}
    if more_ids:
        more_map = {
            str(pk): corr
            for pk, corr in IntegracionMoreApp.objects.filter(pk__in=more_ids).values_list(
                'pk', 'numero_correlativo'
            )
        }
    cliente_map = {}
    if cliente_ids:
        cliente_map = {
            str(pk): num
            for pk, num in Cliente.objects.filter(pk__in=cliente_ids).values_list(
                'pk', 'numero_cliente'
            )
        }

    for reg in registros:
        eid = str(reg.entity_id or '')
        if reg.entity == 'IntegracionMoreApp' and more_map.get(eid) is not None:
            reg.referencia_label = f'Corr. {more_map[eid]}'
        elif reg.entity == 'Cliente' and cliente_map.get(eid):
            reg.referencia_label = f'Nº {cliente_map[eid]}'
        elif reg.entity == 'OrdenTrabajo':
            reg.referencia_label = f'OT #{eid}'
        else:
            reg.referencia_label = f'#{eid}' if eid else '—'
    return registros


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'AUDITOR', 'GERENCIA'])
def auditoria_list_view(request):
    """Historial de auditoría persistente (PDF punto 12)."""
    from web.models import AuditLog
    from web.services.audit_labels import ACCION_LABELS, ENTIDAD_LABELS, label_accion, label_entidad

    entity = request.GET.get('entity', '').strip()
    action = request.GET.get('action', '').strip()
    referencia = (
        request.GET.get('referencia', '').strip()
        or request.GET.get('entity_id', '').strip()
    )

    qs = AuditLog.objects.select_related('actor').order_by('-created_at')
    if entity:
        qs = qs.filter(entity__iexact=entity) if entity in ENTIDAD_LABELS else qs.filter(entity__icontains=entity)
    if action:
        qs = qs.filter(action=action)
    if referencia:
        qs = qs.filter(entity_id__in=_entity_ids_por_referencia_auditoria(referencia))

    acciones_db = list(
        AuditLog.objects.order_by('action').values_list('action', flat=True).distinct()[:80]
    )
    acciones_opciones = []
    vistas = set()
    for codigo in list(ACCION_LABELS.keys()) + acciones_db:
        if not codigo or codigo in vistas:
            continue
        vistas.add(codigo)
        acciones_opciones.append({'codigo': codigo, 'label': label_accion(codigo)})
    acciones_opciones.sort(key=lambda item: item['label'].casefold())

    entidades_db = list(
        AuditLog.objects.order_by('entity').values_list('entity', flat=True).distinct()[:80]
    )
    entidades_opciones = []
    vistas_ent = set()
    for codigo in list(ENTIDAD_LABELS.keys()) + entidades_db:
        if not codigo or codigo in vistas_ent:
            continue
        vistas_ent.add(codigo)
        entidades_opciones.append({'codigo': codigo, 'label': label_entidad(codigo)})
    entidades_opciones.sort(key=lambda item: item['label'].casefold())

    registros = _enriquecer_referencia_auditoria(list(qs[:500]))

    return render(request, 'auditoria/list.html', {
        'registros': registros,
        'entity': entity,
        'action': action,
        'referencia': referencia,
        'total': qs.count(),
        'acciones_opciones': acciones_opciones,
        'entidades_opciones': entidades_opciones,
    })