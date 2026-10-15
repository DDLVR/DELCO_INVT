"""Pantallas HTML de Fase 2: ver registros (submissions) de cada formulario MoreApp."""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
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
from .moreapp_catalogo_views import _extract_version_fields, _fold_text, _form_row, _pretty
from .moreapp_fechas import format_moreapp_when, iso_day_moreapp
from .moreapp_http import assert_safe_id

_PAGE_SIZE = 20
_EXPORT_PAGE_SIZE = 50
_EXPORT_MAX_PAGES = 20
_SKIP_WIDGETS = {"header", "image"}
_CLIENTE_KEYS = {
    "numcliente",
    "numerocliente",
    "nrocliente",
    "ncliente",
    "codigocliente",
    "cliente",
}
_TECNICO_KEYS = {
    "tecnicoresponsable",
    "tecnicodelco",
    "tecnico",
}


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


def _norm_key(value: Any) -> str:
    return _fold_text(value).replace(" ", "").replace("_", "").replace("-", "")


def _is_cliente_key(name: str) -> bool:
    return _norm_key(name) in _CLIENTE_KEYS


def _is_tecnico_key(name: str) -> bool:
    key = _norm_key(name)
    if key in _TECNICO_KEYS:
        return True
    return "tecnico" in key and "responsable" in key


def _preview_keys(campos: List[Dict[str, Any]]) -> List[str]:
    keys: List[str] = []
    for campo in campos:
        data_name = str(campo.get("data_name") or "").strip()
        widget = str(campo.get("widget") or "")
        if not data_name or widget in _SKIP_WIDGETS or widget in {"photo", "signature", "file", "drawing"}:
            continue
        if _is_cliente_key(data_name) or _is_tecnico_key(data_name):
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
    for key in ("NOMBRES", "nombres", "nombre", "name", "label", "value", "emailAddress"):
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
    return format_moreapp_when(value)


def _iso_day(value: Any) -> str:
    return iso_day_moreapp(value)


def _chile_millis(fecha: str, *, end: bool) -> Optional[int]:
    try:
        day = datetime.strptime(fecha, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    clock = time(23, 59, 59, 999000) if end else time(0, 0, 0)
    aware = timezone.make_aware(datetime.combine(day, clock), timezone.get_current_timezone())
    return int(aware.timestamp() * 1000)


def _clean_person_text(value: Any) -> str:
    text = str(value or "").strip()
    return text.rstrip(" ;,|").strip()


def _nested_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list) and value:
        return _nested_text(value[0])
    if isinstance(value, dict):
        return _clean_person_text(_datasource_text(value))
    return _clean_person_text(value)


def _value_by_keys(data: Dict[str, Any], matcher) -> str:
    for key, value in data.items():
        if not matcher(str(key)):
            continue
        text = _nested_text(value)
        if text:
            return text
    return ""


def _cliente_numero(data: Dict[str, Any]) -> str:
    text = _value_by_keys(data, _is_cliente_key)
    if text:
        return text
    for nested in data.values():
        if not isinstance(nested, dict):
            continue
        for key in ("CLIENTE", "cliente", "numCliente", "NUMCLIENTE"):
            value = nested.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return ""


def _tecnico_desde_data(data: Dict[str, Any]) -> str:
    return _value_by_keys(data, _is_tecnico_key)


def _usuarios_por_email(emails: List[str]) -> Dict[str, str]:
    cleaned = []
    for email in emails:
        text = str(email or "").strip().lower()
        if "@" in text:
            cleaned.append(text)
    if not cleaned:
        return {}
    Usuario = get_user_model()
    mapping: Dict[str, str] = {}
    for user in Usuario.objects.filter(email__in=list(set(cleaned))):
        email = str(user.email or "").strip().lower()
        nombre = (
            getattr(user, "nombre_interno", "")
            or ("%s %s" % (getattr(user, "nombre", "") or "", getattr(user, "apellido", "") or "")).strip()
        )
        if email and nombre:
            mapping[email] = str(nombre)
    return mapping


