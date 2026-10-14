"""Pantallas HTML de Fase 1 para observar el catálogo MoreApp sin tocar reportes actuales."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from django.contrib import messages
from django.shortcuts import redirect, render

from web.decorators import admin_or_administrativo

from .moreapp_api import (
    MoreAppApiConfigError,
    MoreAppApiError,
    get_datasource,
    get_form,
    get_form_version,
    list_datasources,
    list_form_versions,
    list_forms,
)
from .moreapp_http import assert_safe_id

_WIDGET_LABELS = {
    "photo": "Foto",
    "signature": "Firma",
    "header": "Título",
    "image": "Imagen",
    "text": "Texto",
    "text_area": "Nota",
    "number": "Número",
    "radio": "Opción",
    "lookup": "Lista",
    "search": "Búsqueda",
    "email": "Email",
    "datetime": "Fecha/hora",
    "date": "Fecha",
    "location": "Ubicación",
    "barcode": "Código",
    "checkbox": "Check",
    "slider": "Slider",
    "subform": "Subformulario",
    "drawing": "Dibujo",
    "file": "Archivo",
}


def _as_list(data: Any) -> List[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("elements", "content", "items", "datasources"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if data.get("id") and (data.get("fields") is not None or data.get("meta") is not None):
            return [data]
    return []


def _pretty(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(data)


def _widget_short(widget: str) -> str:
    parts = (widget or "").split(":")
    if len(parts) >= 2:
        return parts[1]
    return widget or "campo"


def _extract_fields(fields: Any, depth: int = 0) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not isinstance(fields, list):
        return rows
    for field in fields:
        if not isinstance(field, dict):
            continue
        props = field.get("properties") if isinstance(field.get("properties"), dict) else {}
        short = _widget_short(str(field.get("widget") or ""))
        rows.append(
            {
                "widget": short,
                "widget_label": _WIDGET_LABELS.get(short, short.replace("_", " ").title()),
                "data_name": props.get("data_name") or props.get("dataName") or "",
                "label": props.get("label_text") or props.get("label") or field.get("name") or "Sin etiqueta",
                "required": bool(props.get("required")),
                "data_type": (field.get("data") or {}).get("type") or field.get("dataType") or "",
                "depth": depth,
            }
        )
        nested = props.get("fields")
        if isinstance(nested, list):
            rows.extend(_extract_fields(nested, depth + 1))
    return rows


def _extract_version_fields(version: Dict[str, Any]) -> List[Dict[str, Any]]:
    campos = _extract_fields(version.get("fields"))
    extra = version.get("fieldProperties")
    if not isinstance(extra, dict):
        return campos
    seen = {row.get("data_name") for row in campos if row.get("data_name")}
    for group in extra.values():
        if not isinstance(group, dict):
            continue
        nested = _extract_fields(group.get("fields"), 1)
        if not nested:
            continue
        name = ((group.get("meta") or {}).get("name") if isinstance(group.get("meta"), dict) else "") or "Grupo"
        campos.append(
            {
                "widget": "subform",
                "widget_label": "Grupo",
                "data_name": "",
                "label": name,
                "required": False,
                "data_type": "",
                "depth": 0,
            }
        )
        for row in nested:
            data_name = row.get("data_name")
            if data_name and data_name in seen:
                continue
            campos.append(row)
            if data_name:
                seen.add(data_name)
    return campos


def _version_row(item: Dict[str, Any]) -> Dict[str, str]:
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    status = item.get("status") or meta.get("status") or ""
    return {
        "id": str(item.get("id") or ""),
        "status": str(status),
        "last_updated": str(meta.get("lastUpdated") or item.get("lastUpdated") or ""),
        "updated_by": str(meta.get("lastUpdatedBy") or ""),
    }


def _form_row(item: Dict[str, Any]) -> Dict[str, Any]:
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    published = item.get("publishedVersion") if isinstance(item.get("publishedVersion"), dict) else {}
    latest = item.get("latestVersion") if isinstance(item.get("latestVersion"), dict) else {}
    status = str(item.get("status") or meta.get("status") or "")
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or meta.get("name") or "Sin nombre",
        "status": status,
        "status_badge": {
            "ACTIVE": "success",
            "HIDDEN": "secondary",
            "TRASH": "danger",
        }.get(status, "secondary"),
        "description": item.get("description") or meta.get("description") or "",
        "published_version": published.get("formVersion") or "",
        "latest_status": latest.get("status") or meta.get("status") or "",
        "latest_updated": latest.get("lastUpdated") or meta.get("lastUpdated") or "",
        "icon": item.get("icon") or meta.get("icon") or "clipboard",
    }


@admin_or_administrativo
def catalogo_forms_view(request):
    context = {
        "conexion": None,
        "formularios": [],
        "error": "",
        "query": (request.GET.get("query") or "").strip(),
        "page": int(request.GET.get("page") or 0),
        "activos": 0,
    }
    try:
        raw = list_forms(page=context["page"], query_text=context["query"])
        rows = [_form_row(item) for item in _as_list(raw) if isinstance(item, dict)]
        context["conexion"] = {
            "ok": True,
            "forms_detected_in_first_call": len(rows),
        }
        context["formularios"] = rows
        context["activos"] = sum(1 for row in rows if row.get("status") == "ACTIVE")
        context["raw_json"] = _pretty(raw)
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_catalogo.html", context)


@admin_or_administrativo
def catalogo_form_detail_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_catalogo")

    context = {
        "form_id": form_id,
        "formulario": {},
        "versiones": [],
        "campos": [],
        "error": "",
        "raw_json": "",
        "version_id": "",
        "campos_requeridos": 0,
        "fotos": 0,
        "firmas": 0,
    }
    try:
        formulario = get_form(form_id)
        raw_versions = list_form_versions(form_id, page=0, size=20)
        versiones_raw = _as_list(raw_versions)
        published = (formulario or {}).get("publishedVersion") or {}
        latest = (formulario or {}).get("latestVersion") or {}
        version_id = published.get("formVersion") or latest.get("id") or ""
        if not version_id and versiones_raw:
            version_id = (versiones_raw[0] or {}).get("id") or ""
        campos: List[Dict[str, Any]] = []
        if version_id:
            try:
                version_id = assert_safe_id(str(version_id), "formVersionId")
            except MoreAppApiConfigError:
                version_id = str(version_id)
            version_detalle = get_form_version(form_id, version_id) or {}
            campos = _extract_version_fields(version_detalle if isinstance(version_detalle, dict) else {})
        version_rows = [_version_row(item) for item in versiones_raw if isinstance(item, dict)]
        context.update(
            {
                "formulario": _form_row(formulario if isinstance(formulario, dict) else {}),
                "versiones": version_rows,
                "campos": campos,
                "version_id": version_id,
                "campos_requeridos": sum(1 for row in campos if row.get("required")),
                "fotos": sum(1 for row in campos if row.get("widget") == "photo"),
                "firmas": sum(1 for row in campos if row.get("widget") == "signature"),
                "raw_json": _pretty(
                    {
                        "form": {
                            "id": (formulario or {}).get("id"),
                            "name": (formulario or {}).get("name"),
                            "status": (formulario or {}).get("status"),
                            "publishedVersion": published,
                            "latestVersion": latest,
                        },
                        "versions": version_rows,
                        "fields": campos,
                    }
                ),
            }
        )
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_formulario.html", context)


@admin_or_administrativo
def catalogo_datasources_view(request):
    context = {"datasources": [], "error": "", "raw_json": ""}
    try:
        raw = list_datasources()
        rows = []
        for item in _as_list(raw):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "id": item.get("id") or "",
                    "name": item.get("name") or "Sin nombre",
                    "search_type": item.get("searchType") or "",
                    "update_interval": (
                        (item.get("urlConfiguration") or {}).get("updateInterval")
                        or (item.get("googleConfiguration") or {}).get("updateInterval")
                        or ""
                    ),
                }
            )
        context["datasources"] = rows
        context["raw_json"] = _pretty(raw)
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_datasources.html", context)


@admin_or_administrativo
def catalogo_datasource_detail_view(request, datasource_id: str):
    try:
        datasource_id = assert_safe_id(datasource_id, "datasourceId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_datasources")

    context = {"datasource_id": datasource_id, "error": "", "raw_json": ""}
    try:
        data = get_datasource(datasource_id)
        context["raw_json"] = _pretty(data)
        context["datasource"] = data if isinstance(data, dict) else {"value": data}
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_datasource.html", context)
