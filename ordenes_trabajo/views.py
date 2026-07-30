from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Count
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from io import BytesIO
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
import json

from .models import (
    OrdenTrabajo,
    AdjuntoOrden,
    IntegracionMoreApp,
    InformeCliente,
    ValidacionComunicacionOT,
)
from .serializers import OrdenTrabajoSerializer
from .services import validate_ot_for_creation
from .utils import (
    importar_ordenes_excel,
    exportar_ordenes_excel,
    asignar_ordenes_masivo,
    aplicar_alerta_duplicado,
    crear_orden_derivada_por_observacion,
    guardar_informe_pdf,
    detectar_duplicado_orden,
    aplicar_cola_ordenes,
    contadores_colas_ordenes,
    paso_operativo_ot,
    COLAS_ORDEN,
    ESTADOS_TERMINADOS,
    ESTADOS_TERMINADOS_LABELS,
)
from usuarios.models import Usuario
from clientes.models import Cliente
from inventario.models import Medidor, SimCard, Modem
from web.decorators import admin_only
from web.services.audit import AuditEvent, register_audit_event


def puede_editar_observaciones_orden(orden, usuario):
    """Admin/administrativo o técnico responsable pueden editar observaciones."""
    if usuario.rol in ['ADMIN', 'ADMINISTRATIVO']:
        return True
    if usuario.rol == 'TECNICO' and orden.tecnico_responsable == usuario:
        return True
    return False


def _queryset_ordenes_filtrado(request, aplicar_filtros=True):
    """Queryset de órdenes según rol y filtros GET (listado y exportación)."""
    usuario = request.user

    if usuario.rol in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
        ordenes = OrdenTrabajo.objects.filter(eliminado=False)
    elif usuario.rol == 'TECNICO':
        ordenes = OrdenTrabajo.objects.filter(tecnico_responsable=usuario, eliminado=False)
    else:
        ordenes = OrdenTrabajo.objects.none()

    if aplicar_filtros:
        estado_filtro = request.GET.get('estado', '')
        tipo_filtro = request.GET.get('tipo_trabajo', '')
        tecnico_filtro = request.GET.get('tecnico', '')
        cliente_filtro = request.GET.get('cliente', '')
        buscar = request.GET.get('buscar', '')
        cola = request.GET.get('cola', '')

        if estado_filtro:
            ordenes = ordenes.filter(estado=estado_filtro)
        if tipo_filtro:
            ordenes = ordenes.filter(tipo_trabajo=tipo_filtro)
        if tecnico_filtro:
            ordenes = ordenes.filter(tecnico_responsable_id=tecnico_filtro)
        if cliente_filtro:
            if str(cliente_filtro).isdigit():
                ordenes = ordenes.filter(cliente_id=int(cliente_filtro))
            else:
                ordenes = ordenes.filter(cliente__numero_cliente__icontains=cliente_filtro)
        if buscar:
            ordenes = ordenes.filter(
                Q(titulo__icontains=buscar)
                | Q(descripcion__icontains=buscar)
                | Q(cliente__numero_cliente__icontains=buscar)
            )
        if cola:
            ordenes = aplicar_cola_ordenes(ordenes, cola)

        alarma = (request.GET.get('alarma') or '').strip().lower()
        if alarma == 'ot_sin_responder':
            from reportes.services import ESTADOS_PENDIENTES_OT
            ordenes = ordenes.filter(estado__in=ESTADOS_PENDIENTES_OT)

    return ordenes.select_related(
        'tecnico_responsable',
        'cliente',
        'medidor',
        'simcard',
        'modem',
        'creada_por',
    ).annotate(
        moreapp_count=Count('sincronizaciones_moreapp', distinct=True),
    ).order_by('id')


@login_required
def ordenes_list_view(request):
    """
    Lista de órdenes de trabajo con filtros y paginación servidor.
    """
    from django.core.paginator import Paginator

    usuario = request.user
    base_ordenes = _queryset_ordenes_filtrado(request, aplicar_filtros=False)
    ordenes_qs = _queryset_ordenes_filtrado(request)

    estado_filtro = request.GET.get('estado', '')
    tipo_filtro = request.GET.get('tipo_trabajo', '')
    tecnico_filtro = request.GET.get('tecnico', '')
    cliente_filtro = request.GET.get('cliente', '')
    buscar = request.GET.get('buscar', '')
    cola_filtro = request.GET.get('cola', '')
    alarma_filtro = (request.GET.get('alarma') or '').strip().lower()

    try:
        per_page = int(request.GET.get('per_page') or 50)
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in (25, 50, 100):
        per_page = 50

    total_alertas_duplicado = ordenes_qs.filter(alerta_duplicado=True).count()
    # Forzar ID asc aquí: anotar/colas no deben perder el orden visible.
    ordenes_qs = ordenes_qs.order_by('id')
    page_obj = Paginator(ordenes_qs, per_page).get_page(request.GET.get('page') or 1)

    tecnicos = Usuario.objects.filter(rol='TECNICO', is_active=True).order_by('nombre_interno')
    # Solo clientes con OT (cap) — no cargar todo el padrón en el filtro
    clientes = Cliente.objects.filter(
        pk__in=OrdenTrabajo.objects.exclude(cliente_id=None).values('cliente_id')
    ).order_by('numero_cliente')[:500]

    cliente_filtro_label = ''
    tecnico_filtro_label = ''
    if cliente_filtro:
        if str(cliente_filtro).isdigit():
            c = Cliente.objects.filter(pk=int(cliente_filtro)).first()
            if c:
                cliente_filtro_label = f'{c.numero_cliente}' + (f' · {c.customer_name}' if c.customer_name else '')
        else:
            cliente_filtro_label = str(cliente_filtro)
    if tecnico_filtro and str(tecnico_filtro).isdigit():
        t = Usuario.objects.filter(pk=int(tecnico_filtro)).first()
        if t:
            tecnico_filtro_label = t.nombre_interno or str(t.pk)

    query_params = request.GET.copy()
    query_params.pop('page', None)

    context = {
        'ordenes': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_params.urlencode(),
        'per_page': per_page,
        'tecnicos': tecnicos,
        'clientes': clientes,
        'estados': OrdenTrabajo.ESTADO_CHOICES,
        'tipos_trabajo': OrdenTrabajo.TIPO_TRABAJO_CHOICES,
        'estado_filtro': estado_filtro,
        'tipo_filtro': tipo_filtro,
        'tecnico_filtro': tecnico_filtro,
        'cliente_filtro': cliente_filtro,
        'cliente_filtro_label': cliente_filtro_label,
        'tecnico_filtro_label': tecnico_filtro_label,
        'buscar': buscar,
        'cola_filtro': cola_filtro,
        'alarma': alarma_filtro,
        'alarma_label': 'OT sin responder' if alarma_filtro == 'ot_sin_responder' else '',
        'colas_orden': COLAS_ORDEN,
        'colas_conteo': contadores_colas_ordenes(base_ordenes),
        'total_alertas_duplicado': total_alertas_duplicado,
        'puede_eliminar': usuario.rol == 'ADMIN',
        'paginacion_servidor': True,
    }

    return render(request, 'ordenes/list.html', context)


