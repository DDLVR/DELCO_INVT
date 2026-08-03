# coding: utf-8
"""Helpers de configuración (env / .env en el servidor)."""

import os

from django.core.exceptions import ImproperlyConfigured


def require_env(var_name):
    """Exige variable de entorno; falla si falta o está vacía."""
    value = (os.environ.get(var_name) or '').strip()
    if not value:
        raise ImproperlyConfigured(
            'Falta la variable de entorno obligatoria %s. '
            'Crear archivo .env en el servidor (junto a passenger_wsgi.py) '
            'o definirla en Setup Python App → Environment variables. '
            'Plantilla: .env.example' % var_name
        )
    return value
