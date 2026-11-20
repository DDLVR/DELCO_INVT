"""Listados. Importar desde aquí; no copiar el bloque en la vista.

Ejemplo en uso: Tareas MoreApp, validación, pendientes y trabajos terminados.
Una pantalla nueva llama la función y cambia solo lo que dice «Reutilizar».
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from django.core.paginator import Paginator
from django.db.models import Count


def parse_fecha_iso(valor: Any):
    """Fecha YYYY-MM-DD, o None. Reutilizar: otro desde/hasta. No recorta espacios."""
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def fecha_legible(iso: Any) -> str:
    """YYYY-MM-DD a dd/mm/aaaa. Reutilizar: la pastilla de una fecha. Si no parsea, deja el texto."""
    parsed = parse_fecha_iso(iso)
    if parsed is None:
        return iso or ""
    return parsed.strftime("%d/%m/%Y")


def paginar_consulta(request, queryset, opciones: Sequence[int] = (25, 50, 100), default: int = 50):
    """Página un listado. Reutilizar: otra grilla; cambia opciones y el default (25, 50, 100 y 50)."""
    try:
        per_page = int(request.GET.get("per_page") or default)
    except (TypeError, ValueError):
        per_page = default
    if per_page not in opciones:
        per_page = default
    page_obj = Paginator(queryset, per_page).get_page(request.GET.get("page") or 1)
    return page_obj, per_page


def consulta_sin_pagina(params):
    """GET sin page. Reutilizar: el enlace de la página siguiente."""
    consulta = params.copy()
    consulta.pop("page", None)
    return consulta


def leer_textos_get(request, claves, minusculas=()):
    """Textos del GET, recortados. Reutilizar: pasa las claves y cuáles van en minúscula."""
    datos = {clave: (request.GET.get(clave) or "").strip() for clave in claves}
    for clave in minusculas:
        if clave in datos:
            datos[clave] = datos[clave].lower()
    return datos


def quitar_de_consulta(params, *claves: str) -> str:
    """Querystring sin page ni esas claves. Reutilizar: el enlace Quitar de un filtro."""
    consulta = consulta_sin_pagina(params)
    for clave in claves:
        consulta.pop(clave, None)
    return consulta.urlencode()


def pastilla_filtro(params, claves, titulo: str, valor: Any) -> Optional[Dict[str, str]]:
    """Una pastilla, o None si va vacía. Reutilizar: claves a quitar, título y texto visible."""
    texto = (valor or "").strip()
    if not texto:
        return None
    return {
        "titulo": titulo,
        "valor": texto,
        "quitar": quitar_de_consulta(params, *claves),
    }


def conteo_por_campo(qs, campo: str = "estado", alias: str = "c") -> Dict[Any, int]:
    """Filas por valor de un campo. Reutilizar: el campo y el alias del conteo (c o n)."""
    return {
        row[campo]: row[alias]
        for row in qs.values(campo).annotate(**{alias: Count("id")})
    }


def top_por_campo(qs, campo: str, limite: Optional[int] = 8, alias: str = "n", omitir_vacio: bool = False):
    """Valores más repetidos. Reutilizar: campo, tope y si el vacío cuenta."""
    consulta = qs.exclude(**{campo: ""}) if omitir_vacio else qs
    filas = consulta.values(campo).annotate(**{alias: Count("id")}).order_by("-%s" % alias)
    if limite:
        filas = filas[:limite]
    return list(filas)


def es_ajax(request) -> bool:
    """La petición espera JSON. Reutilizar: un guardado que no recarga la página."""
    return (
        (request.headers.get("X-Requested-With") or "") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "").lower()
    )
