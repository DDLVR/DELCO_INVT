"""Pantallas HTML de Fase 1 para observar el catálogo MoreApp sin tocar reportes actuales."""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.decorators import admin_or_administrativo

from .models import MoreAppFormularioOculto

from .moreapp_api import (
    MoreAppApiConfigError,
    MoreAppApiError,
    get_datasource,
    get_datasource_entries,
    get_form,
    get_form_version,
    list_all_forms,
    list_datasources,
    list_form_versions,
    list_users,
)
from .moreapp_fechas import format_moreapp_when
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


def _fold_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


def _fecha_param(raw: Any) -> str:
    text = str(raw or "").strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
    return text


def _catalogo_qs(query: str, mostrar_ocultos: bool, fecha_desde: str, fecha_hasta: str) -> str:
    params: Dict[str, str] = {}
    if query:
        params["query"] = query
    if mostrar_ocultos:
        params["mostrar_ocultos"] = "1"
    if fecha_desde:
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        params["fecha_hasta"] = fecha_hasta
    return urlencode(params)


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
        "last_updated": format_moreapp_when(meta.get("lastUpdated") or item.get("lastUpdated") or ""),
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
        "latest_updated": format_moreapp_when(latest.get("lastUpdated") or meta.get("lastUpdated") or ""),
        "icon": item.get("icon") or meta.get("icon") or "clipboard",
    }


def _catalogo_return_url(request) -> str:
    url = reverse("moreapp_api_catalogo")
    query = (request.POST.get("query") or request.GET.get("query") or "").strip()
    mostrar = (request.POST.get("mostrar_ocultos") or request.GET.get("mostrar_ocultos") or "").strip() in (
        "1",
        "true",
        "on",
    )
    fecha_desde = _fecha_param(request.POST.get("fecha_desde") or request.GET.get("fecha_desde"))
    fecha_hasta = _fecha_param(request.POST.get("fecha_hasta") or request.GET.get("fecha_hasta"))
    qs = _catalogo_qs(query, mostrar, fecha_desde, fecha_hasta)
    if qs:
        return url + "?" + qs
    return url


@admin_or_administrativo
def catalogo_forms_view(request):
    query = (request.GET.get("query") or "").strip()
    mostrar_ocultos = (request.GET.get("mostrar_ocultos") or "").strip() in ("1", "true", "on")
    fecha_desde = _fecha_param(request.GET.get("fecha_desde"))
    fecha_hasta = _fecha_param(request.GET.get("fecha_hasta"))
    registros_params: Dict[str, str] = {}
    if fecha_desde:
        registros_params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        registros_params["fecha_hasta"] = fecha_hasta
    context = {
        "conexion": None,
        "formularios": [],
        "error": "",
        "query": query,
        "mostrar_ocultos": mostrar_ocultos,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "tiene_filtros": bool(query or mostrar_ocultos or fecha_desde or fecha_hasta),
        "registros_qs": urlencode(registros_params),
        "activos": 0,
        "ocultos": 0,
    }
    try:
        raw = list_all_forms()
        rows = [_form_row(item) for item in raw if isinstance(item, dict)]
        if query:
            needle = _fold_text(query)
            rows = [row for row in rows if needle in _fold_text(row.get("name"))]
        ocultos_ids = set(
            MoreAppFormularioOculto.objects.filter(usuario=request.user).values_list("form_id", flat=True)
        )
        for row in rows:
            row["oculto"] = row.get("id") in ocultos_ids
        ocultos_count = MoreAppFormularioOculto.objects.filter(usuario=request.user).count()
        if not mostrar_ocultos:
            rows = [row for row in rows if not row.get("oculto")]
        context["conexion"] = {
            "ok": True,
            "forms_detected_in_first_call": len(rows),
        }
        context["formularios"] = rows
        context["activos"] = sum(1 for row in rows if row.get("status") == "ACTIVE")
        context["ocultos"] = ocultos_count
        context["raw_json"] = _pretty(raw)
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_catalogo.html", context)


@require_POST
@admin_or_administrativo
def catalogo_ocultar_form_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect(_catalogo_return_url(request))
    nombre = (request.POST.get("nombre") or "").strip()[:255]
    MoreAppFormularioOculto.objects.get_or_create(
        usuario=request.user,
        form_id=form_id,
        defaults={"form_name": nombre},
    )
    messages.success(request, "Formulario oculto en tu catálogo. Puedes volver a mostrarlo cuando quieras.")
    return redirect(_catalogo_return_url(request))


@require_POST
@admin_or_administrativo
def catalogo_mostrar_form_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect(_catalogo_return_url(request))
    MoreAppFormularioOculto.objects.filter(usuario=request.user, form_id=form_id).delete()
    messages.success(request, "Formulario visible otra vez en tu catálogo.")
    return redirect(_catalogo_return_url(request))


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


def _column_rows(mapping: Any) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not isinstance(mapping, list):
        return rows
    for item in mapping:
        if not isinstance(item, dict):
            continue
        col_id = str(item.get("id") or item.get("key") or "")
        label = str(item.get("label") or item.get("name") or col_id)
        if not col_id and not label:
            continue
        rows.append({"id": col_id, "label": label})
    return rows


