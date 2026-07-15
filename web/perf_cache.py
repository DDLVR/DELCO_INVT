"""Cachés de corta duración para aliviar páginas con mucho volumen."""

from __future__ import annotations

import sys

from django.core.cache import cache

TTL_CORTO = 60
TTL_MEDIO = 180


def _en_tests() -> bool:
    """Evita que LocMem contamine casos de prueba del mismo proceso."""
    return any(arg == 'test' or arg.startswith('test') for arg in sys.argv)


def cache_get_or_set(key: str, factory, ttl: int = TTL_CORTO):
    if _en_tests():
        return factory()
    valor = cache.get(key)
    if valor is not None:
        return valor
    valor = factory()
    cache.set(key, valor, ttl)
    return valor


def cache_invalidate(*keys: str) -> None:
    for key in keys:
        cache.delete(key)