@login_required
def ordenes_terminadas_view(request):
    """
    Vista de consulta de trabajos terminados (realizadas / validadas / finalizadas)
    con filtros y resumen para seguimiento administrativo.
    """
    from datetime import datetime, timedelta
    from django.core.paginator import Paginator
    from django.db.models import Count

    usuario = request.user
    if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR', 'TECNICO']:
        messages.error(request, 'No tienes acceso a trabajos terminados')
        return redirect('dashboard')

    base = _queryset_ordenes_filtrado(request, aplicar_filtros=False).filter(
        estado__in=ESTADOS_TERMINADOS,
    )

    estado_filtro = (request.GET.get('estado') or '').strip()
    tipo_filtro = (request.GET.get('tipo_trabajo') or '').strip()
    tecnico_filtro = (request.GET.get('tecnico') or '').strip()
    cliente_filtro = (request.GET.get('cliente') or '').strip()
    buscar = (request.GET.get('buscar') or '').strip()
    fecha_desde = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta = (request.GET.get('fecha_hasta') or '').strip()
    periodo = (request.GET.get('periodo') or '').strip().lower()

    qs = base
    if estado_filtro and estado_filtro in ESTADOS_TERMINADOS:
        qs = qs.filter(estado=estado_filtro)
    if tipo_filtro:
        qs = qs.filter(tipo_trabajo=tipo_filtro)
    if tecnico_filtro and tecnico_filtro.isdigit():
        qs = qs.filter(tecnico_responsable_id=int(tecnico_filtro))
    if cliente_filtro:
        if cliente_filtro.isdigit():
            qs = qs.filter(cliente_id=int(cliente_filtro))
        else:
            qs = qs.filter(cliente__numero_cliente__icontains=cliente_filtro)
    if buscar:
        qs = qs.filter(
            Q(titulo__icontains=buscar)
            | Q(descripcion__icontains=buscar)
            | Q(cliente__numero_cliente__icontains=buscar)
            | Q(cliente__customer_name__icontains=buscar)
        )

    ahora = timezone.now()
    if periodo == '7':
        qs = qs.filter(
            Q(fecha_fin_ejecucion__gte=ahora - timedelta(days=7))
            | Q(fecha_fin_ejecucion__isnull=True, fecha_creacion__gte=ahora - timedelta(days=7))
        )
    elif periodo == '30':
        qs = qs.filter(
            Q(fecha_fin_ejecucion__gte=ahora - timedelta(days=30))
            | Q(fecha_fin_ejecucion__isnull=True, fecha_creacion__gte=ahora - timedelta(days=30))
        )
    else:
        if fecha_desde:
            try:
                d0 = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
                qs = qs.filter(
                    Q(fecha_fin_ejecucion__date__gte=d0)
                    | Q(fecha_fin_ejecucion__isnull=True, fecha_creacion__date__gte=d0)
                )
            except ValueError:
                fecha_desde = ''
        if fecha_hasta:
            try:
                d1 = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
                qs = qs.filter(
                    Q(fecha_fin_ejecucion__date__lte=d1)
                    | Q(fecha_fin_ejecucion__isnull=True, fecha_creacion__date__lte=d1)
                )
            except ValueError:
                fecha_hasta = ''

    qs = qs.select_related(
        'tecnico_responsable', 'cliente', 'validada_por', 'creada_por',
    ).annotate(
        moreapp_count=Count('sincronizaciones_moreapp', distinct=True),
        informes_count=Count('informes', distinct=True),
        adjuntos_count=Count('adjuntos', distinct=True),
    ).order_by('-fecha_fin_ejecucion', '-id')

    total = qs.count()
    resumen_estado = {
        row['estado']: row['n']
        for row in qs.values('estado').annotate(n=Count('id'))
    }
    por_tecnico = list(
        qs.exclude(tecnico_responsable__isnull=True)
        .values('tecnico_responsable__nombre_interno')
        .annotate(n=Count('id'))
        .order_by('-n')[:8]
    )
    por_tipo = list(
        qs.values('tipo_trabajo').annotate(n=Count('id')).order_by('-n')
    )
    con_moreapp = qs.filter(moreapp_count__gt=0).count()
    con_informe_pdf = qs.filter(informes_count__gt=0).count()
    con_adjuntos = qs.filter(adjuntos_count__gt=0).count()

    try:
        per_page = int(request.GET.get('per_page') or 50)
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in (25, 50, 100):
        per_page = 50

    page_obj = Paginator(qs, per_page).get_page(request.GET.get('page') or 1)

    tecnicos = Usuario.objects.filter(rol='TECNICO', is_active=True).order_by('nombre_interno')
    tecnico_filtro_label = ''
    if tecnico_filtro and tecnico_filtro.isdigit():
        t = Usuario.objects.filter(pk=int(tecnico_filtro)).first()
        if t:
            tecnico_filtro_label = t.nombre_interno or str(t.pk)

    cliente_filtro_label = ''
    if cliente_filtro:
        if cliente_filtro.isdigit():
            c = Cliente.objects.filter(pk=int(cliente_filtro)).first()
            if c:
                cliente_filtro_label = f'{c.numero_cliente}' + (
                    f' · {c.customer_name}' if c.customer_name else ''
                )
        else:
            cliente_filtro_label = cliente_filtro

    query_params = request.GET.copy()
    query_params.pop('page', None)

    tipo_labels = dict(OrdenTrabajo.TIPO_TRABAJO_CHOICES)
    por_tipo_display = [
        {'label': tipo_labels.get(row['tipo_trabajo'], row['tipo_trabajo']), 'n': row['n']}
        for row in por_tipo
    ]

    context = {
        'ordenes': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_params.urlencode(),
        'per_page': per_page,
        'tecnicos': tecnicos,
        'tipos_trabajo': OrdenTrabajo.TIPO_TRABAJO_CHOICES,
        'estados_terminados': ESTADOS_TERMINADOS_LABELS,
        'estado_filtro': estado_filtro,
        'tipo_filtro': tipo_filtro,
        'tecnico_filtro': tecnico_filtro,
        'tecnico_filtro_label': tecnico_filtro_label,
        'cliente_filtro': cliente_filtro,
        'cliente_filtro_label': cliente_filtro_label,
        'buscar': buscar,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'periodo': periodo,
        'resumen': {
            'total': total,
            'finalizadas': resumen_estado.get('FINALIZADA', 0),
            'validadas': resumen_estado.get('VALIDADA', 0),
            'realizadas': resumen_estado.get('REALIZADA', 0),
            'con_moreapp': con_moreapp,
            'con_informe_pdf': con_informe_pdf,
            'con_adjuntos': con_adjuntos,
            'por_tecnico': por_tecnico,
            'por_tipo': por_tipo_display,
        },
    }
    return render(request, 'ordenes/terminadas.html', context)


