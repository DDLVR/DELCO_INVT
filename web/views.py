
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from inventario.models import MovimientoInventario, MovimientoItem, Ubicacion
from django.views.decorators.http import require_POST

@login_required
@require_POST
def inventario_eliminar_view(request, pk):
    """Elimina un equipo (medidor, sim, modem) y registra quién lo eliminó"""
    tipo = request.POST.get('tipo', 'medidor')
    try:
        if tipo == 'medidor':
            equipo = get_object_or_404(Medidor, pk=pk)
            identificador = equipo.serie
            tipo_item = 'MEDIDOR'
        elif tipo == 'sim':
            equipo = get_object_or_404(SimCard, pk=pk)
            identificador = equipo.imei or equipo.abonado or str(equipo.pk)
            tipo_item = 'SIM'
        elif tipo == 'modem':
            equipo = get_object_or_404(Modem, pk=pk)
            identificador = equipo.serie
            tipo_item = 'MODEM'
        else:
            return JsonResponse({'success': False, 'message': 'Tipo de equipo no válido'})

        ubicacion = getattr(equipo, 'ubicacion_actual', None)
        if ubicacion is None:
            ubicacion = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
        if ubicacion is None:
            ubicacion = Ubicacion.objects.create(tipo='BODEGA_DELCO', nombre='Bodega Principal')

        movimiento = MovimientoInventario.objects.create(
            tipo='ELIMINACION',
            origen=ubicacion,
            destino=ubicacion,
            responsable=request.user,
            observacion=(
                f'Eliminación de {tipo_item} {identificador} por '
                f'{request.user.nombre_interno if hasattr(request.user, "nombre_interno") else request.user}'
            )
        )

        from inventario.models import MovimientoItem
        item_kwargs = {'movimiento': movimiento, 'tipo_equipo': tipo_item, 'cantidad': 1}
        if tipo_item == 'MEDIDOR':
            item_kwargs['medidor'] = equipo
        elif tipo_item == 'SIM':
            item_kwargs['simcard'] = equipo
        else:
            item_kwargs['modem'] = equipo
        MovimientoItem.objects.create(**item_kwargs)

        equipo.delete()
        return JsonResponse({'success': True, 'message': f'{tipo.capitalize()} eliminado correctamente'})
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
from io import BytesIO
from datetime import datetime
from .decorators import role_required, admin_or_administrativo
from ordenes_trabajo.models import OrdenTrabajo
from inventario.models import Medidor, SimCard, Modem, EstadoInventario, Ubicacion
from clientes.models import Cliente
from importaciones.utils import importar_equipos_excel, exportar_equipos_excel
from importaciones.models import ImportacionExcel, ImportacionExcelError

