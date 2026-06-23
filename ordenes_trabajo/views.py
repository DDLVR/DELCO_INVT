from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

from .models import OrdenTrabajo, AdjuntoOrden, IntegracionMoreApp
from .serializers import OrdenTrabajoSerializer
from usuarios.models import Usuario
from clientes.models import Cliente
from inventario.models import Medidor, SimCard, Modem


@login_required
def ordenes_list_view(request):
    """
    Lista de órdenes de trabajo con filtros
    """
    usuario = request.user
    
    # Base queryset según rol
    if usuario.rol in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
        ordenes = OrdenTrabajo.objects.all()
    elif usuario.rol == 'TECNICO':
        ordenes = OrdenTrabajo.objects.filter(tecnico_responsable=usuario)
    else:
        ordenes = OrdenTrabajo.objects.none()
    
    # Aplicar filtros
    estado_filtro = request.GET.get('estado', '')
    tipo_filtro = request.GET.get('tipo_trabajo', '')
    tecnico_filtro = request.GET.get('tecnico', '')
    cliente_filtro = request.GET.get('cliente', '')
    buscar = request.GET.get('buscar', '')
    
    if estado_filtro:
        ordenes = ordenes.filter(estado=estado_filtro)
    
    if tipo_filtro:
        ordenes = ordenes.filter(tipo_trabajo=tipo_filtro)
    
    if tecnico_filtro:
        ordenes = ordenes.filter(tecnico_responsable_id=tecnico_filtro)
    
    if cliente_filtro:
        ordenes = ordenes.filter(cliente_id=cliente_filtro)
    
    if buscar:
        ordenes = ordenes.filter(
            Q(titulo__icontains=buscar) |
            Q(descripcion__icontains=buscar) |
            Q(cliente__numero_cliente__icontains=buscar)
        )
    
    ordenes = ordenes.select_related(
        'tecnico_responsable', 
        'cliente', 
        'medidor', 
        'simcard', 
        'modem'
    ).order_by('-fecha_creacion')
    
    # Obtener opciones para filtros
    tecnicos = Usuario.objects.filter(rol='TECNICO', is_active=True)
    clientes = Cliente.objects.all()
    
    context = {
        'ordenes': ordenes,
        'tecnicos': tecnicos,
        'clientes': clientes,
        'estados': OrdenTrabajo.ESTADO_CHOICES,
        'tipos_trabajo': OrdenTrabajo.TIPO_TRABAJO_CHOICES,
        'estado_filtro': estado_filtro,
        'tipo_filtro': tipo_filtro,
        'tecnico_filtro': tecnico_filtro,
        'cliente_filtro': cliente_filtro,
        'buscar': buscar,
    }
    
    return render(request, 'ordenes/list.html', context)


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
            if cliente_id:
                orden.cliente = Cliente.objects.get(id=cliente_id)
            
            # Técnico responsable
            tecnico_id = request.POST.get('tecnico_responsable')
            orden.tecnico_responsable = Usuario.objects.get(id=tecnico_id)
            
            # Observaciones iniciales (los equipos se registran después)
            orden.observaciones_tecnicas = request.POST.get('observaciones_tecnicas', '')
            
            orden.estado = 'PENDIENTE'
            orden.creada_por = request.user
            orden.fecha_asignacion = timezone.now()
            
            orden.save()
            
            messages.success(request, f'Orden #{orden.id} creada con estado PENDIENTE y asignada a {orden.tecnico_responsable.nombre_interno}')
            return redirect('orden_detalle', pk=orden.id)
            
        except Exception as e:
            messages.error(request, f'Error al crear orden: {str(e)}')
    
    # GET - Mostrar formulario
    tecnicos = Usuario.objects.filter(rol='TECNICO', is_active=True)
    clientes = Cliente.objects.all()
    
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
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    
    # Verificar permisos
    usuario = request.user
    if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
        if usuario.rol == 'TECNICO' and orden.tecnico_responsable != usuario:
            messages.error(request, 'No tienes acceso a esta orden')
            return redirect('ordenes_list')
    
    # Obtener adjuntos
    adjuntos = orden.adjuntos.all()
    
    # Obtener integraciones MoreApp
    sincronizaciones = orden.sincronizaciones_moreapp.all()
    
    context = {
        'orden': orden,
        'adjuntos': adjuntos,
        'sincronizaciones': sincronizaciones,
        'puede_editar': usuario.rol in ['ADMIN', 'ADMINISTRATIVO'],
        'es_tecnico_responsable': orden.tecnico_responsable == usuario,
        'estados': OrdenTrabajo.ESTADO_CHOICES,
    }
    
    return render(request, 'ordenes/detalle.html', context)


@login_required
@login_required
def cambiar_estado_orden_view(request, pk):
    """
    Cambia el estado de una orden validando permisos por rol.
    """
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    nuevo_estado = request.POST.get('nuevo_estado')
    
    # Validar que el usuario tiene permiso
    if not orden.puede_cambiar_estado(request.user, nuevo_estado):
        messages.error(request, 'No tienes permiso para cambiar este estado')
        return redirect('orden_detalle', pk=pk)
    
    # Cambiar estado
    resultado = orden.cambiar_estado(request.user, nuevo_estado)
    
    if resultado['success']:
        messages.success(request, resultado['mensaje'])
    else:
        messages.error(request, resultado['mensaje'])
    
    return redirect('orden_detalle', pk=pk)


@login_required
def orden_editar_tecnico_view(request, pk):
    """
    Permite al técnico editar orden (máximo 2 veces)
    """
    orden = get_object_or_404(OrdenTrabajo, pk=pk)
    
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
        orden = get_object_or_404(OrdenTrabajo, pk=pk)
        
        # Verificar permisos
        if request.user.rol not in ['ADMIN', 'ADMINISTRATIVO'] and orden.tecnico_responsable != request.user:
            return JsonResponse({'success': False, 'message': 'No tienes permisos'}, status=403)
        
        try:
            archivo = request.FILES.get('archivo')
            tipo = request.POST.get('tipo', 'OTRO')
            
            if not archivo:
                return JsonResponse({'success': False, 'message': 'No se envió archivo'}, status=400)
            
            adjunto = AdjuntoOrden()
            adjunto.orden = orden
            adjunto.tipo = tipo
            adjunto.nombre_archivo = archivo.name
            adjunto.archivo = archivo
            adjunto.subido_por = request.user
            adjunto.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Archivo subido exitosamente',
                'adjunto_id': adjunto.id
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
        orden = get_object_or_404(OrdenTrabajo, pk=pk)
        
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
            messages.success(request, '✓ Equipos registrados correctamente en la orden')
            
        except Exception as e:
            messages.error(request, f'❌ Error al registrar equipos: {str(e)}')
        
        return redirect('orden_detalle', pk=pk)
    
    return redirect('orden_detalle', pk=pk)


# ========================================
# API REST para ViewSet
# ========================================

class OrdenTrabajoViewSet(viewsets.ModelViewSet):
    """
    API REST para gestionar Órdenes de Trabajo
    """

    serializer_class = OrdenTrabajoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        usuario = self.request.user

        if usuario.rol in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
            return OrdenTrabajo.objects.all()
        elif usuario.rol == 'TECNICO':
            return OrdenTrabajo.objects.filter(tecnico_responsable=usuario)
        
        return OrdenTrabajo.objects.none()

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
            
            integracion.estado_sincronizacion = 'EXITOSO'
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