@login_required
def orden_crear_view(request):
    """
    Crear nueva orden de trabajo
    """
    if request.user.rol not in ['ADMIN', 'ADMINISTRATIVO']:
        messages.error(request, 'No tienes permisos para crear órdenes')
        return redirect('ordenes_list')
    
    if request.method == 'POST':
        try:
            # Crear orden
            orden = OrdenTrabajo()
            orden.titulo = request.POST.get('titulo')
            orden.descripcion = request.POST.get('descripcion', '')
            orden.tipo_trabajo = request.POST.get('tipo_trabajo')
            
            # Cliente
            cliente_id = request.POST.get('cliente')
            cliente = None
            if cliente_id:
                cliente = Cliente.objects.get(id=cliente_id)
                orden.cliente = cliente

            ot_validation = validate_ot_for_creation(
                cliente,
                request.POST.get('tipo_trabajo'),
            )
            if ot_validation.has_blocking_error:
                for error in ot_validation.errors:
                    messages.error(request, error)
                return redirect('orden_crear')

            orden.observaciones_tecnicas = request.POST.get('observaciones_tecnicas', '')
            
            # Técnico responsable (opcional — sin técnico queda CREADA)
            tecnico_id = request.POST.get('tecnico_responsable', '').strip()
            if tecnico_id:
                orden.tecnico_responsable = Usuario.objects.get(id=tecnico_id)
                orden.estado = 'ASIGNADA'
                orden.fecha_asignacion = timezone.now()
            else:
                orden.estado = 'CREADA'
            
            orden.creada_por = request.user
            orden.save()
            register_audit_event(
                AuditEvent(
                    actor_id=getattr(request.user, 'id', None),
                    action='OT_CREATE',
                    entity='OrdenTrabajo',
                    entity_id=str(orden.pk),
                    field_name='estado',
                    old_value=None,
                    new_value=orden.estado,
                    reason='Creación de orden de trabajo',
                )
            )
            aplicar_alerta_duplicado(orden)

            for warning in ot_validation.warnings:
                messages.warning(request, warning)

            if orden.alerta_duplicado:
                messages.warning(request, f'Alerta: posible trabajo duplicado — {orden.descripcion_alerta_duplicado}')

            if orden.estado == 'ASIGNADA':
                messages.success(request, f'Orden #{orden.id} creada y asignada a {orden.tecnico_responsable.nombre_interno}')
            else:
                messages.success(request, f'Orden #{orden.id} creada. Asigna un responsable cuando esté listo.')
            return redirect('orden_detalle', pk=orden.id)
            
        except Exception as e:
            messages.error(request, f'Error al crear orden: {str(e)}')
    
    # GET - Mostrar formulario (tope: evita renderizar miles de clientes en el select)
    tecnicos = Usuario.objects.filter(rol='TECNICO', is_active=True).order_by('nombre_interno')
    clientes = Cliente.objects.filter(activo=True).exclude(numero_cliente='0').order_by('numero_cliente')[:500]
    
    context = {
        'tecnicos': tecnicos,
        'clientes': clientes,
        'tipos_trabajo': OrdenTrabajo.TIPO_TRABAJO_CHOICES,
    }
    
    return render(request, 'ordenes/crear.html', context)