logger = logging.getLogger(__name__)


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
    }
    
    # ADMIN y ADMINISTRATIVO: Vista general de todo
    if rol in ['ADMIN', 'ADMINISTRATIVO']:
        # Órdenes de trabajo
        context['total_ordenes'] = OrdenTrabajo.objects.count()
        context['ordenes_pendientes'] = OrdenTrabajo.objects.filter(
            estado__in=['CREADA', 'ASIGNADA', 'EN_EJECUCION']
        ).count()
        context['ordenes_completadas'] = OrdenTrabajo.objects.filter(
            estado='COMPLETADA'
        ).count()
        context['ordenes_canceladas'] = OrdenTrabajo.objects.filter(
            estado='CANCELADA'
        ).count()
        
        # Usuarios
        context['usuarios_activos'] = request.user.__class__.objects.filter(is_active=True).count()
        context['total_tecnicos'] = request.user.__class__.objects.filter(rol='TECNICO', is_active=True).count()
        context['total_administrativos'] = request.user.__class__.objects.filter(rol='ADMINISTRATIVO', is_active=True).count()
        
        # Inventario - Medidores
        context['total_medidores'] = Medidor.objects.count()
        context['medidores_bodega'] = Medidor.objects.filter(
            estado_inventario__nombre='En bodega'
        ).count()
        context['medidores_instalados'] = Medidor.objects.filter(
            estado_inventario__nombre='Instalado'
        ).count()
        
        # Inventario - SIM Cards
        context['total_sims'] = SimCard.objects.count()
        context['sims_bodega'] = SimCard.objects.filter(
            estado_inventario__nombre='En bodega'
        ).count()
        context['sims_instaladas'] = SimCard.objects.filter(
            estado_inventario__nombre='Instalado'
        ).count()
        
        # Inventario - Modems
        context['total_modems'] = Modem.objects.count()
        context['modems_bodega'] = Modem.objects.filter(
            estado_inventario__nombre='En bodega'
        ).count()
        context['modems_instalados'] = Modem.objects.filter(
            estado_inventario__nombre='Instalado'
        ).count()
        
        # Clientes
        context['total_clientes'] = Cliente.objects.count()
        
        # Calcular porcentajes para barras de progreso (evitar división por cero)
        context['medidores_instalados_pct'] = round((context['medidores_instalados'] / context['total_medidores'] * 100) if context['total_medidores'] > 0 else 0)
        context['medidores_bodega_pct'] = round((context['medidores_bodega'] / context['total_medidores'] * 100) if context['total_medidores'] > 0 else 0)
        
        context['sims_instaladas_pct'] = round((context['sims_instaladas'] / context['total_sims'] * 100) if context['total_sims'] > 0 else 0)
        context['sims_bodega_pct'] = round((context['sims_bodega'] / context['total_sims'] * 100) if context['total_sims'] > 0 else 0)
        
        context['modems_instalados_pct'] = round((context['modems_instalados'] / context['total_modems'] * 100) if context['total_modems'] > 0 else 0)
        context['modems_bodega_pct'] = round((context['modems_bodega'] / context['total_modems'] * 100) if context['total_modems'] > 0 else 0)
        
        # Estados disponibles para gráficos
        from django.db.models import Count
        context['medidores_por_estado'] = list(
            Medidor.objects.values('estado_inventario__nombre')
            .annotate(cantidad=Count('id'))
            .order_by('-cantidad')[:5]
        )
        context['sims_por_estado'] = list(
            SimCard.objects.values('estado_inventario__nombre')
            .annotate(cantidad=Count('id'))
            .order_by('-cantidad')[:5]
        )
        context['modems_por_estado'] = list(
            Modem.objects.values('estado_inventario__nombre')
            .annotate(cantidad=Count('id'))
            .order_by('-cantidad')[:5]
        )
        
        # Movimientos de inventario (últimos 7 días)
        from inventario.models import MovimientoInventario
        from datetime import timedelta
        fecha_hace_7_dias = datetime.now() - timedelta(days=7)
        
        context['movimientos_recientes'] = MovimientoInventario.objects.filter(
            fecha_hora__gte=fecha_hace_7_dias
        ).count()
        context['movimientos_hoy'] = MovimientoInventario.objects.filter(
            fecha_hora__date=datetime.now().date()
        ).count()
        
        return render(request, 'dashboards/admin_dashboard.html', context)
    elif rol == 'TECNICO':
        context['mis_ordenes'] = OrdenTrabajo.objects.filter(
            tecnico_responsable=request.user
        ).order_by('-fecha_creacion')
        context['en_ejecucion'] = context['mis_ordenes'].filter(
            estado='EN_EJECUCION'
        ).count()
        context['finalizadas'] = context['mis_ordenes'].filter(
            estado='FINALIZADA'
        ).count()
        return render(request, 'dashboards/tecnico_dashboard.html', context)
    
    # SUPERVISOR: Validaciones pendientes
    elif rol == 'SUPERVISOR':
        context['pendientes_validacion'] = OrdenTrabajo.objects.filter(
            estado='PENDIENTE_VALIDACION'
        )
        context['observadas'] = OrdenTrabajo.objects.filter(
            estado='OBSERVADA'
        ).count()
        return render(request, 'dashboards/supervisor_dashboard.html', context)
    
    # GERENCIA: KPIs y reportes
    elif rol == 'GERENCIA':
        context['ordenes_finalizadas'] = OrdenTrabajo.objects.filter(
            estado='FINALIZADA'
        ).count()
        context['tasa_cumplimiento'] = '95%'  # Placeholder
        return render(request, 'dashboards/gerencia_dashboard.html', context)
    
    # AUDITOR: Auditoría y logs
    elif rol == 'AUDITOR':
        context['ultimas_ordenes'] = OrdenTrabajo.objects.order_by('-fecha_creacion')[:20]
        return render(request, 'dashboards/auditor_dashboard.html', context)
    
    # Default
    return render(request, 'dashboard.html', context)


# ========== VISTAS DE ÓRDENES DE TRABAJO ==========

@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO'])
def ordenes_list_view(request):
    """Listado de órdenes (Admin/Administrativo pueden ver todas, TECNICO solo las suyas)"""
    ordenes = OrdenTrabajo.objects.all().order_by('-fecha_creacion')
    
    # Si es TECNICO, filtrar solo sus órdenes asignadas
    if request.user.rol == 'TECNICO':
        ordenes = ordenes.filter(tecnico_responsable=request.user) | ordenes.filter(tecnicos_equipo=request.user)
        ordenes = ordenes.distinct()
    
    # Filtro por estado si se proporciona
    estado = request.GET.get('estado')
    if estado:
        ordenes = ordenes.filter(estado=estado)
    
    context = {
        'ordenes': ordenes,
        'estados': OrdenTrabajo.ESTADO_CHOICES,
        'estado_filtro': estado,
    }
    return render(request, 'ordenes/list.html', context)


@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'SUPERVISOR'])
def orden_detalle_view(request, pk):
    """Detalle de una orden específica"""
    orden = OrdenTrabajo.objects.get(pk=pk)
    
    # Validar acceso
    tiene_acceso = (
        request.user.rol in ['ADMIN', 'ADMINISTRATIVO', 'SUPERVISOR'] or
        request.user == orden.tecnico_responsable or
        request.user in orden.tecnicos_equipo.all()
    )
    
    if not tiene_acceso:
        messages.error(request, 'No tienes acceso a esta orden')
        return redirect('login')
    
    context = {
        'orden': orden,
        'puede_cambiar_estado': orden.puede_cambiar_estado(request.user, None),
        'adjuntos': orden.adjuntos.all(),
    }
    return render(request, 'ordenes/detalle.html', context)


@admin_or_administrativo
def orden_crear_view(request):
    """Crear nueva orden"""
    if request.method == 'POST':
        # TODO: Implementar formulario y lógica de creación
        pass
    
    context = {}
    return render(request, 'ordenes/crear.html', context)


# ========== VISTAS DE INVENTARIO ==========

