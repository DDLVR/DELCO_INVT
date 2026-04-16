import json
import hashlib
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .models import IntegracionMoreAppLog


@csrf_exempt
@require_http_methods(["POST"])
def webhook_moreapp(request):
    """
    Endpoint legacy de MoreApp (compatibilidad).
    
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

        if not orden_id:
            raise ValueError('orden_id requerido')

        # Módulo de órdenes retirado: conservar referencia histórica sin FK.
        log.orden_asociada_ref = int(orden_id)
        log.adjunto_creado_ref = None

        # Hash del archivo si existe (solo trazabilidad en log)
        archivo_base64 = payload.get('archivo_base64')
        archivo_hash = ''
        if archivo_base64:
            archivo_hash = hashlib.sha256(archivo_base64.encode()).hexdigest()

        payload_ext = dict(payload)
        payload_ext['archivo_nombre_resuelto'] = archivo_nombre
        payload_ext['archivo_url'] = archivo_url
        payload_ext['tipo_adjunto'] = tipo_adjunto
        payload_ext['archivo_hash'] = archivo_hash
        log.payload_crudo = payload_ext

        # Actualizar log
        log.estado = 'PROCESADO'
        log.save()
        
        return JsonResponse({
            'success': True,
            'mensaje': f'Registro legacy recibido para OT #{orden_id}',
            'adjunto_id': None,
            'log_id': log.id
        }, status=201)
    
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
