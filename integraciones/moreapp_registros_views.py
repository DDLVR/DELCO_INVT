"""Pantallas HTML de Fase 2: ver registros (submissions) de cada formulario MoreApp."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from web.decorators import admin_or_administrativo

from .moreapp_api import (
    MoreAppApiConfigError,
    MoreAppApiError,
    download_registration_file,
    get_form,
    get_form_version,
    get_latest_submission,
    get_submission,
    list_submissions,
)
from .moreapp_catalogo_views import _extract_version_fields, _form_row, _pretty
from .moreapp_http import assert_safe_id

_PAGE_SIZE = 20
_SKIP_WIDGETS = {"header", "image"}


def _page_int(raw: Any) -> int:
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _submission_items(raw: Any) -> List[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("elements", "content", "items", "submissions"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        data = raw.get("data")
        if isinstance(data, list):
            return data
    return []


def _label_map(campos: List[Dict[str, Any]]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for campo in campos:
        data_name = str(campo.get("data_name") or "").strip()
        if not data_name or campo.get("widget") in _SKIP_WIDGETS:
            continue
        mapping[data_name] = str(campo.get("label") or data_name)
    return mapping


def _preview_keys(campos: List[Dict[str, Any]]) -> List[str]:
    keys: List[str] = []
    for campo in campos:
        data_name = str(campo.get("data_name") or "").strip()
        widget = str(campo.get("widget") or "")
        if not data_name or widget in _SKIP_WIDGETS or widget in {"photo", "signature", "file", "drawing"}:
            continue
        if data_name not in keys:
            keys.append(data_name)
        if len(keys) >= 4:
            break
    return keys


def _gridfs_file(value: Any) -> Dict[str, str]:
    text = str(value or "")
    prefix = "gridfs://registrationFiles/"
    if not text.startswith(prefix):
        return {}
    file_id = text[len(prefix) :].strip()
    if not file_id:
        return {}
    return {
        "id": file_id,
        "name": file_id,
        "content_type": "image/jpeg",
        "is_image": "1",
    }


def _is_file_item(item: Any) -> bool:
    if isinstance(item, str) and item.startswith("gridfs://registrationFiles/"):
        return True
    if not isinstance(item, dict):
        return False
    file_id = item.get("id") or item.get("fileId") or item.get("uniqueId")
    if not file_id:
        return False
    return bool(
        item.get("contentType")
        or item.get("filename")
        or item.get("fileName")
        or item.get("url")
        or str(item.get("id") or "").startswith("gridfs://")
    )


def _file_row(item: Any) -> Dict[str, str]:
    if isinstance(item, str):
        grid = _gridfs_file(item)
        if grid:
            return grid
    if not isinstance(item, dict):
        return {}
    raw_id = str(item.get("id") or item.get("fileId") or item.get("uniqueId") or "")
    grid = _gridfs_file(raw_id)
    if grid:
        return grid
    content_type = str(item.get("contentType") or "")
    return {
        "id": raw_id,
        "name": str(item.get("filename") or item.get("fileName") or item.get("name") or raw_id),
        "content_type": content_type,
        "is_image": content_type.startswith("image/") or not content_type,
    }


def _datasource_text(item: Dict[str, Any]) -> str:
    for key in ("NOMBRES", "nombre", "name", "label", "value", "emailAddress"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    parts = []
    for key, value in item.items():
        if key in {"id", "uid"} or value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            continue
        parts.append("%s: %s" % (key, value))
        if len(parts) >= 3:
            break
    return " · ".join(parts) if parts else str(item.get("id") or "")


def _format_value(value: Any) -> Dict[str, Any]:
    if value in (None, ""):
        return {"text": "", "files": []}
    if isinstance(value, list):
        files: List[Dict[str, str]] = []
        texts: List[str] = []
        for item in value:
            if _is_file_item(item):
                files.append(_file_row(item))
            elif isinstance(item, dict):
                texts.append(_datasource_text(item) or json.dumps(item, ensure_ascii=False))
            elif item not in (None, ""):
                texts.append(str(item))
        return {"text": ", ".join(texts), "files": files}
    if isinstance(value, dict):
        if _is_file_item(value):
            return {"text": "", "files": [_file_row(value)]}
        lat = value.get("lat") if value.get("lat") is not None else value.get("latitude")
        lng = value.get("lng") if value.get("lng") is not None else value.get("longitude")
        if lat is not None and lng is not None:
            return {"text": "%s, %s" % (lat, lng), "files": []}
        return {"text": _datasource_text(value), "files": []}
    if isinstance(value, bool):
        return {"text": "Sí" if value else "No", "files": []}
    grid = _gridfs_file(value)
    if grid:
        return {"text": "", "files": [grid]}
    return {"text": str(value), "files": []}


def _format_when(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) or (isinstance(value, str) and str(value).isdigit()):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp = stamp / 1000.0
        try:
            return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return str(value)
    text = str(value)
    if text.endswith("Z") and "T" in text:
        return text.replace("T", " ").replace("Z", "").split(".")[0]
    return text


def _info_meta(item: Dict[str, Any]) -> Tuple[str, str, str]:
    info = item.get("info") if isinstance(item.get("info"), dict) else {}
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    created = _format_when(
        info.get("date")
        or info.get("created")
        or meta.get("created")
        or meta.get("lastUpdated")
        or ""
    )
    user = str(
        info.get("userName")
        or info.get("email")
        or meta.get("createdBy")
        or info.get("userId")
        or ""
    )
    status = str(info.get("status") or meta.get("status") or item.get("status") or "")
    return created, user, status


def _submission_row(item: Dict[str, Any], label_map: Dict[str, str], preview_keys: List[str]) -> Dict[str, Any]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    created, user, status = _info_meta(item)
    preview = []
    for key in preview_keys:
        formatted = _format_value(data.get(key))
        preview.append(
            {
                "key": key,
                "label": label_map.get(key, key),
                "text": formatted.get("text") or "",
            }
        )
    return {
        "id": str(item.get("id") or ""),
        "created": created,
        "user": user,
        "status": status,
        "preview": preview,
    }


def _detail_fields(item: Dict[str, Any], label_map: Dict[str, str]) -> List[Dict[str, Any]]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    rows: List[Dict[str, Any]] = []
    seen = set()
    for key, label in label_map.items():
        formatted = _format_value(data.get(key))
        rows.append(
            {
                "key": key,
                "label": label,
                "text": formatted.get("text") or "",
                "files": formatted.get("files") or [],
            }
        )
        seen.add(key)
    for key, value in data.items():
        if key in seen:
            continue
        formatted = _format_value(value)
        rows.append(
            {
                "key": str(key),
                "label": str(key),
                "text": formatted.get("text") or "",
                "files": formatted.get("files") or [],
            }
        )
    return rows


def _campos_desde_formulario(formulario: Dict[str, Any]) -> List[Dict[str, Any]]:
    published = formulario.get("publishedVersion") if isinstance(formulario.get("publishedVersion"), dict) else {}
    latest = formulario.get("latestVersion") if isinstance(formulario.get("latestVersion"), dict) else {}
    version_id = published.get("formVersion") or latest.get("id") or ""
    form_id = str(formulario.get("id") or "")
    if not version_id or not form_id:
        return []
    try:
        version_id = assert_safe_id(str(version_id), "formVersionId")
        version = get_form_version(form_id, version_id) or {}
    except (MoreAppApiConfigError, MoreAppApiError):
        return []
    if not isinstance(version, dict):
        return []
    return _extract_version_fields(version)


@admin_or_administrativo
def registros_form_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_catalogo")

    query = (request.GET.get("query") or "").strip()
    page = _page_int(request.GET.get("page"))
    context = {
        "form_id": form_id,
        "formulario": {},
        "registros": [],
        "error": "",
        "query": query,
        "page": page,
        "has_next": False,
        "has_prev": page > 0,
        "preview_labels": [],
    }
    try:
        formulario = get_form(form_id)
        formulario_row = _form_row(formulario if isinstance(formulario, dict) else {})
        campos = _campos_desde_formulario(formulario if isinstance(formulario, dict) else {})
        labels = _label_map(campos)
        preview_keys = _preview_keys(campos)
        payload: Dict[str, Any] = {
            "sort": [{"key": "info.date", "direction": -1}],
        }
        if query:
            payload["query"] = query
        raw = list_submissions(form_id, page=page, payload=payload)
        items = [item for item in _submission_items(raw) if isinstance(item, dict)]
        registros = [_submission_row(item, labels, preview_keys) for item in items]
        context.update(
            {
                "formulario": formulario_row,
                "registros": registros,
                "has_next": len(items) >= _PAGE_SIZE,
                "preview_labels": [labels.get(key, key) for key in preview_keys],
            }
        )
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_registros.html", context)


@require_GET
@admin_or_administrativo
def ultimo_registro_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
        raw = get_latest_submission(form_id)
        items = [item for item in _submission_items(raw) if isinstance(item, dict)]
        if not items:
            return JsonResponse({"ok": True, "date": "", "empty": True})
        created, _user, _status = _info_meta(items[0])
        return JsonResponse({"ok": True, "date": created, "empty": not bool(created)})
    except MoreAppApiConfigError as exc:
        return JsonResponse({"ok": False, "date": "", "empty": True, "error": str(exc)}, status=400)
    except MoreAppApiError as exc:
        return JsonResponse({"ok": False, "date": "", "empty": True, "error": str(exc)}, status=502)


@admin_or_administrativo
def registro_detail_view(request, form_id: str, submission_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
        submission_id = assert_safe_id(submission_id, "submissionId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_catalogo")

    context = {
        "form_id": form_id,
        "submission_id": submission_id,
        "formulario": {},
        "registro": {},
        "campos": [],
        "error": "",
        "raw_json": "",
    }
    try:
        formulario = get_form(form_id)
        formulario_row = _form_row(formulario if isinstance(formulario, dict) else {})
        campos_tpl = _campos_desde_formulario(formulario if isinstance(formulario, dict) else {})
        labels = _label_map(campos_tpl)
        item = get_submission(submission_id)
        if not isinstance(item, dict):
            item = {"value": item}
        created, user, status = _info_meta(item)
        campos = _detail_fields(item, labels)
        context.update(
            {
                "formulario": formulario_row,
                "registro": {
                    "id": str(item.get("id") or submission_id),
                    "created": created,
                    "user": user,
                    "status": status,
                },
                "campos": campos,
                "raw_json": _pretty(
                    {
                        "id": item.get("id"),
                        "info": item.get("info"),
                        "meta": item.get("meta"),
                        "data": item.get("data"),
                    }
                ),
            }
        )
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_registro.html", context)


@require_GET
@admin_or_administrativo
def registro_archivo_view(request, file_id: str):
    try:
        file_id = assert_safe_id(file_id, "fileId")
        archivo = download_registration_file(file_id)
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_catalogo")
    except MoreAppApiError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_catalogo")

    content_type = archivo.get("content_type") or "application/octet-stream"
    filename = (archivo.get("filename") or file_id).replace('"', "")
    response = HttpResponse(archivo["content"], content_type=content_type)
    disposition = "inline" if str(content_type).startswith("image/") else "attachment"
    response["Content-Disposition"] = '%s; filename="%s"' % (disposition, filename)
    return response