@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO'])
def inventario_list_view(request):
    """Listado de equipos en inventario con filtros"""
    from django.core.paginator import Paginator
    
    from usuarios.models import Usuario
    from clientes.models import Cliente
    
    tipo = request.GET.get('tipo', 'medidor')
    page_num = request.GET.get('page', '1')
    per_page_raw = request.GET.get('per_page', '100')
    busqueda = request.GET.get('q', '').strip()
    campo_busqueda = request.GET.get('campo', 'all').strip()
    estado_filtro = request.GET.get('estado', '')
    ubicacion_filtro = request.GET.get('ubicacion', '')
    proyecto_filtro = request.GET.get('proyecto', '').strip()
    caja_filtro = request.GET.get('caja', '').strip()
    tipo_medidor_filtro = request.GET.get('tipo_medidor', '').strip()

    # Tamaño de página permitido (optimizado)
    per_page_options = [10, 25, 50, 100]
    try:
        per_page = int(per_page_raw)
    except (TypeError, ValueError):
        per_page = 100
    if per_page not in per_page_options:
        per_page = 100
    
    # Obtener datos base
    if tipo == 'medidor':
        equipos = Medidor.objects.select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).all().order_by('-id')
        titulo = 'Medidores'
    elif tipo == 'sim':
        equipos = SimCard.objects.select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'en_custodia_de', 'medidor'
        ).all().order_by('-id')
        titulo = 'SIM Cards'
    elif tipo == 'modem':
        equipos = Modem.objects.select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).all().order_by('-id')
        titulo = 'Módems'
    else:
        equipos = Medidor.objects.select_related(
            'estado_inventario', 'ubicacion_actual', 'cliente', 'entregado_a'
        ).all().order_by('-id')
        titulo = 'Medidores'
        tipo = 'medidor'
    
    # TECNICO: Solo ve equipos asignados a él
    if request.user.rol == 'TECNICO':
        if tipo == 'sim':
            # SimCard usa 'en_custodia_de' en lugar de 'entregado_a'
            equipos = equipos.filter(en_custodia_de=request.user)
        else:
            # Medidor y Modem usan 'entregado_a'
            equipos = equipos.filter(entregado_a=request.user)
    
    # Aplicar filtros
    if estado_filtro:
        equipos = equipos.filter(estado_inventario_id=estado_filtro)
    
    if ubicacion_filtro:
        equipos = equipos.filter(ubicacion_actual_id=ubicacion_filtro)

    if proyecto_filtro:
        equipos = equipos.filter(proyecto__icontains=proyecto_filtro)

    if caja_filtro and tipo in ('medidor', 'modem'):
        equipos = equipos.filter(caja__icontains=caja_filtro)

    if tipo == 'medidor' and tipo_medidor_filtro:
        equipos = equipos.filter(tipo_medidor=tipo_medidor_filtro)

    # Búsqueda global por servidor (evita filtrar solo el bloque cargado)
    if busqueda:
        if tipo == 'medidor':
            campos_por_tipo = {
                'serie': 'serie__icontains',
                'marca': 'marca__icontains',
                'caja': 'caja__icontains',
                'modulo': 'modulo__icontains',
                'tipo_medidor': 'tipo_medidor__icontains',
                'entregado_a': 'entregado_a__nombre_interno__icontains',
                'proyecto': 'proyecto__icontains',
                'estado': 'estado_inventario__nombre__icontains',
                'cliente': 'cliente__numero_cliente__icontains',
            }
            campos_all = [
                'serie__icontains',
                'marca__icontains',
                'caja__icontains',
                'modulo__icontains',
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
                'entregado_a': 'entregado_a_nombre__icontains',
                'proyecto': 'proyecto__icontains',
                'estado': 'estado_inventario__nombre__icontains',
                'cliente': 'cliente__numero_cliente__icontains',
            }
            campos_all = [
                'imei__icontains',
                'operador__icontains',
                'abonado__icontains',
                'entregado_a_nombre__icontains',
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
                'tecnico': 'tecnico_responsable__icontains',
                'estado': 'estado_inventario__nombre__icontains',
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
                'estado_inventario__nombre__icontains',
                'cliente__numero_cliente__icontains',
                'proyecto__icontains',
            ]

        if campo_busqueda in campos_por_tipo:
            equipos = equipos.filter(**{campos_por_tipo[campo_busqueda]: busqueda})
        else:
            query = Q()
            for lookup in campos_all:
                query |= Q(**{lookup: busqueda})
            equipos = equipos.filter(query)

    total_filtrado = equipos.count()
    paginador = Paginator(equipos, per_page)
    page_obj = paginador.get_page(page_num)
    equipos = page_obj.object_list

    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_string = query_params.urlencode()
    
    # Obtener opciones para filtros (solo estados de negocio definidos)
    if tipo in ('medidor', 'modem'):
        estados_permitidos = ['En bodega', 'Instalado', 'Retirado', 'En reparación', 'Dado de baja', 'En peaje']
    else:
        estados_permitidos = ['En bodega', 'Instalado', 'Retirado', 'En reparación', 'Dado de baja']
    estados_disponibles = list(EstadoInventario.objects.filter(nombre__in=estados_permitidos))
    estados_disponibles.sort(key=lambda e: estados_permitidos.index(e.nombre) if e.nombre in estados_permitidos else 99)
    ubicaciones_disponibles = Ubicacion.objects.all()
    usuarios = Usuario.objects.filter(rol='TECNICO')  # Solo técnicos
    clientes = Cliente.objects.all()
    medidores = Medidor.objects.all().order_by('serie')  # Todos los medidores
    proyectos_disponibles = sorted(set(
        list(Medidor.objects.exclude(proyecto='').values_list('proyecto', flat=True))
        + list(SimCard.objects.exclude(proyecto='').values_list('proyecto', flat=True))
        + list(Modem.objects.exclude(proyecto='').values_list('proyecto', flat=True))
    ))
    
    context = {
        'equipos': equipos,
        'tipo': tipo,
        'titulo': titulo,
        'estados_disponibles': estados_disponibles,
        'ubicaciones_disponibles': ubicaciones_disponibles,
        'usuarios': usuarios,
        'clientes': clientes,
        'medidores': medidores,
        'estado_seleccionado': estado_filtro,
        'ubicacion_seleccionada': ubicacion_filtro,
        'proyecto_seleccionado': proyecto_filtro,
        'caja_seleccionada': caja_filtro,
        'tipo_medidor_seleccionado': tipo_medidor_filtro,
        'proyectos_disponibles': proyectos_disponibles,
        'tipo_medidor_choices': Medidor.TIPO_MEDIDOR_CHOICES,
        'total_medidores_directos': Medidor.objects.filter(tipo_medidor='DIRECTO').count(),
        'total_medidores_indirectos': Medidor.objects.filter(tipo_medidor='INDIRECTO').count(),
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
@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO'])
@require_http_methods(["GET"])
def inventario_obtener_datos_view(request, pk):
    """Obtiene datos de un equipo en formato JSON"""
    
    tipo = request.GET.get('tipo', 'medidor')
    
    try:
        # Obtener el equipo según tipo
        if tipo == 'medidor':
            equipo = get_object_or_404(Medidor, pk=pk)
        elif tipo == 'sim':
            equipo = get_object_or_404(SimCard, pk=pk)
        elif tipo == 'modem':
            equipo = get_object_or_404(Modem, pk=pk)
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
                'fecha_entrega': equipo.fecha_entrega.strftime('%Y-%m-%d') if equipo.fecha_entrega else '',
                'estado_id': getattr(equipo, 'estado_inventario_id', '') or '',
                'cliente_id': getattr(equipo, 'cliente_id', '') or '',
                'cliente_numero': equipo.cliente.numero_cliente if getattr(equipo, 'cliente', None) else '',
                'medidor_id': getattr(equipo, 'medidor_id', '') or '',
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
                'medidor_id': getattr(equipo, 'medidor_id', '') or '',
                'observaciones': getattr(equipo, 'observaciones', '') or '',
                'marca_secundaria': getattr(equipo, 'marca_secundaria', '') or '',
                'retirado': getattr(equipo, 'retirado', '') or '',
                'serie_secundaria': getattr(equipo, 'serie_secundaria', '') or '',
                'irregularidad': getattr(equipo, 'irregularidad', '') or '',
                'proyecto': getattr(equipo, 'proyecto', '') or '',
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
                'fecha_entrega': equipo.fecha_entrega.strftime('%Y-%m-%d') if equipo.fecha_entrega else '',
                'estado_id': getattr(equipo, 'estado_inventario_id', '') or '',
                'entregado_a_id': getattr(equipo, 'entregado_a_id', '') or '',
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
        # Obtener el equipo según tipo
        if tipo == 'medidor':
            equipo = get_object_or_404(Medidor, pk=pk)
        elif tipo == 'sim':
            equipo = get_object_or_404(SimCard, pk=pk)
        elif tipo == 'modem':
            equipo = get_object_or_404(Modem, pk=pk)
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

        # Snapshot para detectar qué cambió
        if tipo == 'medidor':
            before = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'entregado_a_id': equipo.entregado_a_id,
                'cliente_id': equipo.cliente_id,
                'proyecto': equipo.proyecto,
                'tipo_medidor': equipo.tipo_medidor,
            }
        elif tipo == 'sim':
            before = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'cliente_id': equipo.cliente_id,
                'medidor_id': equipo.medidor_id,
                'proyecto': equipo.proyecto,
            }
        else:
            before = {
                'estado_id': equipo.estado_inventario_id,
                'cliente_id': equipo.cliente_id,
                'medidor_id': equipo.medidor_id,
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
            cliente_texto = request.POST.get('cliente_texto', '').strip()
            cliente_id = request.POST.get('cliente', '').strip()
            medidor_id = request.POST.get('medidor', '').strip()
            proyecto = request.POST.get('proyecto', '').strip()
            
            # Debug
            print(f'[DEBUG SIMCARD] fecha_entrega={fecha_entrega} | estado_id={estado_id}')
            print(f'[DEBUG SIMCARD] cliente_texto={cliente_texto} | cliente_id={cliente_id} | medidor_id={medidor_id}')
            
            if fecha_entrega:
                equipo.fecha_entrega = fecha_entrega
            
            if estado_id:
                try:
                    estado_obj = EstadoInventario.objects.get(pk=int(estado_id))
                    equipo.estado_inventario = estado_obj
                except (ValueError, TypeError, EstadoInventario.DoesNotExist):
                    pass
            
            if cliente_texto:
                cliente_obj = Cliente.objects.filter(numero_cliente=cliente_texto).first()
                if not cliente_obj:
                    cliente_obj = Cliente.objects.create(
                        numero_cliente=cliente_texto,
                        direccion=f'Cliente {cliente_texto}',
                        comuna='Por definir'
                    )
                equipo.cliente = cliente_obj
            elif cliente_id:
                try:
                    equipo.cliente_id = int(cliente_id)
                except (ValueError, TypeError):
                    pass
            else:
                equipo.cliente = None
            
            if medidor_id:
                try:
                    equipo.medidor_id = int(medidor_id)
                except (ValueError, TypeError):
                    pass
            equipo.proyecto = proyecto
        elif tipo == 'modem':
            # Para Módems - solo campos AMARILLO (editables por administrativo)
            cliente_id = request.POST.get('cliente', '').strip()
            medidor_id = request.POST.get('medidor', '').strip()
            ip = request.POST.get('ip', '').strip()
            puerto = request.POST.get('puerto', '').strip()
            marca_secundaria = request.POST.get('marca_secundaria', '').strip()
            observaciones = request.POST.get('observaciones', '').strip()
            retirado = request.POST.get('retirado', '').strip()
            serie_secundaria = request.POST.get('serie_secundaria', '').strip()
            irregularidad = request.POST.get('irregularidad', '').strip()
            proyecto = request.POST.get('proyecto', '').strip()
            
            print(f'[DEBUG MODEM] cliente_id={cliente_id} | medidor_id={medidor_id}')
            
            if cliente_id:
                try:
                    equipo.cliente_id = int(cliente_id)
                except (ValueError, TypeError):
                    equipo.cliente_id = None
            else:
                equipo.cliente_id = None
            
            if medidor_id:
                try:
                    equipo.medidor_id = int(medidor_id)
                except (ValueError, TypeError):
                    equipo.medidor_id = None
            else:
                equipo.medidor_id = None

            # Campos azules editables
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
        else:
            # Para Medidor - todos los campos editables
            fecha_entrega = request.POST.get('fecha_entrega', '').strip()
            estado_id = request.POST.get('estado_medidor', '').strip()
            entregado_a_id = request.POST.get('entregado_a', '').strip()
            cliente_texto = request.POST.get('cliente_texto', '').strip()
            proyecto = request.POST.get('proyecto', '').strip()
            tipo_medidor = request.POST.get('tipo_medidor', '').strip().upper()

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
                try:
                    entregado_a_obj = Usuario.objects.get(pk=int(entregado_a_id))
                    equipo.entregado_a = entregado_a_obj
                except (ValueError, TypeError, Usuario.DoesNotExist):
                    pass
            
            if cliente_texto:
                cliente_obj = Cliente.objects.filter(numero_cliente=cliente_texto).first()
                if not cliente_obj:
                    cliente_obj = Cliente.objects.create(
                        numero_cliente=cliente_texto,
                        direccion=f'Cliente {cliente_texto}',
                        comuna='Por definir'
                    )
                equipo.cliente = cliente_obj
            else:
                equipo.cliente = None
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
                'cliente_id': equipo.cliente_id,
                'proyecto': equipo.proyecto,
                'tipo_medidor': equipo.tipo_medidor,
            }
            etiquetas = {
                'fecha_entrega': 'Fecha Entrega',
                'estado_id': 'Estado',
                'entregado_a_id': 'Entregado A',
                'cliente_id': 'Cliente',
                'proyecto': 'Proyecto',
                'tipo_medidor': 'Tipo Medidor',
            }
            tipo_item = 'MEDIDOR'
            identificador = equipo.serie
        elif tipo == 'sim':
            after = {
                'fecha_entrega': equipo.fecha_entrega,
                'estado_id': equipo.estado_inventario_id,
                'cliente_id': equipo.cliente_id,
                'medidor_id': equipo.medidor_id,
                'proyecto': equipo.proyecto,
            }
            etiquetas = {
                'fecha_entrega': 'Fecha Entrega',
                'estado_id': 'Estado',
                'cliente_id': 'Cliente',
                'medidor_id': 'Medidor',
                'proyecto': 'Proyecto',
            }
            tipo_item = 'SIM'
            identificador = equipo.imei or equipo.abonado or str(equipo.pk)
        else:
            after = {
                'estado_id': equipo.estado_inventario_id,
                'cliente_id': equipo.cliente_id,
                'medidor_id': equipo.medidor_id,
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
                'estado_id': 'Estado',
                'cliente_id': 'Cliente',
                'medidor_id': 'Medidor',
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

        return JsonResponse({'success': True, 'message': f'{tipo.capitalize()} creado correctamente'})

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
        return JsonResponse({'success': False, 'message': 'Selecciona al menos un equipo'})

    try:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    except Exception:
        ids = []

    if not ids:
        return JsonResponse({'success': False, 'message': 'IDs inválidos para edición múltiple'})

    if tipo == 'medidor':
        queryset = Medidor.objects.filter(pk__in=ids)
        tipo_item = 'MEDIDOR'
    elif tipo == 'sim':
        queryset = SimCard.objects.filter(pk__in=ids)
        tipo_item = 'SIM'
    elif tipo == 'modem':
        queryset = Modem.objects.filter(pk__in=ids)
        tipo_item = 'MODEM'
    else:
        return JsonResponse({'success': False, 'message': 'Tipo de equipo no válido'})

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
    medidor_id = request.POST.get('medidor_id', '').strip()
    proyecto = request.POST.get('proyecto', '').strip()
    tipo_medidor = request.POST.get('tipo_medidor', '').strip().upper()
    observacion = request.POST.get('observacion', '').strip()

    cliente_obj = None
    if cliente_texto:
        cliente_obj = Cliente.objects.filter(numero_cliente=cliente_texto).first()
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
            medidor_obj = Medidor.objects.get(pk=int(medidor_id))
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
        'message': f'Actualizados: {actualizados} | Sin cambios: {sin_cambios}',
        'actualizados': actualizados,
        'sin_cambios': sin_cambios,
    })


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO'])
@require_http_methods(["GET"])
def inventario_exportar_view(request):
    """Exporta equipos a archivo Excel"""
    
    tipo = request.GET.get('tipo', 'medidor')
    search = (request.GET.get('search') or '').strip()
    search_field = (request.GET.get('search_field') or 'all').strip()
    limit_raw = (request.GET.get('limit') or '-1').strip()
    proyecto_filtro = (request.GET.get('proyecto') or '').strip()
    caja_filtro = (request.GET.get('caja') or '').strip()
    tipo_medidor_filtro = (request.GET.get('tipo_medidor') or '').strip()
    
    # Obtener datos base
    if tipo == 'medidor':
        equipos = Medidor.objects.all()
        tipo_nombre = 'MEDIDORES'
        nombre_seccion = 'Medidores'
    elif tipo == 'sim':
        equipos = SimCard.objects.all()
        tipo_nombre = 'SIM'
        nombre_seccion = 'SIM-Cards'
    elif tipo == 'modem':
        equipos = Modem.objects.all()
        tipo_nombre = 'MODEMS'
        nombre_seccion = 'Modems'
    else:
        equipos = Medidor.objects.all()
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
    
    # Aplicar búsqueda (según filtros visibles en la tabla)
    if search:
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
                    | Q(entregado_a_nombre__icontains=search)
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
                    '7': 'entregado_a_nombre',
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
                    '8': 'tecnico_responsable',
                    '9': 'estado_inventario__nombre',
                    '10': 'cliente__numero_cliente',
                    '11': 'proyecto',
                },
            }
            if tipo == 'medidor' and search_field == '4':
                val = search.lower()
                if val in ['si', 'sí', 'true', '1', 'yes']:
                    equipos = equipos.filter(modulo=True)
                elif val in ['no', 'false', '0']:
                    equipos = equipos.filter(modulo=False)
                else:
                    equipos = equipos.none()
            else:
                campo = field_map.get(tipo, {}).get(search_field)
                if campo:
                    equipos = equipos.filter(**{f'{campo}__icontains': search})

    # Aplicar cantidad visible (selector Mostrar)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = -1
    if limit != -1:
        equipos = equipos[:limit]
    
    # Generar archivo Excel
    wb = exportar_equipos_excel(equipos, tipo_nombre)
    
    # Preparar respuesta HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    timestamp = datetime.now().strftime("%d-%m-%Y")
    response['Content-Disposition'] = f'attachment; filename="{nombre_seccion}-{timestamp}.xlsx"'
    
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
        'date_joined': request.user.date_joined.strftime('%d/%m/%Y %H:%M'),
    })


