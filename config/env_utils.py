# coding: utf-8
"""Helpers de configuración segura (sin secretos embebidos)."""

import os

from django.core.exceptions import ImproperlyConfigured


def require_env(var_name):
    """Exige variable de entorno; falla si falta o está vacía."""
    value = (os.environ.get(var_name) or '').strip()
    if not value:
        raise ImproperlyConfigured(
            'Falta la variable de entorno obligatoria %s. '
            'Definirla en Passenger / Hostingplus (ver .env.example).' % var_name
        )
    return value