def _tecnico_responsable(item: Dict[str, Any], data: Dict[str, Any], usuarios: Optional[Dict[str, str]] = None) -> str:
    from_data = _tecnico_desde_data(data)
    if from_data:
        return from_data
    info = item.get("info") if isinstance(item.get("info"), dict) else {}
    user_name = str(info.get("userName") or "").strip()
    email = str(info.get("email") or info.get("userId") or "").strip()
    usuarios = usuarios or {}
    for candidate in (email, user_name):
        mapped = usuarios.get(candidate.lower()) if candidate else ""
        if mapped:
            return mapped
    if user_name and "@" not in user_name:
        return user_name
    return user_name or email


def _submissions_query(
    tecnico: str,
    num_cliente: str,
    fecha_desde: str,
    fecha_hasta: str,
) -> List[Dict[str, Any]]:
    filters: List[Dict[str, Any]] = []
    date_value: Dict[str, int] = {}
    if fecha_desde:
        start = _chile_millis(fecha_desde, end=False)
        if start is not None:
            date_value["start"] = start
    if fecha_hasta:
        end = _chile_millis(fecha_hasta, end=True)
        if end is not None:
            date_value["end"] = end
    if date_value:
        filters.append({"path": "info.date", "type": "date", "value": date_value})
    cliente = (num_cliente or "").strip()
    if cliente:
        if cliente.isdigit():
            filters.append({"path": "data.numCliente", "type": "number", "value": int(cliente)})
        else:
            filters.append({"path": "data.numCliente", "type": "string", "value": cliente})
    return filters


def _item_matches_filtros(item: Dict[str, Any], tecnico: str, num_cliente: str, usuarios: Optional[Dict[str, str]] = None) -> bool:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    info = item.get("info") if isinstance(item.get("info"), dict) else {}
    if num_cliente:
        hay_cliente = _fold_text(_cliente_numero(data))
        if _fold_text(num_cliente) not in hay_cliente:
            return False
    if tecnico:
        needle = _fold_text(tecnico)
        tecnico_nombre = _fold_text(_tecnico_responsable(item, data, usuarios))
        extras = _fold_text(
            " ".join(
                str(part)
                for part in (info.get("userName"), info.get("userId"), info.get("email"))
                if part not in (None, "")
            )
        )
        if needle not in tecnico_nombre and needle not in extras:
            return False
    return True


def _filtros_qs(
    tecnico: str,
    num_cliente: str,
    fecha_desde: str,
    fecha_hasta: str,
    page: Optional[int] = None,
) -> str:
    params: Dict[str, Any] = {}
    if tecnico:
        params["tecnico"] = tecnico
    if num_cliente:
        params["num_cliente"] = num_cliente
    if fecha_desde:
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        params["fecha_hasta"] = fecha_hasta
    if page is not None:
        params["page"] = page
    return urlencode(params)


def _info_meta(item: Dict[str, Any], usuarios: Optional[Dict[str, str]] = None) -> Tuple[str, str, str, str]:
    info = item.get("info") if isinstance(item.get("info"), dict) else {}
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    raw_date = info.get("date") or info.get("created") or meta.get("created") or meta.get("lastUpdated") or ""
    created = _format_when(raw_date)
    tecnico = _tecnico_responsable(item, data, usuarios)
    status = str(info.get("status") or meta.get("status") or item.get("status") or "")
    cliente = _cliente_numero(data)
    return created, tecnico, status, cliente


