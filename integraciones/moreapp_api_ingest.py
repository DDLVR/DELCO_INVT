# coding: utf-8
"""Persiste submissions de la API MoreApp usando el extractor existente (reader)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_INGEST = "moreapp:api_ingest"
_LOCK_INGEST = "moreapp:api_ingest_lock"
_PAGE_SIZE = 50


def _items(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("elements", "content", "items", "submissions"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        data = raw.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def asegurar_payload_api(item: Dict[str, Any], form_name: str = "") -> Dict[str, Any]:
    """Completa id/info/meta/data para procesar_payload_moreapp."""
    payload = dict(item)
    if not payload.get("id"):
        payload["id"] = str(item.get("_id") or item.get("submissionId") or "").strip()
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    info = dict(info)
    if form_name and not str(info.get("formName") or "").strip():
        info["formName"] = form_name
    payload["info"] = info
    if not isinstance(payload.get("meta"), dict):
        payload["meta"] = {}
    if not isinstance(payload.get("data"), dict):
        payload["data"] = {}
    return payload


def ingest_submission_items(
    items: Iterable[Dict[str, Any]],
    form_name: str = "",
    aplicar_operativo: bool = False,
    max_nuevos: int = 50,
) -> Dict[str, int]:
    """Crea IntegracionMoreApp para submissions nuevas. Idempotente por id."""
    stats = {"nuevos": 0, "omitidos": 0, "errores": 0}
    lote = [item for item in items if isinstance(item, dict)]
    if not lote:
        return stats

    from ordenes_trabajo.models import IntegracionMoreApp
    from integraciones.reader import procesar_payload_moreapp

    ids = []
    for item in lote:
        sid = str(item.get("id") or item.get("_id") or "").strip()
        if sid:
            ids.append(sid)
    existentes = set()
    if ids:
        existentes = set(
            IntegracionMoreApp.objects.filter(moreapp_submission_id__in=ids).values_list(
                "moreapp_submission_id",
                flat=True,
            )
        )

    for item in lote:
        sid = str(item.get("id") or item.get("_id") or "").strip()
        if not sid:
            stats["omitidos"] += 1
            continue
        ya_existe = sid in existentes
        if ya_existe and not aplicar_operativo:
            stats["omitidos"] += 1
            continue
        if (not ya_existe) and stats["nuevos"] >= max_nuevos:
            stats["omitidos"] += 1
            continue
        payload = asegurar_payload_api(item, form_name)
        try:
            resultado = procesar_payload_moreapp(
                payload,
                ruta_context="api",
                aplicar_operativo=aplicar_operativo,
            )
        except Exception:
            logger.exception("Ingesta MoreApp API falló id=%s", sid)
            stats["errores"] += 1
            continue
        estado = resultado.get("resultado")
        if estado == "nuevo":
            stats["nuevos"] += 1
            existentes.add(sid)
        elif estado == "error":
            stats["errores"] += 1
        else:
            stats["omitidos"] += 1

    if stats["nuevos"]:
        try:
            cache.delete_many(["operacional:codigos_moreapp", "operacional:cliente_ids"])
        except Exception:
            pass
    return stats


def ingest_asignados_si_corresponde(*, aplicar_operativo: bool = False) -> Optional[Dict[str, int]]:
    """Una página reciente por formulario asignado. Cacheada para no repetir el REST."""
    if not bool(getattr(settings, "MOREAPP_API_ENABLED", False)):
        return None
    from web.perf_cache import TTL_MEDIO, cache_get_or_set

    if cache.get(_LOCK_INGEST):
        return None

    def _run():
        cache.set(_LOCK_INGEST, 1, 45)
        try:
            return _ingest_asignados(aplicar_operativo=aplicar_operativo)
        finally:
            cache.delete(_LOCK_INGEST)

    return cache_get_or_set(_CACHE_INGEST, _run, TTL_MEDIO)


def _ingest_asignados(*, aplicar_operativo: bool) -> Dict[str, int]:
    from integraciones.models import MoreAppFormularioAsignado
    from integraciones.moreapp_api import MoreAppApiConfigError, MoreAppApiError, list_submissions

    total = {"nuevos": 0, "omitidos": 0, "errores": 0}
    asignados = list(MoreAppFormularioAsignado.objects.values("form_id", "form_name").distinct())
    for row in asignados:
        form_id = str(row.get("form_id") or "").strip()
        nombre = str(row.get("form_name") or form_id).strip()
        if not form_id:
            continue
        try:
            raw = list_submissions(
                form_id,
                0,
                {"pageSize": _PAGE_SIZE, "sort": [{"key": "info.date", "direction": -1}]},
            )
        except (MoreAppApiConfigError, MoreAppApiError) as exc:
            logger.warning("Ingesta MoreApp API: no se listó %s (%s)", form_id, exc)
            continue
        stats = ingest_submission_items(
            _items(raw),
            form_name=nombre,
            aplicar_operativo=aplicar_operativo,
        )
        for key in total:
            total[key] += stats.get(key, 0)
    return total
