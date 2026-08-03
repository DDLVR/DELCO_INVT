# coding: utf-8
"""Helpers de configuración (env / .env en el servidor)."""

import logging
import os

from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


def require_env(var_name):
    """Exige variable de entorno; falla si falta o está vacía."""
    value = (os.environ.get(var_name) or '').strip()
    if not value:
        raise ImproperlyConfigured(
            'Falta la variable de entorno obligatoria %s. '
            'Definirla en Passenger / Hostingplus o en el archivo .env del servidor '
            '(ver .env.example).' % var_name
        )
    return value


def env_or_default(var_name, default, *, warn=True):
    """
    Lee variable de entorno; si falta, usa default (arranque compatible con Hostingplus).
    Preferir siempre definir la variable en Passenger o .env del servidor.
    """
    value = (os.environ.get(var_name) or '').strip()
    if value:
        return value
    if warn:
        logger.warning(
            'Variable %s no definida; usando valor por defecto de compatibilidad. '
            'Configúrala en Passenger o en .env del servidor.',
            var_name,
        )
    return default
