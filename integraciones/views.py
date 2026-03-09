import json
import hashlib
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from ordenes_trabajo.models import OrdenTrabajo, AdjuntoOrden
from .models import IntegracionMoreAppLog


@csrf_exempt
@require_http_methods(["POST"])
def webhook_moreapp(request):
    """
    Endpoint para recibir archivos FPT desde MoreApp.
    
    Formato esperado del payload:
    {
        "orden_id": 123,
        "archivo": {
            "nombre": "foto.jpg",
            "url": "https://moreapp.com/...",
            "tipo": "FOTO" o "FPT",
            "metadata": {...}
        }
    }
    
    O si viene el archivo codificado en base64:
    {
        "orden_id": 123,
        "archivo_nombre": "foto.jpg",
        "archivo_base64": "iVBORw0KGgo...",
        "tipo": "FOTO"
    }
    """
    
    try:
        # Parsear payload
        payload = json.loads(request.body.decode('utf-8'))
        
        # Crear log
        log = IntegracionMoreAppLog.objects.create(
            estado='RECIBIDO',
            payload_crudo=payload
        )
        
        # Obtener datos
        orden_id = payload.get('orden_id')
        archivo_info = payload.get('archivo', {})
        archivo_nombre = payload.get('archivo_nombre') or archivo_info.get('nombre')
        archivo_url = archivo_info.get('url')
        tipo_adjunto = payload.get('tipo', 'FPT')
        
        # Validar que exista la orden
        if not orden_id:
            raise ValueError('orden_id requerido')
        
        orden = OrdenTrabajo.objects.get(pk=orden_id)
        log.orden_asociada = orden
        
        # Crear adjunto (versión simple)
        # En producción, descargar el archivo desde URL si viene
        adjunto = AdjuntoOrden.objects.create(
            orden=orden,
            tipo=tipo_adjunto,
            nombre_archivo=archivo_nombre or f'adjunto_{orden_id}_{log.id}',
            url_externa=archivo_url,
            metadata={
                'origen': 'MoreApp',
                'payload_original': payload
            }
        )
        
        # Calcular hash si se proporciona archivo base64
        archivo_base64 = payload.get('archivo_base64')
        if archivo_base64:
            # En versión real, decodificar y guardar el archivo
            # Por ahora solo registrar
            adjunto.hash_archivo = hashlib.sha256(
                archivo_base64.encode()
            ).hexdigest()
            adjunto.save()
        
        # Actualizar log
        log.estado = 'PROCESADO'
        log.adjunto_creado = adjunto
        log.save()
        
        return JsonResponse({
            'success': True,
            'mensaje': f'Adjunto recibido para OT #{orden_id}',
            'adjunto_id': adjunto.id,
            'log_id': log.id
        }, status=201)
    
    except OrdenTrabajo.DoesNotExist:
        log.estado = 'ERROR'
        log.mensaje_error = f'Orden #{orden_id} no existe'
        log.save()
        
        return JsonResponse({
            'success': False,
            'error': 'Orden no encontrada'
        }, status=404)
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Payload JSON inválido'
        }, status=400)
    
    except Exception as e:
        log = IntegracionMoreAppLog.objects.create(
            estado='ERROR',
            payload_crudo=payload if 'payload' in locals() else {},
            mensaje_error=str(e)
        )
        
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
