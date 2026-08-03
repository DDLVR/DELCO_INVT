"""
Webhook legacy de MoreApp (compatibilidad de URL).

El flujo real es:
- Carpetas / sync: integraciones.reader + ordenes_trabajo.IntegracionMoreApp
- Webhook realtime: web.views.movimientos_importar_moreapp_webhook → procesar_payload_moreapp
"""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def webhook_moreapp(request):
    """
    Endpoint legacy: acepta el POST, no persiste en BD y redirige al caller
    hacia el webhook operativo (`/api/moreapp-webhook/`).
    """
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON inválido'}, status=400)

    orden_id = payload.get('orden_id')
    logger.info(
        'Webhook MoreApp legacy recibido (sin persistencia). orden_id=%s keys=%s',
        orden_id,
        list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
    )
    return JsonResponse(
        {
            'success': True,
            'mensaje': (
                'Endpoint legacy. Use /api/moreapp-webhook/ para sincronización '
                'en tiempo real (IntegracionMoreApp).'
            ),
            'orden_id': orden_id,
            'deprecated': True,
        },
        status=200,
    )
