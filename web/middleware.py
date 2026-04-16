import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect


class AbsoluteSessionTimeoutMiddleware:
    """Cierra sesion al cumplir tiempo maximo absoluto desde login."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            ttl = int(getattr(settings, 'ABSOLUTE_SESSION_TIMEOUT_SECONDS', 28800))
            now_ts = int(time.time())
            login_ts = request.session.get('auth_login_ts')

            if not login_ts:
                # Sesiones antiguas sin marca quedan acotadas desde este acceso.
                request.session['auth_login_ts'] = now_ts
            else:
                try:
                    elapsed = now_ts - int(login_ts)
                except (TypeError, ValueError):
                    elapsed = ttl + 1

                if elapsed >= ttl:
                    logout(request)
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse(
                            {
                                'success': False,
                                'message': 'Tu sesión expiró por seguridad (8 horas). Inicia sesión nuevamente.',
                            },
                            status=401,
                        )
                    messages.warning(request, 'Tu sesión expiró por seguridad (8 horas). Inicia sesión nuevamente.')
                    return redirect('login')

        return self.get_response(request)
