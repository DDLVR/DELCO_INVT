"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings

from web.protected_media import serve_evidencias, serve_media

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('web.urls')),
    path('integraciones/', include('integraciones.urls')),
    # Media y evidencias: requieren sesión (no públicos)
    re_path(r'^media/(?P<path>.*)$', serve_media, name='protected_media'),
    re_path(
        r'^registros/evidencias/(?P<path>.*)$',
        serve_evidencias,
        name='protected_evidencias',
    ),
]

if not settings.DEBUG:
    # Fallback estáticos en hosting compartido (WhiteNoise también cubre esto).
    from django.contrib.staticfiles.views import serve as staticfiles_serve

    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', staticfiles_serve, {'insecure': True}),
    ]