@login_required
def orden_detalle_view(request, pk):
    """
    Detalle de una orden de trabajo con toda la información
    """
    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
    
    # Verificar permisos
    usuario = request.user
    if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
        if usuario.rol == 'TECNICO' and orden.tecnico_responsable != usuario:
            messages.error(request, 'No tienes acceso a esta orden')
            return redirect('ordenes_list')

    if request.method == 'POST' and request.POST.get('accion') == 'guardar_observaciones':
        if puede_editar_observaciones_orden(orden, usuario):
            orden.observaciones_tecnicas = request.POST.get('observaciones_tecnicas', '').strip()
            orden.save(update_fields=['observaciones_tecnicas'])
            messages.success(request, 'Observaciones técnicas guardadas')
        else:
            messages.error(request, 'No tienes permiso para editar las observaciones técnicas')
        return redirect('orden_detalle', pk=pk)

    if request.method == 'POST' and request.POST.get('accion') == 'reasignar_tecnico':
        if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO']:
            messages.error(request, 'No tienes permiso para reasignar el técnico')
            return redirect('orden_detalle', pk=pk)
        if orden.eliminado:
            messages.error(request, 'No se puede reasignar una orden eliminada')
            return redirect('ordenes_list')

        tecnico_id = request.POST.get('tecnico_responsable', '').strip()
        motivo_reasignacion = request.POST.get('motivo_reasignacion', '').strip()
        if not tecnico_id:
            messages.error(request, 'Debes seleccionar un técnico')
            return redirect('orden_detalle', pk=pk)
        if not motivo_reasignacion:
            messages.error(request, 'Debes indicar un comentario al reasignar la orden.')
            return redirect('orden_detalle', pk=pk)

        try:
            nuevo_tecnico = Usuario.objects.get(pk=int(tecnico_id), rol='TECNICO', is_active=True)
        except (Usuario.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Técnico no válido')
            return redirect('orden_detalle', pk=pk)

        tecnico_anterior = orden.tecnico_responsable
        tecnico_anterior_id = getattr(tecnico_anterior, 'id', None)
        estado_anterior_ot = orden.estado
        if tecnico_anterior_id is not None:
            if tecnico_anterior_id == nuevo_tecnico.id and orden.estado == 'REASIGNADA':
                messages.info(request, 'El técnico ya está asignado a esta orden')
                return redirect('orden_detalle', pk=pk)

        orden.tecnico_responsable = nuevo_tecnico
        orden.estado = 'REASIGNADA'
        orden.tecnico_solicito_reasignacion = False
        orden.motivo_reasignacion = motivo_reasignacion
        if not orden.fecha_asignacion:
            orden.fecha_asignacion = timezone.now()
        orden.save(update_fields=[
            'tecnico_responsable',
            'estado',
            'tecnico_solicito_reasignacion',
            'motivo_reasignacion',
            'fecha_asignacion',
        ])

        anterior_txt = (
            tecnico_anterior.nombre_interno if tecnico_anterior else 'sin asignar'
        )
        from ordenes_trabajo.models import RegistroValidacionOT
        RegistroValidacionOT.objects.create(
            orden=orden,
            accion='REASIGNADA',
            realizado_por=usuario,
            comentario=motivo_reasignacion,
            estado_anterior=estado_anterior_ot,
            estado_nuevo='REASIGNADA',
            detalle_extra=f'{anterior_txt} → {nuevo_tecnico.nombre_interno}',
        )
        register_audit_event(
            AuditEvent(
                actor_id=getattr(usuario, 'id', None),
                action='OT_REASSIGN_TECH',
                entity='OrdenTrabajo',
                entity_id=str(orden.pk),
                field_name='tecnico_responsable',
                old_value=str(getattr(tecnico_anterior, 'id', '') or ''),
                new_value=str(nuevo_tecnico.id),
                reason=(
                    f'Reasignación de {anterior_txt} a {nuevo_tecnico.nombre_interno} '
                    f'por {usuario.nombre_interno}: {motivo_reasignacion}'
                ),
            )
        )
        messages.success(
            request,
            f'Técnico reasignado a {nuevo_tecnico.nombre_interno}. Estado: Reasignada.',
        )
        return redirect('orden_detalle', pk=pk)
    
    # Obtener adjuntos e informes
    adjuntos = orden.adjuntos.all()
    informes = orden.informes.all()
    
    # Obtener integraciones MoreApp
    sincronizaciones = orden.sincronizaciones_moreapp.filter(eliminado=False).order_by('-fecha_recepcion')
    moreapp_count = sincronizaciones.count()
    sync_advertencia = sincronizaciones.filter(estado_revision='CON_ADVERTENCIA').exists()
    paso_operativo = paso_operativo_ot(orden, moreapp_count=moreapp_count, sync_advertencia=sync_advertencia)
    if paso_operativo.get('accion_label') == 'Revisar pendientes':
        paso_operativo['accion_url'] = '/operacional/pendientes/?estado=CON_ADVERTENCIA'
    elif paso_operativo.get('accion_label') == 'Ver informes MoreApp':
        paso_operativo['accion_url'] = '/reportes/moreapp/'

    estados_revision = ('PENDIENTE_VALIDACION', 'REALIZADA_PENDIENTE_COMPROBACION')
    puede_validar = usuario.rol in ['ADMIN', 'ADMINISTRATIVO'] and orden.estado in estados_revision
    puede_observar = usuario.rol == 'AUDITOR' and orden.estado in estados_revision
    puede_reasignar = usuario.rol in ['ADMIN', 'ADMINISTRATIVO'] and not orden.eliminado

    historial_ordenes_cliente = OrdenTrabajo.objects.none()
    if orden.cliente_id:
        historial_ordenes_cliente = (
            OrdenTrabajo.objects.filter(cliente_id=orden.cliente_id, eliminado=False)
            .exclude(pk=orden.pk)
            .select_related('tecnico_responsable')
            .order_by('-fecha_creacion')[:30]
        )

    tecnicos = Usuario.objects.filter(rol='TECNICO', is_active=True).order_by('nombre_interno')
    registros_validacion = (
        orden.registros_validacion.select_related('realizado_por').order_by('-fecha')[:50]
    )
    validaciones_comunicacion = (
        orden.validaciones_comunicacion
        .select_related('solicitado_por', 'validado_por')
        .order_by('-fecha_solicitud')[:50]
    )
    tiene_comunicacion_pendiente = orden.validaciones_comunicacion.filter(
        estado='SOLICITADA'
    ).exists()
    puede_solicitar_comunicacion = (
        orden.estado != 'CANCELADA'
        and (
            usuario.rol in ['ADMIN', 'ADMINISTRATIVO']
            or orden.tecnico_responsable_id == usuario.id
        )
    )
    puede_registrar_comunicacion = (
        usuario.rol in ['ADMIN', 'ADMINISTRATIVO'] and orden.estado != 'CANCELADA'
    )

    context = {
        'orden': orden,
        'adjuntos': adjuntos,
        'informes': informes,
        'sincronizaciones': sincronizaciones,
        'paso_operativo': paso_operativo,
        'historial_ordenes_cliente': historial_ordenes_cliente,
        'registros_validacion': registros_validacion,
        'validaciones_comunicacion': validaciones_comunicacion,
        'tiene_comunicacion_pendiente': tiene_comunicacion_pendiente,
        'puede_solicitar_comunicacion': puede_solicitar_comunicacion,
        'puede_registrar_comunicacion': puede_registrar_comunicacion,
        'puede_editar': usuario.rol in ['ADMIN', 'ADMINISTRATIVO'],
        'puede_reasignar': puede_reasignar,
        'tecnicos': tecnicos,
        'puede_validar': puede_validar,
        'puede_observar': puede_observar,
        'puede_finalizar': usuario.rol in ['ADMIN', 'ADMINISTRATIVO'] and orden.estado == 'VALIDADA',
        'ordenes_derivadas': orden.ordenes_derivadas.filter(eliminado=False).order_by('-fecha_creacion'),
        'puede_eliminar': usuario.rol == 'ADMIN' and not orden.eliminado,
        'es_tecnico_responsable': orden.tecnico_responsable == usuario if orden.tecnico_responsable else False,
        'puede_editar_observaciones': puede_editar_observaciones_orden(orden, usuario),
        'puede_subir_respaldo_moreapp': (
            usuario.rol in ['ADMIN', 'ADMINISTRATIVO']
            or (orden.tecnico_responsable_id == usuario.id)
        ) and orden.estado != 'CANCELADA',
        'tiene_informe_moreapp_sync': informes.filter(origen='MOREAPP').exists(),
        'tiene_respaldo_moreapp': informes.filter(origen='RESPALDO_MOREAPP').exists(),
        'sin_evidencia_moreapp': (
            not sincronizaciones.exists()
            and not informes.filter(origen__in=['MOREAPP', 'RESPALDO_MOREAPP']).exists()
        ),
    }

    # Volver: si viene de trabajos terminados (o la OT ya está cerrada), regresar ahí
    desde = (request.GET.get('desde') or '').strip().lower()
    if desde == 'terminadas' or orden.estado in ESTADOS_TERMINADOS:
        from django.urls import reverse
        context['volver_url'] = reverse('ordenes_terminadas')
        context['volver_label'] = 'Volver a trabajos terminados'
    else:
        from django.urls import reverse
        context['volver_url'] = reverse('ordenes_list')
        context['volver_label'] = 'Volver'
    
    return render(request, 'ordenes/detalle.html', context)


@login_required
def orden_guardar_observaciones_view(request, pk):
    """Guarda observaciones técnicas (admin, administrativo o técnico responsable)."""
    if request.method != 'POST':
        return redirect('orden_detalle', pk=pk)

    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)

    if not puede_editar_observaciones_orden(orden, request.user):
        messages.error(request, 'No tienes permiso para editar las observaciones técnicas')
        return redirect('orden_detalle', pk=pk)

    orden.observaciones_tecnicas = request.POST.get('observaciones_tecnicas', '').strip()
    orden.save(update_fields=['observaciones_tecnicas'])
    messages.success(request, 'Observaciones técnicas guardadas')
    return redirect('orden_detalle', pk=pk)


@login_required
def cambiar_estado_orden_view(request, pk):
    """
    Cambia el estado de una orden validando permisos por rol.
    """
    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
    nuevo_estado = request.POST.get('nuevo_estado')
    observacion = request.POST.get('observacion_validacion', '').strip()

    if not orden.puede_cambiar_estado(request.user, nuevo_estado):
        messages.error(request, 'No tienes permiso para cambiar este estado')
        return redirect('orden_detalle', pk=pk)

    if nuevo_estado == 'OBSERVADA' and not observacion:
        messages.error(request, 'Debe indicar el motivo de la observación antes de rechazar.')
        return redirect('orden_detalle', pk=pk)

    # La validación/rechazo siempre queda a nombre del usuario autenticado.
    resultado = orden.cambiar_estado(request.user, nuevo_estado, razon=observacion)

    if resultado['success']:
        sync_info = resultado.get('sync_inventario') or {}
        if sync_info.get('sci4_alerta') and orden.cliente_id:
            messages.warning(
                request,
                'Cliente marcado como Pendiente SCi4: hay que actualizar la base comercial '
                f'con los equipos de la OT #{orden.pk}.',
            )
        if nuevo_estado == 'VALIDADA':
            messages.success(
                request,
                f'Orden validada por {request.user.nombre_interno}. '
                'Use Acciones → Finalizada para cerrar el trabajo en la plataforma.',
            )
        elif nuevo_estado == 'OBSERVADA':
            nueva = crear_orden_derivada_por_observacion(orden, request.user, observacion)
            messages.warning(
                request,
                f'Orden observada. Se creó la OT derivada #{nueva.pk} para reintento en terreno.',
            )
            return redirect('orden_detalle', pk=nueva.pk)
        else:
            messages.success(request, resultado['mensaje'])
    else:
        messages.error(request, resultado['mensaje'])

    return redirect('orden_detalle', pk=pk)


