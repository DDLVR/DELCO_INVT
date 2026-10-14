"""Respuestas JSON compartidas para los módulos MoreApp API."""

from __future__ import annotations

import re

from django.http import JsonResponse

from .moreapp_api import MoreAppApiConfigError, MoreAppApiError, get_customer_id

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def assert_safe_id(value: str, nombre: str = "id") -> str:
    raw = (value or "").strip()
    if not _SAFE_ID.match(raw):
        raise MoreAppApiConfigError("%s inválido." % nombre)
    return raw


def json_ok(data, *, modulo: str, operacion: str) -> JsonResponse:
    customer_id = ""
    try:
        customer_id = get_customer_id()
    except Exception:
        customer_id = ""
    return JsonResponse(
        {
            "success": True,
            "module": modulo,
            "operation": operacion,
            "customerId": customer_id,
            "data": data,
        },
        status=200,
    )


def json_error(exc: Exception, *, modulo: str, operacion: str) -> JsonResponse:
    status = 500
    if isinstance(exc, MoreAppApiConfigError):
        status = 400
    elif isinstance(exc, MoreAppApiError):
        status = 502
    return JsonResponse(
        {
            "success": False,
            "module": modulo,
            "operation": operacion,
            "error": str(exc),
        },
        status=status,
    )