def _datasource_row(item: Dict[str, Any]) -> Dict[str, Any]:
    columns = _column_rows(item.get("columnMapping") or item.get("dataKeyList"))
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or "Sin nombre",
        "search_type": item.get("searchType") or "",
        "enabled": bool(item.get("enabled", True)),
        "update_status": item.get("updateStatus") or "",
        "last_updated": format_moreapp_when(item.get("lastUpdated") or item.get("lastSuccessfulUpdate") or ""),
        "columns": columns,
        "column_labels": ", ".join(col["label"] for col in columns if col.get("label")),
        "column_count": len(columns),
    }


@admin_or_administrativo
def catalogo_datasources_view(request):
    query = (request.GET.get("query") or "").strip()
    context = {
        "datasources": [],
        "error": "",
        "raw_json": "",
        "query": query,
        "tiene_filtros": bool(query),
    }
    try:
        raw = list_datasources()
        rows = [_datasource_row(item) for item in _as_list(raw) if isinstance(item, dict)]
        if query:
            needle = _fold_text(query)
            rows = [
                row
                for row in rows
                if needle in _fold_text(row.get("name")) or needle in _fold_text(row.get("column_labels"))
            ]
        context["datasources"] = rows
        context["raw_json"] = _pretty(
            [
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "searchType": row.get("search_type"),
                    "lastUpdated": row.get("last_updated"),
                    "columns": row.get("column_labels"),
                }
                for row in rows
            ]
        )
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

    context = {
        "datasource_id": datasource_id,
        "error": "",
        "raw_json": "",
        "datasource": {},
        "columnas": [],
        "filas": None,
        "sin_filas_api": True,
    }
    try:
        data = get_datasource(datasource_id)
        datasource = data if isinstance(data, dict) else {}
        row = _datasource_row(datasource)
        columnas = list(row.get("columns") or [])
        filas = None
        try:
            entries = get_datasource_entries(datasource_id)
        except MoreAppApiError:
            entries = {}
        if isinstance(entries, dict):
            if entries.get("numberOfEntries") is not None:
                filas = entries.get("numberOfEntries")
            extra_cols = _column_rows(entries.get("dataKeyList"))
            if extra_cols and not columnas:
                columnas = extra_cols
                row["column_labels"] = ", ".join(col["label"] for col in columnas if col.get("label"))
                row["column_count"] = len(columnas)
        row["columns"] = columnas
        context.update(
            {
                "datasource": row,
                "columnas": columnas,
                "filas": filas,
                "sin_filas_api": True,
                "raw_json": _pretty(
                    {
                        "id": datasource.get("id"),
                        "name": datasource.get("name"),
                        "searchType": datasource.get("searchType"),
                        "enabled": datasource.get("enabled"),
                        "lastUpdated": row.get("last_updated"),
                        "columnMapping": columnas,
                        "numberOfEntries": filas,
                    }
                ),
            }
        )
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_datasource.html", context)


def _group_labels(value: Any) -> str:
    if isinstance(value, list):
        labels = []
        for item in value:
            if isinstance(item, dict):
                labels.append(str(item.get("name") or item.get("id") or ""))
            elif item not in (None, ""):
                labels.append(str(item))
        return ", ".join(part for part in labels if part)
    if value in (None, ""):
        return ""
    return str(value)


def _user_row(item: Dict[str, Any]) -> Dict[str, Any]:
    settings = item.get("settings") if isinstance(item.get("settings"), dict) else {}
    display = (
        settings.get("displayName")
        or settings.get("name")
        or item.get("username")
        or item.get("emailAddress")
        or ""
    )
    groups = item.get("groups") if isinstance(item.get("groups"), list) else []
    return {
        "id": str(item.get("id") or ""),
        "nombre": str(display),
        "email": str(item.get("emailAddress") or ""),
        "username": str(item.get("username") or ""),
        "disabled": bool(item.get("disabled")),
        "email_validated": bool(item.get("emailValidated")),
        "groups": _group_labels(groups),
        "groups_count": len(groups),
    }


@admin_or_administrativo
def catalogo_usuarios_view(request):
    query = (request.GET.get("query") or "").strip()
    context = {
        "usuarios": [],
        "error": "",
        "query": query,
        "tiene_filtros": bool(query),
        "activos": 0,
        "deshabilitados": 0,
    }
    try:
        raw = list_users()
        rows = [_user_row(item) for item in _as_list(raw) if isinstance(item, dict)]
        if query:
            needle = _fold_text(query)
            rows = [
                row
                for row in rows
                if needle in _fold_text(row.get("nombre"))
                or needle in _fold_text(row.get("email"))
                or needle in _fold_text(row.get("username"))
            ]
        context["usuarios"] = rows
        context["activos"] = sum(1 for row in rows if not row.get("disabled"))
        context["deshabilitados"] = sum(1 for row in rows if row.get("disabled"))
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_usuarios.html", context)
