"""
Webhook legacy de MoreApp (compatibilidad de URL).

El flujo real es:
- Carpetas / sync: integraciones.reader + ordenes_trabajo.IntegracionMoreApp
- Webhook realtime: web.views.movimientos_importar_moreapp_webhook → procesar_payload_moreapp
"""
import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _webhook_secret_ok(request):
    expected = str(getattr(settings, 'MOREAPP_WEBHOOK_SECRET', '') or '').strip()
    if not expected:
        return False
    provided = (request.headers.get('X-MoreApp-Secret', '') or '').strip()
    auth_header = (request.headers.get('Authorization', '') or '').strip()
    if not provided and auth_header.lower().startswith('bearer '):
        provided = auth_header[7:].strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


@csrf_exempt
@require_http_methods(["POST"])
def webhook_moreapp(request):
    """
    Endpoint legacy: exige el mismo secreto y responde 410 Gone.
    Usar `/api/moreapp-webhook/` para sincronización en tiempo real.
    """
    if not _webhook_secret_ok(request):
        return JsonResponse({'success': False, 'error': 'Webhook no autorizado'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON inválido'}, status=400)

    orden_id = payload.get('orden_id') if isinstance(payload, dict) else None
    logger.info(
        'Webhook MoreApp legacy rechazado (410). orden_id=%s',
        orden_id,
    )
    return JsonResponse(
        {
            'success': False,
            'error': (
                'Endpoint legacy deshabilitado. Use /api/moreapp-webhook/ '
                'para sincronización en tiempo real.'
            ),
            'orden_id': orden_id,
            'deprecated': True,
        },
        status=410,
    )
