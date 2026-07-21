"""Nombres únicos y legibles para archivos exportados."""

import os

from django.utils import timezone


def nombre_exportacion_con_fecha(nombre_archivo: str) -> str:
    """Agrega fecha y hora antes de la extensión.

    Ejemplo: ``clientes_completos_2026-07-21_15-29-45.xlsx``.
    El formato evita caracteres inválidos en Windows y ordena cronológicamente.
    """
    ahora = timezone.now()
    if timezone.is_aware(ahora):
        ahora = timezone.localtime(ahora)
    base, extension = os.path.splitext(nombre_archivo)
    timestamp = ahora.strftime('%Y-%m-%d_%H-%M-%S')
    return f'{base}_{timestamp}{extension}'
