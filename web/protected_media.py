# coding: utf-8
"""Servir archivos de media/evidencias solo a usuarios autenticados."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.static import serve as django_serve


@login_required
def serve_media(request, path):
    """Adjuntos y archivos subidos (ordenes, comprobantes, etc.)."""
    return django_serve(request, path, document_root=settings.MEDIA_ROOT)


@login_required
def serve_evidencias(request, path):
    """Evidencias de terreno bajo /registros/evidencias/."""
    return django_serve(request, path, document_root=settings.EVIDENCIAS_ROOT)