@login_required
def orden_editar_tecnico_view(request, pk):
    """
    Permite al técnico editar orden (máximo 2 veces)
    """
    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
    
    # Validar que es el técnico responsable
    if orden.tecnico_responsable != request.user:
        messages.error(request, 'No eres responsable de esta orden')
        return redirect('orden_detalle', pk=pk)
    
    # Validar ediciones permitidas
    puede_editar, razon = orden.puede_tecnico_editar(request.user)
    if not puede_editar:
        messages.error(request, razon)
        return redirect('orden_detalle', pk=pk)
    
    if request.method == 'POST':
        try:
            # Actualizar observaciones
            orden.observaciones_tecnicas = request.POST.get('observaciones_tecnicas', '')
            
            # Actualizar campos de medidor/simcard/modem si se proporciona
            medidor_id = request.POST.get('medidor_id', '').strip()
            simcard_id = request.POST.get('simcard_id', '').strip()
            modem_id = request.POST.get('modem_id', '').strip()
            
            if medidor_id:
                from inventario.models import Medidor
                try:
                    orden.medidor_id = int(medidor_id)
                except (ValueError, Medidor.DoesNotExist):
                    pass
            
            if simcard_id:
                from inventario.models import SimCard
                try:
                    orden.simcard_id = int(simcard_id)
                except (ValueError, SimCard.DoesNotExist):
                    pass
            
            if modem_id:
                from inventario.models import Modem
                try:
                    orden.modem_id = int(modem_id)
                except (ValueError, Modem.DoesNotExist):
                    pass
            
            orden.incrementar_ediciones_tecnico()
            messages.success(request, f'Orden actualizada. Ediciones restantes: {2 - orden.ediciones_tecnico}')
            
        except Exception as e:
            messages.error(request, f'Error al actualizar orden: {str(e)}')
    
    return redirect('orden_detalle', pk=pk)


@login_required
def orden_subir_adjunto_view(request, pk):
    """
    Subir adjunto (foto, PDF) a una orden
    """
    if request.method == 'POST':
        orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
        
        # Verificar permisos
        if request.user.rol not in ['ADMIN', 'ADMINISTRATIVO'] and orden.tecnico_responsable != request.user:
            return JsonResponse({'success': False, 'message': 'No tienes permisos'}, status=403)
        
        try:
            archivo = request.FILES.get('archivo')
            tipo = request.POST.get('tipo', 'OTRO')

            if not archivo:
                return JsonResponse({'success': False, 'message': 'No se envió archivo'}, status=400)

            nombre = (archivo.name or '').strip()
            ext = nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''
            # Si suben imagen, forzar tipo FOTO para que se previsualice
            if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}:
                tipo = 'FOTO'
            elif ext == 'pdf' and tipo not in ('PDF', 'FPT'):
                tipo = 'PDF'

            tipos_ok = {c[0] for c in AdjuntoOrden.TIPO_CHOICES}
            if tipo not in tipos_ok:
                tipo = 'OTRO'

            adjunto = AdjuntoOrden()
            adjunto.orden = orden
            adjunto.tipo = tipo
            adjunto.nombre_archivo = nombre or archivo.name
            adjunto.archivo = archivo
            adjunto.subido_por = request.user
            adjunto.save()

            return JsonResponse({
                'success': True,
                'message': 'Archivo subido exitosamente',
                'adjunto_id': adjunto.id,
                'tipo': adjunto.tipo,
                'es_imagen': adjunto.es_imagen,
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)


@login_required
def orden_registrar_equipos_view(request, pk):
    """
    Permite al técnico registrar los equipos que utilizó en el trabajo
    """
    if request.method == 'POST':
        orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
        
        # Verificar que sea el técnico responsable
        if orden.tecnico_responsable != request.user:
            messages.error(request, 'Solo el técnico responsable puede registrar equipos')
            return redirect('orden_detalle', pk=pk)
        
        # Verificar que la orden esté en ejecución o finalizada
        if orden.estado not in ['EN_EJECUCION', 'FINALIZADA']:
            messages.error(request, 'La orden debe estar en ejecución o finalizada para registrar equipos')
            return redirect('orden_detalle', pk=pk)
        
        try:
            # Registrar medidor (primero intenta por ID si viene del autocomplete, luego por serie)
            medidor_id = request.POST.get('medidor_id', '').strip()
            medidor_serie = request.POST.get('medidor_serie', '').strip()
            
            if medidor_id:
                # Si viene del autocomplete, usar ID
                try:
                    medidor = Medidor.objects.get(id=int(medidor_id))
                    # Verificar que el medidor esté en custodia del técnico
                    if medidor.en_custodia_de == request.user or request.user.rol in ['ADMIN', 'ADMINISTRATIVO']:
                        orden.medidor = medidor
                        messages.success(request, f'✓ Medidor {medidor.serie} registrado correctamente')
                    else:
                        messages.warning(request, f'⚠ El medidor {medidor.serie} no está en tu custodia')
                except (Medidor.DoesNotExist, ValueError):
                    messages.warning(request, 'Medidor no encontrado')
            elif medidor_serie:
                # Si no viene ID pero viene serie (compatibilidad con entrada manual)
                try:
                    medidor = Medidor.objects.get(serie=medidor_serie)
                    # Verificar que el medidor esté en custodia del técnico
                    if medidor.en_custodia_de == request.user or request.user.rol in ['ADMIN', 'ADMINISTRATIVO']:
                        orden.medidor = medidor
                    else:
                        messages.warning(request, f'⚠ El medidor {medidor_serie} no está en tu custodia')
                except Medidor.DoesNotExist:
                    messages.warning(request, f'⚠ Medidor {medidor_serie} no encontrado')
            else:
                orden.medidor = None
            
            # Registrar SIM Card
            simcard_imei = request.POST.get('simcard_imei', '').strip()
            if simcard_imei:
                try:
                    simcard = SimCard.objects.get(imei=simcard_imei)
                    # Verificar que la SIM esté en custodia del técnico
                    if simcard.en_custodia_de == request.user or request.user.rol in ['ADMIN', 'ADMINISTRATIVO']:
                        orden.simcard = simcard
                        messages.success(request, f'✓ SIM Card {simcard_imei} registrada correctamente')
                    else:
                        messages.warning(request, f'⚠ La SIM {simcard_imei} no está en tu custodia')
                except SimCard.DoesNotExist:
                    messages.warning(request, f'⚠ SIM Card {simcard_imei} no encontrada')
            else:
                orden.simcard = None
            
            # Registrar Módem
            modem_serie = request.POST.get('modem_serie', '').strip()
            if modem_serie:
                try:
                    modem = Modem.objects.get(serie=modem_serie)
                    # Verificar que el módem esté en custodia del técnico
                    if modem.en_custodia_de == request.user or request.user.rol in ['ADMIN', 'ADMINISTRATIVO']:
                        orden.modem = modem
                        messages.success(request, f'✓ Módem {modem_serie} registrado correctamente')
                    else:
                        messages.warning(request, f'⚠ El módem {modem_serie} no está en tu custodia')
                except Modem.DoesNotExist:
                    messages.warning(request, f'⚠ Módem {modem_serie} no encontrado')
            else:
                orden.modem = None
            
            orden.save()

            from ordenes_trabajo.sync import sincronizar_orden_completa
            if orden.estado in {'REALIZADA', 'REALIZADA_PENDIENTE_COMPROBACION', 'VALIDADA', 'FINALIZADA'}:
                sincronizar_orden_completa(orden, request.user, orden.estado)

            messages.success(request, '✓ Equipos registrados correctamente en la orden')
            
        except Exception as e:
            messages.error(request, f'❌ Error al registrar equipos: {str(e)}')
        
        return redirect('orden_detalle', pk=pk)
    
    return redirect('orden_detalle', pk=pk)


def _requiere_admin_ordenes(view_func):
    """Solo ADMIN o ADMINISTRATIVO pueden gestionar órdenes masivamente."""
    def wrapper(request, *args, **kwargs):
        if request.user.rol not in ['ADMIN', 'ADMINISTRATIVO']:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                return JsonResponse({'success': False, 'message': 'Sin permisos'}, status=403)
            messages.error(request, 'No tienes permisos para esta acción')
            return redirect('ordenes_list')
        return view_func(request, *args, **kwargs)
    return login_required(wrapper)


@_requiere_admin_ordenes
@require_POST
def ordenes_importar_view(request):
    """Importación masiva de órdenes desde Excel."""
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'success': False, 'message': 'No se seleccionó ningún archivo'})

    try:
        importacion = importar_ordenes_excel(archivo, request.user)
        errores_resumen = []
        if importacion.fallidas > 0:
            from collections import Counter
            errores = importacion.errores.all()[:100]
            for motivo, count in Counter(e.motivo for e in errores).most_common(5):
                errores_resumen.append({'motivo': motivo[:150], 'count': count})

        return JsonResponse({
            'success': importacion.exitosas > 0,
            'message': importacion.observaciones or 'Importación finalizada.',
            'exitosas': importacion.exitosas,
            'fallidas': importacion.fallidas,
            'total_filas': importacion.total_filas,
            'importacion_id': importacion.id,
            'errores_resumen': errores_resumen,
            'estado': importacion.estado,
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'message': str(exc), 'exitosas': 0, 'fallidas': 0})