def _submission_row(
    item: Dict[str, Any],
    label_map: Dict[str, str],
    preview_keys: List[str],
    usuarios: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    created, tecnico, status, cliente = _info_meta(item, usuarios)
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
        "user": tecnico,
        "tecnico": tecnico,
        "cliente": cliente,
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


def _catalogo_qs_from_fechas(fecha_desde: str, fecha_hasta: str) -> str:
    params: Dict[str, str] = {}
    if fecha_desde:
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        params["fecha_hasta"] = fecha_hasta
    return urlencode(params)


def _excel_registros_response(formulario: Dict[str, Any], registros: List[Dict[str, Any]], preview_labels: List[str]):
    from reportes.exports import build_excel_response

    headers = ["Fecha", "Técnico responsable", "N° cliente"] + list(preview_labels) + ["Estado", "ID"]
    rows = []
    for registro in registros:
        row = [
            registro.get("created") or "",
            registro.get("tecnico") or "",
            registro.get("cliente") or "",
        ]
        preview = registro.get("preview") or []
        texts = [str(item.get("text") or "") for item in preview]
        while len(texts) < len(preview_labels):
            texts.append("")
        row.extend(texts[: len(preview_labels)])
        row.append(registro.get("status") or "")
        row.append(registro.get("id") or "")
        rows.append(row)
    title = "MoreApp · %s" % (formulario.get("name") or "Registros")
    return build_excel_response(
        "moreapp_registros.xlsx",
        headers,
        rows,
        title=title,
        sheet_title="Registros",
    )


def _cargar_submissions(
    form_id: str,
    *,
    page: int,
    page_size: int,
    tecnico: str,
    num_cliente: str,
    fecha_desde: str,
    fecha_hasta: str,
) -> Tuple[List[Dict[str, Any]], Any]:
    payload: Dict[str, Any] = {
        "pageSize": page_size,
        "sort": [{"key": "info.date", "direction": -1}],
    }
    filters = _submissions_query(tecnico, num_cliente, fecha_desde, fecha_hasta)
    if filters:
        payload["query"] = filters
    try:
        raw = list_submissions(form_id, page=page, payload=payload)
    except MoreAppApiError:
        if not (tecnico or num_cliente):
            raise
        payload.pop("query", None)
        date_only = _submissions_query("", "", fecha_desde, fecha_hasta)
        if date_only:
            payload["query"] = date_only
        raw = list_submissions(form_id, page=page, payload=payload)
    items = [item for item in _submission_items(raw) if isinstance(item, dict)]
    if not items and (tecnico or num_cliente) and payload.get("query"):
        payload.pop("query", None)
        date_only = _submissions_query("", "", fecha_desde, fecha_hasta)
        if date_only:
            payload["query"] = date_only
        raw = list_submissions(form_id, page=page, payload=payload)
        items = [item for item in _submission_items(raw) if isinstance(item, dict)]
    return items, raw


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

    tecnico = (request.GET.get("tecnico") or request.GET.get("query") or "").strip()
    num_cliente = (request.GET.get("num_cliente") or "").strip()
    fecha_desde = (request.GET.get("fecha_desde") or "").strip()
    fecha_hasta = (request.GET.get("fecha_hasta") or "").strip()
    page = _page_int(request.GET.get("page"))
    exportar = (request.GET.get("export") or "").strip().lower() in ("xlsx", "excel", "1")
    filtros_detalle = _filtros_qs(tecnico, num_cliente, fecha_desde, fecha_hasta, page if page else None)
    context = {
        "form_id": form_id,
        "formulario": {},
        "registros": [],
        "error": "",
        "tecnico": tecnico,
        "num_cliente": num_cliente,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "page": page,
        "has_next": False,
        "has_prev": page > 0,
        "preview_labels": [],
        "filtros_qs": _filtros_qs(tecnico, num_cliente, fecha_desde, fecha_hasta),
        "filtros_detalle": filtros_detalle,
        "filtros_prev": _filtros_qs(tecnico, num_cliente, fecha_desde, fecha_hasta, page - 1 if page else 0),
        "filtros_next": _filtros_qs(tecnico, num_cliente, fecha_desde, fecha_hasta, page + 1),
        "catalogo_qs": _catalogo_qs_from_fechas(fecha_desde, fecha_hasta),
        "tiene_filtros": bool(tecnico or num_cliente or fecha_desde or fecha_hasta),
    }
    try:
        formulario = get_form(form_id)
        formulario_row = _form_row(formulario if isinstance(formulario, dict) else {})
        campos = _campos_desde_formulario(formulario if isinstance(formulario, dict) else {})
        labels = _label_map(campos)
        preview_keys = _preview_keys(campos)
        preview_labels = [labels.get(key, key) for key in preview_keys]
        page_size = _EXPORT_PAGE_SIZE if (exportar or tecnico or num_cliente) else _PAGE_SIZE
        pages = range(_EXPORT_MAX_PAGES) if exportar else [page]
        collected: List[Dict[str, Any]] = []
        has_next = False
        for page_idx in pages:
            items, raw = _cargar_submissions(
                form_id,
                page=page_idx,
                page_size=page_size,
                tecnico=tecnico,
                num_cliente=num_cliente,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
            )
            collected.extend(items)
            total = raw.get("totalSize") if isinstance(raw, dict) else None
            if total is None or tecnico or num_cliente:
                page_has_next = len(items) >= _PAGE_SIZE
            else:
                page_has_next = (page_idx * page_size + len(items)) < int(total)
            if not exportar:
                has_next = page_has_next
                break
            if not items or not page_has_next:
                break
        emails = []
        for item in collected:
            info = item.get("info") if isinstance(item.get("info"), dict) else {}
            emails.extend([info.get("userId") or "", info.get("email") or "", info.get("userName") or ""])
        usuarios = _usuarios_por_email(emails)
        if tecnico or num_cliente:
            collected = [item for item in collected if _item_matches_filtros(item, tecnico, num_cliente, usuarios)]
        registros = [_submission_row(item, labels, preview_keys, usuarios) for item in collected]
        if exportar:
            return _excel_registros_response(formulario_row, registros, preview_labels)
        context.update(
            {
                "formulario": formulario_row,
                "registros": registros,
                "has_next": has_next,
                "preview_labels": preview_labels,
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
            return JsonResponse({"ok": True, "date": "", "day": "", "empty": True})
        created, _tecnico, _status, _cliente = _info_meta(items[0])
        info = items[0].get("info") if isinstance(items[0].get("info"), dict) else {}
        meta = items[0].get("meta") if isinstance(items[0].get("meta"), dict) else {}
        raw_date = info.get("date") or info.get("created") or meta.get("created") or meta.get("lastUpdated") or ""
        return JsonResponse(
            {
                "ok": True,
                "date": created,
                "day": _iso_day(raw_date),
                "empty": not bool(created),
            }
        )
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

    tecnico = (request.GET.get("tecnico") or request.GET.get("query") or "").strip()
    num_cliente = (request.GET.get("num_cliente") or "").strip()
    fecha_desde = (request.GET.get("fecha_desde") or "").strip()
    fecha_hasta = (request.GET.get("fecha_hasta") or "").strip()
    page = _page_int(request.GET.get("page"))
    context = {
        "form_id": form_id,
        "submission_id": submission_id,
        "formulario": {},
        "registro": {},
        "campos": [],
        "error": "",
        "raw_json": "",
        "filtros_qs": _filtros_qs(tecnico, num_cliente, fecha_desde, fecha_hasta, page if page else None),
        "catalogo_qs": _catalogo_qs_from_fechas(fecha_desde, fecha_hasta),
    }
    try:
        formulario = get_form(form_id)
        formulario_row = _form_row(formulario if isinstance(formulario, dict) else {})
        campos_tpl = _campos_desde_formulario(formulario if isinstance(formulario, dict) else {})
        labels = _label_map(campos_tpl)
        item = get_submission(submission_id)
        if not isinstance(item, dict):
            item = {"value": item}
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        usuarios = _usuarios_por_email([info.get("userId") or "", info.get("email") or "", info.get("userName") or ""])
        created, tecnico, status, cliente = _info_meta(item, usuarios)
        campos = _detail_fields(item, labels)
        context.update(
            {
                "formulario": formulario_row,
                "registro": {
                    "id": str(item.get("id") or submission_id),
                    "created": created,
                    "user": tecnico,
                    "tecnico": tecnico,
                    "cliente": cliente,
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
