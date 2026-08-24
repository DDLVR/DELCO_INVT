"""Captura de errores 500 con código de referencia (sin filtrar stack al usuario)."""
from __future__ import annotations

import logging
import traceback
import uuid

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import requires_csrf_token

logger = logging.getLogger('django.request')


def _quiere_json(request) -> bool:
    accept = (request.headers.get('Accept') or '').lower()
    if 'application/json' in accept:
        return True
    return (request.headers.get('X-Requested-With') or '') == 'XMLHttpRequest'


def _es_staff_interno(request) -> bool:
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'rol', None) in {'ADMIN', 'ADMINISTRATIVO'} or getattr(user, 'is_superuser', False)


class CaptureServerErrorMiddleware:
    """
    Asocia un código corto a cada excepción no controlada.
    El detalle completo queda en logs; la página 500 muestra el código.
    Staff interno ve también el tipo/mensaje (sin traceback).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        error_id = uuid.uuid4().hex[:10].upper()
        request.delco_error_id = error_id
        request.delco_error_type = exception.__class__.__name__
        request.delco_error_message = str(exception)[:500]
        logger.error(
            'DELCO_ERROR_ID=%s path=%s method=%s user=%s\n%s',
            error_id,
            getattr(request, 'path', ''),
            getattr(request, 'method', ''),
            getattr(getattr(request, 'user', None), 'pk', None),
            traceback.format_exc(),
        )
        # Devolver None para que Django siga el flujo normal (handler500 / DEBUG page).
        return None


@requires_csrf_token
def server_error_view(request, template_name='500.html'):
    """Vista 500 amigable con código de referencia."""
    error_id = getattr(request, 'delco_error_id', None) or '—'
    payload = {
        'success': False,
        'error_id': error_id,
        'message': (
            f'Error interno del servidor (código {error_id}). '
            'El detalle quedó registrado; indica este código a soporte.'
        ),
    }
    if _es_staff_interno(request):
        tip = getattr(request, 'delco_error_type', '') or ''
        msg = getattr(request, 'delco_error_message', '') or ''
        if tip or msg:
            payload['debug_hint'] = f'{tip}: {msg}'.strip(': ')

    if _quiere_json(request):
        return JsonResponse(payload, status=500)

    context = {
        'error_id': error_id,
        'debug_hint': payload.get('debug_hint', ''),
        'mostrar_hint': bool(payload.get('debug_hint')),
    }
    try:
        return render(request, template_name, context, status=500)
    except Exception:
        body = (
            f'<h1>Error interno</h1>'
            f'<p>Código: <strong>{error_id}</strong></p>'
            f'<p>El detalle quedó en los logs del servidor.</p>'
        )
        if context.get('mostrar_hint'):
            body += f'<p><code>{context["debug_hint"]}</code></p>'
        return HttpResponse(body, status=500, content_type='text/html; charset=utf-8')
