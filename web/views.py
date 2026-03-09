from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
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


def login_view(request):
    """Autenticación de usuarios con RUT"""
    # Si ya está logueado, no mostrar login
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == "POST":
        rut = request.POST.get("username")  # RUT
        password = request.POST.get("password")
        
        # Debug: verificar si el usuario existe
        from usuarios.models import Usuario
        try:
            usuario = Usuario.objects.get(rut=rut)
            # Intentar autenticar
            user = authenticate(request, username=rut, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f"Bienvenido {usuario.nombre_interno}!")
                return redirect('dashboard')
            else:
                # El usuario existe pero la contraseña es incorrecta
                messages.error(request, "Contraseña incorrecta.")
        except Usuario.DoesNotExist:
            messages.error(request, "RUT no encontrado en el sistema.")
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
            estado_inventario__nombre='BODEGA'
        ).count()
        context['medidores_instalados'] = Medidor.objects.filter(
            estado_inventario__nombre='Instalado'
        ).count()
        
        # Inventario - SIM Cards
        context['total_sims'] = SimCard.objects.count()
        context['sims_bodega'] = SimCard.objects.filter(
            estado_inventario__nombre='BODEGA'
        ).count()
        context['sims_instaladas'] = SimCard.objects.filter(
            estado_inventario__nombre='Instalado'
        ).count()
        
        # Inventario - Modems
        context['total_modems'] = Modem.objects.count()
        context['modems_bodega'] = Modem.objects.filter(
            estado_inventario__nombre='BODEGA'
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
    
    from usuarios.models import Usuario
    from clientes.models import Cliente
    
    tipo = request.GET.get('tipo', 'medidor')
    estado_filtro = request.GET.get('estado', '')
    ubicacion_filtro = request.GET.get('ubicacion', '')
    
    # Obtener datos base
    if tipo == 'medidor':
        equipos = Medidor.objects.all()
        titulo = 'Medidores'
    elif tipo == 'sim':
        equipos = SimCard.objects.all()
        titulo = 'SIM Cards'
    elif tipo == 'modem':
        equipos = Modem.objects.all()
        titulo = 'Módems'
    else:
        equipos = Medidor.objects.all()
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
    
    # Obtener opciones para filtros
    estados_disponibles = EstadoInventario.objects.all()
    ubicaciones_disponibles = Ubicacion.objects.all()
    usuarios = Usuario.objects.filter(rol='TECNICO')  # Solo técnicos
    clientes = Cliente.objects.all()
    medidores = Medidor.objects.all().order_by('serie')  # Todos los medidores
    
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
                'medidor_id': getattr(equipo, 'medidor_id', '') or '',
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
                'cliente_id': getattr(equipo, 'cliente_id', '') or '',
                'medidor_id': getattr(equipo, 'medidor_id', '') or '',
                'observaciones': getattr(equipo, 'observaciones', '') or '',
                # No incluir campos NARANJA adicionales (marca_secundaria, retirado, etc)
            }
        else:
            # Para Medidor
            datos = {
                'id': equipo.id,
                'tipo': tipo,
                'fecha_entrega': equipo.fecha_entrega.strftime('%Y-%m-%d') if equipo.fecha_entrega else '',
                'estado_id': getattr(equipo, 'estado_inventario_id', '') or '',
                'entregado_a_id': getattr(equipo, 'entregado_a_id', '') or '',
                'cliente_id': getattr(equipo, 'cliente_id', '') or '',
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
        
        # Actualizar campos según tipo
        if tipo == 'sim':
            # Para SIM Card - campos verdes que puede modificar el administrativo
            fecha_entrega = request.POST.get('fecha_entrega', '').strip()
            estado_id = request.POST.get('estado_sim', '').strip() or request.POST.get('estado', '').strip()
            cliente_id = request.POST.get('cliente', '').strip()
            medidor_id = request.POST.get('medidor', '').strip()
            
            # Debug
            print(f'[DEBUG SIMCARD] fecha_entrega={fecha_entrega} | estado_id={estado_id}')
            print(f'[DEBUG SIMCARD] cliente_id={cliente_id} | medidor_id={medidor_id}')
            
            if fecha_entrega:
                equipo.fecha_entrega = fecha_entrega
            
            if estado_id:
                try:
                    estado_obj = EstadoInventario.objects.get(pk=int(estado_id))
                    equipo.estado_inventario = estado_obj
                except (ValueError, TypeError, EstadoInventario.DoesNotExist):
                    pass
            
            if cliente_id:
                try:
                    equipo.cliente_id = int(cliente_id)
                except (ValueError, TypeError):
                    pass
            
            if medidor_id:
                try:
                    equipo.medidor_id = int(medidor_id)
                except (ValueError, TypeError):
                    pass
        elif tipo == 'modem':
            # Para Módems - solo campos AMARILLO (editables por administrativo)
            cliente_id = request.POST.get('cliente', '').strip()
            medidor_id = request.POST.get('medidor', '').strip()
            
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
        else:
            # Para Medidor - todos los campos editables
            fecha_entrega = request.POST.get('fecha_entrega', '').strip()
            estado_id = request.POST.get('estado_medidor', '').strip()
            entregado_a_id = request.POST.get('entregado_a', '').strip()
            cliente_id = request.POST.get('cliente', '').strip()
            
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
            
            if cliente_id:
                try:
                    equipo.cliente_id = int(cliente_id)
                except (ValueError, TypeError):
                    pass
        
        # Guardar cambios
        equipo.save()
        
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
@role_required(['ADMIN', 'ADMINISTRATIVO', 'TECNICO'])
@require_http_methods(["GET"])
def inventario_exportar_view(request):
    """Exporta equipos a archivo Excel"""
    
    tipo = request.GET.get('tipo', 'medidor')
    estado_filtro = request.GET.get('estado', '')
    ubicacion_filtro = request.GET.get('ubicacion', '')
    
    # Obtener datos base
    if tipo == 'medidor':
        equipos = Medidor.objects.all()
        tipo_nombre = 'MEDIDORES'
    elif tipo == 'sim':
        equipos = SimCard.objects.all()
        tipo_nombre = 'SIM'
    elif tipo == 'modem':
        equipos = Modem.objects.all()
        tipo_nombre = 'MODEMS'
    else:
        equipos = Medidor.objects.all()
        tipo_nombre = 'MEDIDORES'
    
    # Si es TECNICO, filtrar solo su equipo
    if request.user.rol == 'TECNICO':
        if tipo == 'sim':
            # SimCard usa 'en_custodia_de'
            equipos = equipos.filter(en_custodia_de=request.user)
        else:
            # Medidor y Modem usan 'entregado_a'
            equipos = equipos.filter(entregado_a=request.user)
    
    # Aplicar filtros
    if estado_filtro:
        equipos = equipos.filter(estado_inventario_id=estado_filtro)
    
    if ubicacion_filtro:
        equipos = equipos.filter(ubicacion_actual_id=ubicacion_filtro)
    
    # Generar archivo Excel
    wb = exportar_equipos_excel(equipos, tipo_nombre)
    
    # Preparar respuesta HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    response['Content-Disposition'] = f'attachment; filename="inventario_{tipo}_{timestamp}.xlsx"'
    
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
            datos_json = request.POST.get('datos_corregidos', '{}')
            
            # Parsear datos
            if not datos_json.startswith('['):
                datos_json = '[' + datos_json + ']'
            
            datos_corregidos = json.loads(datos_json)[0]
            
            # Determinar el tipo de equipo y procesar
            tipo_equipo = importacion.tipo
            
            if tipo_equipo == 'EQUIPOS':
                # Se necesita saber qué tipo específico (MEDIDORES, SIM, MODEMS)
                # Intentar determinarlo de los datos
                resultado = _procesar_datos_corregidos(
                    datos_corregidos, 
                    request.user,
                    'MEDIDORES'  # Por defecto
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


def _procesar_datos_corregidos(datos, usuario, tipo_equipo):
    """
    Procesa datos corregidos manualmente por el usuario.
    Datos debe ser una lista: [fecha_recepcion, bodega, marca, caja, serie, modulo, ...]
    """
    try:
        from datetime import datetime as dt
        
        if tipo_equipo == 'MEDIDORES':
            if not isinstance(datos, list) or len(datos) < 5:
                return {
                    'success': False,
                    'error': 'Se requieren al menos 5 campos: fecha_recepcion, bodega, marca, caja, serie'
                }
            
            fecha_recepcion = datos[0]
            bodega_ref = datos[1]
            marca = datos[2]
            caja = str(datos[3]).strip()
            serie = str(datos[4]).strip()
            modulo = str(datos[5]).strip() if len(datos) > 5 else ''
            
            # Validaciones
            if not all([fecha_recepcion, caja, serie]):
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
            
            # Convertir fecha
            if isinstance(fecha_recepcion, str):
                fecha_recepcion = dt.strptime(fecha_recepcion, '%Y-%m-%d').date()
            elif hasattr(fecha_recepcion, 'date'):
                fecha_recepcion = fecha_recepcion.date()
            
            # Obtener o crear ubicación
            bodega = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
            if not bodega:
                bodega = Ubicacion.objects.create(
                    tipo='BODEGA_DELCO',
                    nombre='Bodega Principal'
                )
            
            # Obtener o crear estado
            estado = EstadoInventario.objects.filter(nombre='BODEGA').first()
            if not estado:
                estado = EstadoInventario.objects.create(nombre='BODEGA')
            
            # Crear medidor
            medidor = Medidor.objects.create(
                fecha_recepcion=fecha_recepcion,
                bodega=str(bodega_ref).strip() if bodega_ref else '',
                marca=str(marca).strip() if marca else '',
                caja=caja,
                serie=serie,
                modulo=modulo,
                estado_inventario=estado,
                ubicacion_actual=bodega
            )
            
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
            # Similar para Módems
            if not isinstance(datos, list) or len(datos) < 5:
                return {
                    'success': False,
                    'error': 'Se requieren al menos 5 campos: fecha_recepcion, bodega, marca, caja, serie'
                }
            
            fecha_recepcion = datos[0]
            bodega_ref = datos[1]
            marca = datos[2]
            caja = str(datos[3]).strip()
            serie = str(datos[4]).strip()
            modulo = str(datos[5]).strip() if len(datos) > 5 else ''
            
            if Modem.objects.filter(serie=serie).exists():
                return {
                    'success': False,
                    'error': f'Ya existe módem con serie {serie}'
                }
            
            if isinstance(fecha_recepcion, str):
                fecha_recepcion = dt.strptime(fecha_recepcion, '%Y-%m-%d').date()
            elif hasattr(fecha_recepcion, 'date'):
                fecha_recepcion = fecha_recepcion.date()
            
            bodega = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
            if not bodega:
                bodega = Ubicacion.objects.create(
                    tipo='BODEGA_DELCO',
                    nombre='Bodega Principal'
                )
            
            estado = EstadoInventario.objects.filter(nombre='BODEGA').first()
            if not estado:
                estado = EstadoInventario.objects.create(nombre='BODEGA')
            
            modem = Modem.objects.create(
                fecha_recepcion=fecha_recepcion,
                bodega=str(bodega_ref).strip() if bodega_ref else '',
                marca=str(marca).strip() if marca else '',
                caja=caja,
                serie=serie,
                modulo=modulo,
                estado_inventario=estado,
                ubicacion_actual=bodega
            )
            
            return {
                'success': True,
                'detalle': f'Módem serie {serie} caja {caja}'
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
    """Listar todos los usuarios separados por roles"""
    from usuarios.models import Usuario
    from django.db.models import Q
    
    usuarios = Usuario.objects.filter(is_active=True).order_by('rol', 'nombre_interno')
    
    # Agrupar por rol
    roles_order = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO', 'SUPERVISOR', 'GERENCIA', 'AUDITOR']
    usuarios_por_rol = {}
    
    for rol in roles_order:
        usuarios_por_rol[rol] = usuarios.filter(rol=rol)
    
    context = {
        'usuarios_por_rol': usuarios_por_rol,
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
        email = request.POST.get('email', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        rol = request.POST.get('rol', usuario.rol).strip()
        is_active = request.POST.get('is_active') == 'on'
        
        if not all([nombre_interno, email, rol]):
            messages.error(request, "Campos requeridos vacíos")
            return redirect('usuario_editar', pk=pk)
        
        # Verificar email único (excepto el del usuario actual)
        if Usuario.objects.filter(email=email).exclude(pk=pk).exists():
            messages.error(request, "Ya existe otro usuario con ese email")
            return redirect('usuario_editar', pk=pk)
        
        usuario.nombre_interno = nombre_interno
        usuario.email = email
        usuario.nombre = nombre
        usuario.apellido = apellido
        usuario.rol = rol
        usuario.is_active = is_active
        usuario.save()
        
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
            # Verificar que sea un usuario no-ADMIN
            if request.user.rol == 'ADMIN':
                return JsonResponse({'success': False, 'message': 'Solo administradores pueden cambiar contraseña desde el admin'})
            
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
    
    context = {
        'movimientos': movimientos[:100],  # Limitar a 100 para renderizado inicial
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