@login_required
@role_required(['ADMIN'])
def usuarios_list_view(request):
    """Listar todos los usuarios activos y pasar roles para filtro select"""
    from usuarios.models import Usuario
    usuarios = Usuario.objects.filter(is_active=True).order_by('nombre_interno')
    roles_order = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'SUPERVISOR', 'GERENCIA', 'AUDITOR']
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
    
    roles = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'SUPERVISOR', 'GERENCIA', 'AUDITOR']
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
    
    roles = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'SUPERVISOR', 'GERENCIA', 'AUDITOR']
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
@role_required(['ADMIN', 'ADMINISTRATIVO'])
def clientes_list_view(request):
    """Lista de clientes activos con modo solo lectura para ADMINISTRATIVO."""
    clientes = Cliente.objects.filter(activo=True).order_by('numero_cliente')
    context = {
        'clientes': clientes,
        'total_clientes': clientes.count(),
        'puede_editar': request.user.rol == 'ADMIN',
    }
    return render(request, 'clientes/list.html', context)


@login_required
@role_required(['ADMIN'])
def cliente_crear_view(request):
    """Crear cliente (solo rol ADMIN)."""
    if request.method == 'POST':
        numero_cliente = request.POST.get('numero_cliente', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        comuna = request.POST.get('comuna', '').strip()
        referencia = request.POST.get('referencia', '').strip()
        medidor_serie = request.POST.get('medidor_serie', '').strip()

        if not all([numero_cliente, direccion, comuna]):
            messages.error(request, 'Numero de cliente, direccion y comuna son obligatorios.')
            return redirect('cliente_crear')

        if Cliente.objects.filter(numero_cliente=numero_cliente).exists():
            messages.error(request, f'Ya existe un cliente con numero {numero_cliente}.')
            return redirect('cliente_crear')

        medidor_obj = None
        if medidor_serie:
            medidor_obj = Medidor.objects.filter(serie=medidor_serie).first()
            if not medidor_obj:
                messages.error(request, f'No existe un medidor con serie {medidor_serie}.')
                return redirect('cliente_crear')
            if Cliente.objects.filter(medidor_actual=medidor_obj, activo=True).exists():
                messages.error(request, f'El medidor {medidor_serie} ya esta asignado a otro cliente.')
                return redirect('cliente_crear')

        Cliente.objects.create(
            numero_cliente=numero_cliente,
            direccion=direccion,
            comuna=comuna,
            referencia=referencia,
            medidor_actual=medidor_obj,
            activo=True,
        )
        messages.success(request, f'Cliente {numero_cliente} creado correctamente.')
        return redirect('clientes_list')

    return render(request, 'clientes/crear.html')


@login_required
@role_required(['ADMIN'])
def cliente_editar_view(request, pk):
    """Editar cliente (solo rol ADMIN)."""
    cliente = get_object_or_404(Cliente, pk=pk, activo=True)

    if request.method == 'POST':
        numero_cliente = request.POST.get('numero_cliente', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        comuna = request.POST.get('comuna', '').strip()
        referencia = request.POST.get('referencia', '').strip()
        medidor_serie = request.POST.get('medidor_serie', '').strip()

        if not all([numero_cliente, direccion, comuna]):
            messages.error(request, 'Numero de cliente, direccion y comuna son obligatorios.')
            return redirect('cliente_editar', pk=pk)

        if Cliente.objects.filter(numero_cliente=numero_cliente).exclude(pk=pk).exists():
            messages.error(request, f'Ya existe un cliente con numero {numero_cliente}.')
            return redirect('cliente_editar', pk=pk)

        medidor_obj = None
        if medidor_serie:
            medidor_obj = Medidor.objects.filter(serie=medidor_serie).first()
            if not medidor_obj:
                messages.error(request, f'No existe un medidor con serie {medidor_serie}.')
                return redirect('cliente_editar', pk=pk)
            if Cliente.objects.filter(medidor_actual=medidor_obj, activo=True).exclude(pk=pk).exists():
                messages.error(request, f'El medidor {medidor_serie} ya esta asignado a otro cliente.')
                return redirect('cliente_editar', pk=pk)

        cliente.numero_cliente = numero_cliente
        cliente.direccion = direccion
        cliente.comuna = comuna
        cliente.referencia = referencia
        cliente.medidor_actual = medidor_obj
        cliente.save()

        messages.success(request, f'Cliente {numero_cliente} actualizado correctamente.')
        return redirect('clientes_list')

    context = {'cliente': cliente}
    return render(request, 'clientes/editar.html', context)


@login_required
@role_required(['ADMIN'])
def cliente_eliminar_view(request, pk):
    """Elimina logicamente un cliente (solo rol ADMIN)."""
    if request.method != 'POST':
        return redirect('clientes_list')

    cliente = get_object_or_404(Cliente, pk=pk, activo=True)
    cliente.activo = False
    cliente.save(update_fields=['activo'])
    messages.success(request, f'Cliente {cliente.numero_cliente} eliminado correctamente.')
    return redirect('clientes_list')


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
@admin_or_administrativo
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
    busqueda = request.GET.get('q', '')
    
    # Query base
    movimientos = MovimientoInventario.objects.all().select_related(
        'origen', 'destino', 'responsable', 'orden_trabajo'
    ).prefetch_related('items').order_by('-fecha_hora')
    
    # Aplicar filtros
    if tipo_filtro:
        movimientos = movimientos.filter(tipo=tipo_filtro)
    
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d')
            movimientos = movimientos.filter(fecha_hora__gte=fecha_desde_dt)
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d')
            movimientos = movimientos.filter(fecha_hora__lte=fecha_hasta_dt)
        except ValueError:
            pass
    
    if responsable_id:
        movimientos = movimientos.filter(responsable_id=responsable_id)
    
    if origen_id:
        movimientos = movimientos.filter(origen_id=origen_id)
    
    if destino_id:
        movimientos = movimientos.filter(destino_id=destino_id)
    
    if busqueda:
        movimientos = movimientos.filter(
            Q(observacion__icontains=busqueda) |
            Q(orden_trabajo__numero_ot__icontains=busqueda) |
            Q(responsable__nombre_interno__icontains=busqueda)
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
    
    movimientos_render = list(movimientos[:100])  # Limitar a 100 para renderizado inicial
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
        else:
            mov.item_origen_display = '-'

    context = {
        'movimientos': movimientos_render,
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
        'busqueda': busqueda,
        'tipos_movimiento': MovimientoInventario.TIPO_CHOICES,
    }
    
    return render(request, 'movimientos/list.html', context)


@login_required
@admin_or_administrativo
def movimientos_detalle_view(request, movimiento_id):
    """
    Ver detalles completos de un movimiento específico
    
    Muestra todos los items involucrados y evidencias
    """
    from inventario.models import MovimientoInventario, MovimientoItem
    
    movimiento = get_object_or_404(
        MovimientoInventario.objects.select_related(
            'origen', 'destino', 'responsable', 'orden_trabajo'
        ).prefetch_related('items'),
        id=movimiento_id
    )
    
    # Obtener items agrupados por tipo
    items = movimiento.items.all().select_related(
        'medidor', 'simcard', 'modem'
    )
    
    items_medidores = items.filter(tipo_equipo='MEDIDOR')
    items_sims = items.filter(tipo_equipo='SIM')
    items_modems = items.filter(tipo_equipo='MODEM')
    
    context = {
        'movimiento': movimiento,
        'items_medidores': items_medidores,
        'items_sims': items_sims,
        'items_modems': items_modems,
        'total_items': items.count(),
    }
    
    return render(request, 'movimientos/detalle.html', context)


@login_required
@admin_or_administrativo
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
        equipo_nombre = f"Medidor {equipo.numero_serie}"
    elif tipo_equipo == 'SIM':
        equipo = get_object_or_404(SimCard, id=equipo_id)
        equipo_nombre = f"SIM {equipo.iccid}"
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
        'movimiento__orden_trabajo'
    ).order_by('-movimiento__fecha_hora')
    
    context = {
        'equipo': equipo,
        'equipo_nombre': equipo_nombre,
        'tipo_equipo': tipo_equipo,
        'items': items,
        'total_movimientos': items.count(),
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
    
    try:
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
        
        # Buscar orden de trabajo si existe
        orden = None
        if ot_numero:
            try:
                orden = OrdenTrabajo.objects.get(numero_ot=ot_numero)
            except:
                logger.warning(f"Orden de trabajo no encontrada: {ot_numero}")
        
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
            origen=origen,
            destino=destino,
            responsable=responsable,
            orden_trabajo=orden,
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
                    equipo_obj = Medidor.objects.get(numero_serie=identificador)
                except Medidor.DoesNotExist:
                    errores_equipos.append(f"Medidor {identificador} no encontrado")
                    continue
            elif tipo_eq == 'SIM':
                try:
                    equipo_obj = SimCard.objects.get(iccid=identificador)
                except SimCard.DoesNotExist:
                    errores_equipos.append(f"SIM {identificador} no encontrada")
                    continue
            elif tipo_eq == 'MODEM':
                try:
                    equipo_obj = Modem.objects.get(imei=identificador)
                except Modem.DoesNotExist:
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
        
        return JsonResponse({
            'success': True,
            'movimiento_id': movimiento.id,
            'items_creados': items_creados,
            'errores': errores_equipos if errores_equipos else None,
            'message': 'Movimiento registrado exitosamente'
        })
        
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

ROLES_REPORTES = ('ADMIN', 'ADMINISTRATIVO', 'SUPERVISOR')


@login_required
def reportes_moreapp_list(request):
    """Lista de registros sincronizados desde carpetas de MoreApp."""
    from ordenes_trabajo.models import IntegracionMoreApp

    if request.user.rol not in ROLES_REPORTES:
        messages.error(request, 'No tienes permiso para acceder a Reportes.')
        return redirect('dashboard')

    qs_base = IntegracionMoreApp.objects.all().order_by('-fecha_recepcion')

    # Filtros
    estado = request.GET.get('estado', '')
    alerta = request.GET.get('alerta', '')
    q = request.GET.get('q', '')
    formulario = request.GET.get('formulario', '')

    qs = qs_base
    if estado:
        qs = qs.filter(estado_sincronizacion=estado)
    if alerta == '1':
        qs = qs.filter(alerta_doble_trabajo=True)
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

    registros = list(qs)
    if request.user.rol == 'ADMIN':
        for reg in registros:
            reg.delete_url = f'/reportes/moreapp/{reg.pk}/eliminar/'
    else:
        for reg in registros:
            reg.delete_url = ''

    context = {
        'registros': registros,
        'estado_actual': estado,
        'alerta_actual': alerta,
        'q': q,
        'formulario_actual': formulario,
        'formularios': formularios,
        'total': qs.count(),
        'puede_eliminar_reportes': request.user.rol == 'ADMIN',
        'pendientes': IntegracionMoreApp.objects.filter(estado_sincronizacion='PENDIENTE').count(),
        'alertas': IntegracionMoreApp.objects.filter(alerta_doble_trabajo=True).count(),
        'errores': IntegracionMoreApp.objects.filter(
            estado_sincronizacion__in=('ERROR_JSON', 'ERROR_LECTURA', 'ERROR')
        ).count(),
        'estados_choices': IntegracionMoreApp.ESTADO_CHOICES,
    }
    return render(request, 'reportes/integraciones_list.html', context)


@login_required
def reportes_moreapp_detalle(request, pk):
    """Detalle de un registro MoreApp individual."""
    from ordenes_trabajo.models import IntegracionMoreApp
    from integraciones.reader import leer_carpetas

    if request.user.rol not in ROLES_REPORTES:
        messages.error(request, 'No tienes permiso para acceder a Reportes.')
        return redirect('dashboard')

    registro = get_object_or_404(IntegracionMoreApp, pk=pk)
    if request.user.rol == 'ADMIN':
        registro_delete_url = f'/reportes/moreapp/{registro.pk}/eliminar/'
    else:
        registro_delete_url = ''
    return render(request, 'reportes/integracion_detalle.html', {
        'registro': registro,
        'registro_delete_url': registro_delete_url,
    })


@login_required
def reportes_moreapp_sincronizar(request):
    """Dispara la sincronización manual desde el navegador."""
    from integraciones.reader import leer_carpetas

    if request.user.rol not in ROLES_REPORTES:
        messages.error(request, 'No tienes permiso.')
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('reportes_moreapp_list')

    stats = leer_carpetas()
    messages.success(
        request,
        f'Sincronización completada — Nuevos: {stats["nuevos"]} | '
        f'Duplicados: {stats["duplicados"]} | '
        f'Alertas: {stats["alertas"]} | '
        f'Errores: {stats["errores"]}'
    )
    return redirect('reportes_moreapp_list')


@login_required
@role_required(['ADMIN'])
def reportes_moreapp_eliminar(request, pk):
    """Elimina un registro de reportes MoreApp. Uso exclusivo para limpieza de pruebas."""
    from ordenes_trabajo.models import IntegracionMoreApp

    if request.method != 'POST':
        return redirect('reportes_moreapp_list')

    registro = get_object_or_404(IntegracionMoreApp, pk=pk)
    identificador = registro.moreapp_submission_id
    registro.delete()
    messages.success(request, f'Registro MoreApp {identificador} eliminado correctamente.')

    destino = request.POST.get('next', '').strip()
    if destino:
        return redirect(destino)
    return redirect('reportes_moreapp_list')