@login_required
def ordenes_exportar_view(request):
    """Exporta órdenes (filtradas por defecto; ?todas=1 exporta sin filtros)."""
    if request.user.rol not in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
        messages.error(request, 'Sin permisos para exportar')
        return redirect('ordenes_list')

    filter_keys = ('estado', 'tipo_trabajo', 'tecnico', 'cliente', 'buscar', 'cola')
    tiene_filtros = any((request.GET.get(k) or '').strip() for k in filter_keys)
    forzar_filtrar = request.GET.get('filtrar') == '1'
    exportar_todas = request.GET.get('todas') == '1'
    usar_filtros = (not exportar_todas) and (forzar_filtrar or tiene_filtros)

    qs = _queryset_ordenes_filtrado(request, aplicar_filtros=usar_filtros)
    wb = exportar_ordenes_excel(list(qs))

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    from web.services.export_filenames import nombre_exportacion_con_fecha
    filename = nombre_exportacion_con_fecha('ordenes_trabajo.xlsx')
    response = HttpResponse(
        stream.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store'
    return response


@_requiere_admin_ordenes
@require_POST
def ordenes_asignar_masivo_view(request):
    """Asigna responsable a múltiples órdenes (estado ASIGNADA)."""
    ids_raw = request.POST.get('ids', '').strip()
    tecnico_id = request.POST.get('tecnico_responsable', '').strip()

    if not ids_raw or not tecnico_id:
        return JsonResponse({'success': False, 'message': 'Marca las órdenes y elige el técnico responsable.'})

    try:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
        resultado = asignar_ordenes_masivo(ids, int(tecnico_id), request.user)
        alertas = resultado["alertas_duplicado"]
        msg = f'Se asignaron {resultado["actualizadas"]} orden(es) a {resultado["tecnico"]}.'
        if alertas:
            msg += f' {alertas} quedaron con alerta de posible trabajo duplicado; revísalas.'
        return JsonResponse({'success': True, 'message': msg, **resultado})
    except Usuario.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Ese técnico no está disponible. Elige otro de la lista.'})
    except Exception as exc:
        return JsonResponse({'success': False, 'message': f'No se pudo asignar: {exc}'})


@_requiere_admin_ordenes
@require_POST
def ordenes_modificar_masivo_view(request):
    """Edición masiva de estado y tipo de trabajo."""
    ids_raw = request.POST.get('ids', '').strip()
    if not ids_raw:
        return JsonResponse({'success': False, 'message': 'Marca al menos una orden en la lista antes de continuar.'})

    try:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    except ValueError:
        return JsonResponse({'success': False, 'message': 'La selección de órdenes no es válida. Vuelve a marcarlas e intenta de nuevo.'})

    nuevo_estado = request.POST.get('estado', '').strip()
    nuevo_tipo = request.POST.get('tipo_trabajo', '').strip()
    tecnico_id = request.POST.get('tecnico_responsable', '').strip()

    if not nuevo_estado and not nuevo_tipo and not tecnico_id:
        return JsonResponse({
            'success': False,
            'message': 'No elegiste ningún cambio. Completa al menos un campo o cancela.',
        })

    ordenes = OrdenTrabajo.objects.filter(pk__in=ids, eliminado=False)
    actualizadas = 0

    for orden in ordenes:
        cambios = []
        if nuevo_estado and nuevo_estado in dict(OrdenTrabajo.ESTADO_CHOICES):
            orden.estado = nuevo_estado
            cambios.append('estado')
            if nuevo_estado == 'ASIGNADA' and not orden.fecha_asignacion:
                orden.fecha_asignacion = timezone.now()
            if nuevo_estado in ['REALIZADA', 'FINALIZADA'] and not orden.fecha_fin_ejecucion:
                orden.fecha_fin_ejecucion = timezone.now()
        if nuevo_tipo and nuevo_tipo in dict(OrdenTrabajo.TIPO_TRABAJO_CHOICES):
            orden.tipo_trabajo = nuevo_tipo
            cambios.append('tipo_trabajo')
        if tecnico_id:
            orden.tecnico_responsable = Usuario.objects.get(pk=int(tecnico_id), rol='TECNICO')
            if orden.estado == 'CREADA':
                orden.estado = 'ASIGNADA'
                orden.fecha_asignacion = timezone.now()
            cambios.append('tecnico_responsable')

        if cambios:
            orden.save()
            aplicar_alerta_duplicado(orden)
            actualizadas += 1

    sin_cambios = len(ids) - actualizadas
    msg = f'Se actualizaron {actualizadas} orden(es).'
    if sin_cambios:
        msg += f' {sin_cambios} ya tenían esos mismos datos.'
    return JsonResponse({
        'success': True,
        'message': msg,
        'actualizadas': actualizadas,
    })


@login_required
@require_POST
def orden_subir_informe_view(request, pk):
    """Sube un informe PDF del cliente vinculado a la orden (manual o respaldo MoreApp)."""
    MAX_PDF_BYTES = 15 * 1024 * 1024  # 15 MB

    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)

    if request.user.rol not in ['ADMIN', 'ADMINISTRATIVO'] and orden.tecnico_responsable != request.user:
        return JsonResponse({'success': False, 'message': 'No tienes permisos para subir el PDF.'}, status=403)

    if orden.estado == 'CANCELADA':
        return JsonResponse(
            {'success': False, 'message': 'No se puede adjuntar PDF a una orden cancelada.'},
            status=400,
        )

    if not orden.cliente:
        return JsonResponse(
            {'success': False, 'message': 'La orden no tiene cliente asociado; no se puede guardar el PDF.'},
            status=400,
        )

    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'success': False, 'message': 'No se envió archivo.'}, status=400)

    nombre = (archivo.name or '').strip()
    if not nombre.lower().endswith('.pdf'):
        return JsonResponse({'success': False, 'message': 'Solo se permiten archivos PDF.'}, status=400)

    if archivo.size and archivo.size > MAX_PDF_BYTES:
        return JsonResponse(
            {'success': False, 'message': 'El PDF supera el tamaño máximo permitido (15 MB).'},
            status=400,
        )

    # Validar cabecera PDF (evita renombrar .exe/.jpg a .pdf)
    try:
        cabecera = archivo.read(5)
        archivo.seek(0)
    except Exception:
        return JsonResponse({'success': False, 'message': 'No se pudo leer el archivo.'}, status=400)
    if cabecera != b'%PDF-':
        return JsonResponse(
            {'success': False, 'message': 'El archivo no parece un PDF válido.'},
            status=400,
        )

    como_respaldo = str(request.POST.get('como_respaldo_moreapp', '')).strip().lower() in (
        '1', 'true', 'yes', 'on', 'si', 'sí',
    )
    origen = 'RESPALDO_MOREAPP' if como_respaldo else 'MANUAL'

    try:
        informe = guardar_informe_pdf(
            cliente=orden.cliente,
            archivo_origen=archivo,
            nombre_archivo=nombre,
            orden=orden,
            usuario=request.user,
            origen=origen,
        )
        if origen == 'RESPALDO_MOREAPP':
            mensaje = (
                'Respaldo PDF de MoreApp guardado correctamente. '
                'Quedó asociado a esta orden para revisión administrativa.'
            )
        else:
            mensaje = 'Informe PDF guardado correctamente.'
        return JsonResponse({
            'success': True,
            'message': mensaje,
            'informe_id': informe.id,
            'origen': origen,
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=500)


@login_required
@require_POST
def orden_solicitar_validacion_comunicacion_view(request, pk):
    """Técnico responsable (o admin) solicita prueba de comunicación en la OT."""
    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
    usuario = request.user

    if orden.estado == 'CANCELADA':
        messages.error(request, 'No se puede solicitar validación en una orden cancelada.')
        return redirect('orden_detalle', pk=pk)

    es_admin = usuario.rol in ['ADMIN', 'ADMINISTRATIVO']
    es_responsable = orden.tecnico_responsable_id == usuario.id
    if not es_admin and not es_responsable:
        messages.error(request, 'No tienes permiso para solicitar la validación de comunicación.')
        return redirect('orden_detalle', pk=pk)

    if orden.validaciones_comunicacion.filter(estado='SOLICITADA').exists():
        messages.info(
            request,
            'Ya hay una solicitud de validación de comunicación pendiente en esta orden.',
        )
        return redirect('orden_detalle', pk=pk)

    nota = (request.POST.get('observaciones_solicitud') or '').strip()
    registro = ValidacionComunicacionOT.objects.create(
        orden=orden,
        estado='SOLICITADA',
        solicitado_por=usuario,
        observaciones_solicitud=nota,
    )
    register_audit_event(
        AuditEvent(
            actor_id=getattr(usuario, 'id', None),
            action='OT_COMUNICACION_SOLICITADA',
            entity='ValidacionComunicacionOT',
            entity_id=str(registro.pk),
            field_name='estado',
            old_value='',
            new_value='SOLICITADA',
            reason=f'Solicitud de validación de comunicación en OT #{orden.pk}',
        )
    )
    messages.success(
        request,
        'Solicitud de validación de comunicación registrada. '
        'Administración podrá registrar el resultado de la prueba.',
    )
    return redirect('orden_detalle', pk=pk)


@login_required
@require_POST
def orden_registrar_validacion_comunicacion_view(request, pk):
    """Administrativo registra el resultado (Exitosa / Fallida) de la prueba."""
    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
    usuario = request.user

    if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO']:
        messages.error(request, 'Solo administración puede registrar el resultado de la prueba.')
        return redirect('orden_detalle', pk=pk)

    if orden.estado == 'CANCELADA':
        messages.error(request, 'No se puede registrar validación en una orden cancelada.')
        return redirect('orden_detalle', pk=pk)

    resultado = (request.POST.get('resultado') or '').strip().upper()
    if resultado not in ('EXITOSA', 'FALLIDA'):
        messages.error(request, 'Debes indicar el resultado: Exitosa o Fallida.')
        return redirect('orden_detalle', pk=pk)

    observaciones = (request.POST.get('observaciones') or '').strip()
    validacion_id = (request.POST.get('validacion_id') or '').strip()

    registro = None
    if validacion_id:
        try:
            registro = ValidacionComunicacionOT.objects.get(
                pk=int(validacion_id),
                orden=orden,
                estado='SOLICITADA',
            )
        except (ValidacionComunicacionOT.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'La solicitud de validación no existe o ya fue resuelta.')
            return redirect('orden_detalle', pk=pk)
    else:
        # Registro directo (sin solicitud previa del técnico)
        registro = ValidacionComunicacionOT(
            orden=orden,
            solicitado_por=usuario,
            observaciones_solicitud='Registro directo por administración',
        )

    estado_anterior = registro.estado if registro.pk else ''
    registro.estado = resultado
    registro.validado_por = usuario
    registro.fecha_validacion = timezone.now()
    registro.observaciones = observaciones
    registro.save()

    register_audit_event(
        AuditEvent(
            actor_id=getattr(usuario, 'id', None),
            action='OT_COMUNICACION_REGISTRADA',
            entity='ValidacionComunicacionOT',
            entity_id=str(registro.pk),
            field_name='estado',
            old_value=estado_anterior,
            new_value=resultado,
            reason=(
                f'Validación de comunicación {resultado} en OT #{orden.pk} '
                f'por {usuario.nombre_interno}'
                + (f': {observaciones}' if observaciones else '')
            ),
        )
    )
    label = 'Exitosa' if resultado == 'EXITOSA' else 'Fallida'
    messages.success(
        request,
        f'Resultado de comunicación registrado: {label} '
        f'(por {usuario.nombre_interno}).',
    )
    return redirect('orden_detalle', pk=pk)


@login_required
@admin_only
@require_POST
def orden_eliminar_view(request, pk):
    """Soft-delete de OT: oculta en listados y deja snapshot en movimientos."""
    from web.services.eliminaciones import ENTIDAD_ORDEN, registrar_eliminacion

    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
    orden_id = orden.id
    titulo = orden.titulo
    motivo = request.POST.get('motivo', '').strip()

    _, creado = registrar_eliminacion(
        ENTIDAD_ORDEN,
        orden,
        request.user,
        motivo=motivo,
    )
    if creado:
        messages.success(
            request,
            f'Orden #{orden_id} ({titulo}) eliminada. Quedó registrada en Movimientos.',
        )
    else:
        messages.warning(request, f'La orden #{orden_id} ya estaba eliminada.')
    return redirect('ordenes_list')


# ========================================
# API REST para ViewSet
# ========================================

class OrdenTrabajoViewSet(viewsets.ModelViewSet):
    """
    API REST para gestionar Órdenes de Trabajo.
    Estado solo vía action cambiar_estado; destroy = soft-delete.
    """

    serializer_class = OrdenTrabajoSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        usuario = self.request.user

        if usuario.rol in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
            return OrdenTrabajo.objects.filter(eliminado=False)
        elif usuario.rol == 'TECNICO':
            return OrdenTrabajo.objects.filter(tecnico_responsable=usuario, eliminado=False)

        return OrdenTrabajo.objects.none()

    def perform_create(self, serializer):
        usuario = self.request.user
        if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Solo ADMIN/ADMINISTRATIVO pueden crear OT por API.')
        serializer.save(creada_por=usuario, estado='CREADA')

    def perform_update(self, serializer):
        usuario = self.request.user
        if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO', 'TECNICO']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Sin permiso para editar OT por API.')
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        from rest_framework.exceptions import PermissionDenied
        from web.services.eliminaciones import ENTIDAD_ORDEN, registrar_eliminacion

        if request.user.rol not in ['ADMIN', 'ADMINISTRATIVO']:
            raise PermissionDenied('Sin permiso para eliminar OT.')
        orden = self.get_object()
        registrar_eliminacion(ENTIDAD_ORDEN, orden, request.user, motivo='API destroy')
        return Response({'success': True, 'soft_deleted': True}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def cambiar_estado(self, request, pk=None):
        """Endpoint para cambiar estado de orden"""
        orden = self.get_object()
        nuevo_estado = request.data.get('estado')

        resultado = orden.cambiar_estado(request.user, nuevo_estado)

        if resultado['success']:
            return Response(resultado, status=status.HTTP_200_OK)
        else:
            return Response(resultado, status=status.HTTP_400_BAD_REQUEST)


# ========================================
# INTEGRACIÓN MOREAPP - Webhook Receiver
# ========================================

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])  # MoreApp no usa autenticación estándar
def moreapp_webhook_view(request):
    """
    Recibe webhooks de MoreApp con datos de terreno
    
    Payload esperado de MoreApp:
    {
        "submission_id": "abc123",
        "form_name": "Instalación Medidores",
        "completed_at": "2026-01-27T10:30:00Z",
        "data": {
            "orden_trabajo_id": "123",
            "tecnico_nombre": "Juan Pérez",
            "cliente_numero": "CLI001",
            "tipo_trabajo": "INSTALACION",
            "medidor_serie": "MED-001",
            "sim_imei": "123456789",
            "modem_imei": "987654321",
            "observaciones": "Instalación exitosa",
            "fotos": ["url1", "url2"]
        }
    }
    """
    
    try:
        # Parsear payload
        if isinstance(request.body, bytes):
            payload = json.loads(request.body.decode('utf-8'))
        else:
            payload = request.data
        
        submission_id = payload.get('submission_id')
        
        if not submission_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing submission_id'
            }, status=400)
        
        # Verificar si ya existe
        if IntegracionMoreApp.objects.filter(moreapp_submission_id=submission_id).exists():
            return JsonResponse({
                'success': True,
                'message': 'Submission already processed',
                'status': 'DUPLICADO'
            })
        
        # Crear registro de integración
        integracion = IntegracionMoreApp()
        integracion.moreapp_submission_id = submission_id
        integracion.estado_sincronizacion = 'PROCESANDO'
        integracion.datos_recibidos = payload
        integracion.save()
        
        # Procesar datos
        try:
            procesar_moreapp_submission(integracion, payload)
            
            integracion.estado_sincronizacion = 'PROCESADO'
            integracion.fecha_procesamiento = timezone.now()
            integracion.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Submission processed successfully',
                'integracion_id': integracion.id
            })
            
        except Exception as e:
            integracion.estado_sincronizacion = 'ERROR'
            integracion.mensaje_error = str(e)
            integracion.fecha_procesamiento = timezone.now()
            integracion.save()
            
            return JsonResponse({
                'success': False,
                'error': str(e),
                'integracion_id': integracion.id
            }, status=500)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error parsing payload: {str(e)}'
        }, status=400)


def procesar_moreapp_submission(integracion, payload):
    """
    Procesa el submission de MoreApp y actualiza BD
    """
    data = payload.get('data', {})
    
    # 1. Buscar o crear orden de trabajo
    orden_id = data.get('orden_trabajo_id')
    
    if orden_id:
        try:
            orden = OrdenTrabajo.objects.get(id=orden_id)
        except OrdenTrabajo.DoesNotExist:
            raise Exception(f'Orden #{orden_id} no encontrada')
    else:
        # Crear nueva orden desde MoreApp
        orden = OrdenTrabajo()
        orden.titulo = data.get('titulo', f'Trabajo desde MoreApp')
        orden.descripcion = data.get('descripcion', '')
        orden.tipo_trabajo = data.get('tipo_trabajo', 'OTRO')
        
        # Buscar técnico por nombre
        tecnico_nombre = data.get('tecnico_nombre')
        if tecnico_nombre:
            tecnico = Usuario.objects.filter(
                nombre_interno__icontains=tecnico_nombre,
                rol='TECNICO'
            ).first()
            if tecnico:
                orden.tecnico_responsable = tecnico
        
        # Buscar cliente
        cliente_numero = data.get('cliente_numero')
        if cliente_numero:
            cliente = Cliente.objects.filter(numero_cliente=cliente_numero).first()
            if cliente:
                orden.cliente = cliente
                integracion.actualizo_cliente = True
        
        orden.estado = 'FINALIZADA'
        orden.creada_por = Usuario.objects.filter(rol='ADMIN').first()
        orden.save()
    
    # 2. Actualizar equipos utilizados
    medidor_serie = data.get('medidor_serie')
    if medidor_serie:
        medidor = Medidor.objects.filter(serie=medidor_serie).first()
        if medidor:
            orden.medidor = medidor
            integracion.actualizo_equipos = True
    
    sim_imei = data.get('sim_imei')
    if sim_imei:
        sim = SimCard.objects.filter(imei=sim_imei).first()
        if sim:
            orden.simcard = sim
            integracion.actualizo_equipos = True
    
    modem_imei = data.get('modem_imei')
    if modem_imei:
        modem = Modem.objects.filter(imei=modem_imei).first()
        if modem:
            orden.modem = modem
            integracion.actualizo_equipos = True
    
    # 3. Actualizar observaciones
    observaciones = data.get('observaciones')
    if observaciones:
        orden.observaciones_tecnicas = observaciones
    
    # 4. Actualizar fechas
    completed_at = payload.get('completed_at')
    if completed_at:
        from django.utils.dateparse import parse_datetime
        fecha_fin = parse_datetime(completed_at)
        if fecha_fin:
            orden.fecha_fin_ejecucion = fecha_fin
    
    orden.save()

    from ordenes_trabajo.sync import sincronizar_orden_completa
    sincronizar_orden_completa(orden, orden.creada_por or Usuario.objects.filter(rol='ADMIN').first(), orden.estado)

    # 5. Crear adjuntos desde URLs de fotos
    fotos = data.get('fotos', [])
    if fotos:
        for idx, foto_url in enumerate(fotos):
            adjunto = AdjuntoOrden()
            adjunto.orden = orden
            adjunto.tipo = 'FOTO'
            adjunto.nombre_archivo = f'foto_moreapp_{idx+1}.jpg'
            adjunto.url_externa = foto_url
            adjunto.metadata = {'source': 'MoreApp', 'submission_id': integracion.moreapp_submission_id}
            adjunto.save()
        
        integracion.creo_adjuntos = True
    
    # 6. Vincular integración con orden
    integracion.orden = orden
    integracion.datos_procesados = {
        'orden_id': orden.id,
        'cliente_actualizado': integracion.actualizo_cliente,
        'equipos_actualizados': integracion.actualizo_equipos,
        'adjuntos_creados': len(fotos)
    }
    integracion.save()
