"""Pantallas HTML de Fase 1 para observar el catálogo MoreApp sin tocar reportes actuales."""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.decorators import admin_only, admin_or_formulario_asignado

from .models import MoreAppFormularioOculto, MoreAppFuenteInterna
from .moreapp_cuentas import aplicar_vinculos_a_usuarios, guardar_vinculo, listar_tecnicos_moreapp
from .moreapp_asignaciones import asignaciones_por_form, enriquecer_fila, usuarios_asignables
from .moreapp_permisos import (
    accesos_de_formulario,
    anotar_accesos_en_formularios,
    cargar_usuarios_moreapp_con_permisos,
)

from .moreapp_api import (
    MoreAppApiConfigError,
    MoreAppApiError,
    get_datasource,
    get_datasource_entries,
    get_form,
    get_form_version,
    list_all_forms,
    list_datasource_entry_rows,
    list_datasources,
    list_form_versions,
    list_users,
)
from .moreapp_fechas import format_moreapp_when
from .moreapp_fuentes import parse_uploaded_fuente, upsert_filas
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


def _catalogo_qs(
    query: str,
    mostrar_ocultos: bool,
    fecha_desde: str,
    fecha_hasta: str,
    estado: str = "",
    asignacion: str = "",
    orden: str = "",
) -> str:
    params: Dict[str, str] = {}
    if query:
        params["query"] = query
    if mostrar_ocultos:
        params["mostrar_ocultos"] = "1"
    if fecha_desde:
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        params["fecha_hasta"] = fecha_hasta
    if estado:
        params["estado"] = estado
    if asignacion:
        params["asignacion"] = asignacion
    if orden and orden != "nombre":
        params["orden"] = orden
    return urlencode(params)


def _filtro_estado(raw: Any) -> str:
    value = str(raw or "").strip().upper()
    return value if value in ("ACTIVE", "HIDDEN", "TRASH") else ""


def _filtro_asignacion(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in ("con", "sin") else ""


def _filtro_orden(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in ("nombre", "asignados", "registro") else "nombre"


def _search_haystack(row: Dict[str, Any]) -> str:
    parts = [
        row.get("name"),
        row.get("description"),
        row.get("id"),
        row.get("status"),
        row.get("status_label"),
    ]
    parts.extend(row.get("asignados") or [])
    return _fold_text(" ".join(str(part or "") for part in parts))


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
        search_cfg = props.get("search") if isinstance(props.get("search"), dict) else {}
        datasource_id = str(
            props.get("dataSourceId")
            or props.get("datasourceId")
            or props.get("data_source")
            or props.get("datasource")
            or search_cfg.get("dataSourceId")
            or search_cfg.get("datasourceId")
            or field.get("dataSourceId")
            or ""
        ).strip()
        rows.append(
            {
                "widget": short,
                "widget_label": _WIDGET_LABELS.get(short, short.replace("_", " ").title()),
                "data_name": props.get("data_name") or props.get("dataName") or "",
                "label": props.get("label_text") or props.get("label") or field.get("name") or "Sin etiqueta",
                "required": bool(props.get("required")),
                "data_type": (field.get("data") or {}).get("type") or field.get("dataType") or "",
                "datasource_id": datasource_id,
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
        "status_label": {
            "ACTIVE": "Activo",
            "HIDDEN": "Oculto",
            "TRASH": "Papelera",
        }.get(status, status or "—"),
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
    estado = _filtro_estado(request.POST.get("estado") or request.GET.get("estado"))
    asignacion = _filtro_asignacion(request.POST.get("asignacion") or request.GET.get("asignacion"))
    orden = _filtro_orden(request.POST.get("orden") or request.GET.get("orden"))
    qs = _catalogo_qs(query, mostrar, fecha_desde, fecha_hasta, estado, asignacion, orden)
    if qs:
        return url + "?" + qs
    return url


@admin_only
def catalogo_forms_view(request):
    query = (request.GET.get("query") or "").strip()
    mostrar_ocultos = (request.GET.get("mostrar_ocultos") or "").strip() in ("1", "true", "on")
    fecha_desde = _fecha_param(request.GET.get("fecha_desde"))
    fecha_hasta = _fecha_param(request.GET.get("fecha_hasta"))
    estado = _filtro_estado(request.GET.get("estado"))
    asignacion = _filtro_asignacion(request.GET.get("asignacion"))
    orden = _filtro_orden(request.GET.get("orden"))
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
        "estado": estado,
        "asignacion": asignacion,
        "orden": orden,
        "tiene_filtros": bool(
            query or mostrar_ocultos or fecha_desde or fecha_hasta or estado or asignacion or orden != "nombre"
        ),
        "registros_qs": urlencode(registros_params),
        "activos": 0,
        "ocultos": 0,
        "ocultos_en_catalogo": 0,
        "total_api": 0,
        "asignados_forms": 0,
        "usuarios_asignables": list(usuarios_asignables()),
    }
    try:
        raw = list_all_forms()
        rows = [_form_row(item) for item in raw if isinstance(item, dict)]
        ocultos_ids = set(
            MoreAppFormularioOculto.objects.filter(usuario=request.user).values_list("form_id", flat=True)
        )
        por_form = asignaciones_por_form()
        usuarios_ma, conoce_permisos = cargar_usuarios_moreapp_con_permisos()
        for row in rows:
            form_id = str(row.get("id") or "")
            row["oculto"] = form_id in ocultos_ids
            enriquecer_fila(row, por_form.get(form_id, []))
            row["search_haystack"] = _search_haystack(row)
        anotar_accesos_en_formularios(rows, usuarios_ma, conoce_permisos=conoce_permisos)
        ocultos_en_catalogo = sum(1 for row in rows if row.get("oculto"))
        ocultos_count = MoreAppFormularioOculto.objects.filter(usuario=request.user).count()
        total_api = len(rows)
        if not mostrar_ocultos:
            rows = [row for row in rows if not row.get("oculto")]
        context["conexion"] = {
            "ok": True,
            "forms_detected_in_first_call": len(rows),
        }
        context["formularios"] = rows
        context["activos"] = sum(1 for row in rows if row.get("status") == "ACTIVE")
        context["asignados_forms"] = sum(1 for row in rows if int(row.get("asignados_count") or 0) > 0)
        context["ocultos"] = ocultos_count
        context["ocultos_en_catalogo"] = ocultos_en_catalogo
        context["total_api"] = total_api
        context["raw_json"] = _pretty(raw)
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return render(request, "integraciones/moreapp_catalogo.html", context)


@require_POST
@admin_only
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
@admin_only
def catalogo_mostrar_form_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect(_catalogo_return_url(request))
    MoreAppFormularioOculto.objects.filter(usuario=request.user, form_id=form_id).delete()
    messages.success(request, "Formulario visible otra vez en tu catálogo.")
    return redirect(_catalogo_return_url(request))


@require_POST
@admin_only
def catalogo_mostrar_todos_view(request):
    borrados, _unused = MoreAppFormularioOculto.objects.filter(usuario=request.user).delete()
    if borrados:
        messages.success(
            request,
            "Volviste a mostrar %s formulario%s en tu catálogo."
            % (borrados, "" if borrados == 1 else "s"),
        )
    else:
        messages.info(request, "No tenías formularios ocultos en tu catálogo.")
    return redirect(reverse("moreapp_api_catalogo"))


@admin_or_formulario_asignado
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
    usuarios_ma, conoce_permisos = cargar_usuarios_moreapp_con_permisos()
    context["moreapp_accesos"] = accesos_de_formulario(form_id, usuarios_ma)
    context["moreapp_permisos_conocidos"] = conoce_permisos
    context["puede_ver_accesos_moreapp"] = getattr(request.user, "rol", "") in (
        "ADMIN",
        "ADMINISTRATIVO",
    )
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


def _row_desde_fuente_local(fuente: MoreAppFuenteInterna) -> Dict[str, Any]:
    columns = fuente.columnas if isinstance(fuente.columnas, list) else []
    labels = [
        str(col.get("label") or col.get("id") or "")
        for col in columns
        if isinstance(col, dict)
    ]
    return {
        "id": fuente.datasource_id,
        "name": fuente.nombre,
        "search_type": "",
        "enabled": True,
        "last_updated": "",
        "columns": columns,
        "column_labels": ", ".join(part for part in labels if part),
        "column_count": len(columns),
    }


def _fuentes_locales() -> Dict[str, MoreAppFuenteInterna]:
    return {item.datasource_id: item for item in MoreAppFuenteInterna.objects.all()}


def _filas_para_tabla(filas, columnas: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    col_ids = [str(col.get("id") or "") for col in columnas if col.get("id")]
    out: List[Dict[str, Any]] = []
    for item in filas:
        valores = item.valores if isinstance(item.valores, dict) else {}
        out.append(
            {
                "entry_id": item.entry_id,
                "valores": valores,
                "celdas": [valores.get(col_id, "") for col_id in col_ids],
            }
        )
    return out


def _celdas_de_valores(valores: Dict[str, Any], col_ids: List[str]) -> List[str]:
    celdas: List[str] = []
    for col_id in col_ids:
        value = valores.get(col_id)
        if value in (None, "") and col_id:
            for key, candidate in valores.items():
                if str(key) == col_id:
                    value = candidate
                    break
        if value in (None, ""):
            celdas.append("")
        else:
            celdas.append(str(value))
    return celdas


def _filas_api_para_tabla(rows: List[Any], columnas: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    col_ids = [str(col.get("id") or "") for col in columnas if col.get("id")]
    if not col_ids:
        for item in rows:
            if isinstance(item, dict) and item:
                col_ids = [str(key) for key in item.keys()]
                break
    out: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "entry_id": str(item.get("id") or ""),
                "valores": item,
                "celdas": _celdas_de_valores(item, col_ids) if col_ids else [str(v) for v in item.values()],
            }
        )
    return out


def _filtrar_filas_tabla(filas: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    needle = _fold_text(query)
    if not needle:
        return filas
    return [
        item
        for item in filas
        if needle in _fold_text(item.get("entry_id")) or needle in _fold_text(item.get("valores"))
    ]


def _ds_search_haystack(row: Dict[str, Any]) -> str:
    parts = [
        row.get("name"),
        row.get("column_labels"),
        row.get("id"),
        row.get("search_type"),
        "guardada intranet" if row.get("en_intranet") else "no se guarda",
    ]
    return _fold_text(" ".join(str(part or "") for part in parts))


def _fila_search_haystack(item: Dict[str, Any]) -> str:
    parts = [item.get("entry_id")]
    parts.extend(item.get("celdas") or [])
    return _fold_text(" ".join(str(part or "") for part in parts))


def _marcar_fuentes_locales(rows: List[Dict[str, Any]], locales: Dict[str, MoreAppFuenteInterna]) -> None:
    counts = {}
    if locales:
        counts = dict(
            MoreAppFuenteInterna.objects.filter(datasource_id__in=list(locales.keys()))
            .annotate(n=Count("filas"))
            .values_list("datasource_id", "n")
        )
    for row in rows:
        fuente = locales.get(str(row.get("id") or ""))
        row["en_intranet"] = bool(fuente)
        row["filas_locales"] = counts.get(str(row.get("id") or ""), 0) if fuente else 0


@admin_only
def catalogo_datasources_view(request):
    query = (request.GET.get("query") or "").strip()
    solo_internas = (request.GET.get("solo_internas") or "").strip() in ("1", "true", "on")
    context = {
        "datasources": [],
        "error": "",
        "raw_json": "",
        "query": query,
        "solo_internas": solo_internas,
        "tiene_filtros": bool(query or solo_internas),
        "internas_count": MoreAppFuenteInterna.objects.count(),
        "guardadas_count": 0,
    }
    locales = _fuentes_locales()
    rows: List[Dict[str, Any]] = []
    try:
        raw = list_datasources()
        rows = [_datasource_row(item) for item in _as_list(raw) if isinstance(item, dict)]
        seen = {str(row.get("id") or "") for row in rows}
        for fuente in locales.values():
            if fuente.datasource_id not in seen:
                rows.append(_row_desde_fuente_local(fuente))
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
        rows = [_row_desde_fuente_local(fuente) for fuente in locales.values()]
    _marcar_fuentes_locales(rows, locales)
    for row in rows:
        row["search_haystack"] = _ds_search_haystack(row)
        chips = [
            str(col.get("label") or col.get("id") or "")
            for col in (row.get("columns") or [])
            if isinstance(col, dict)
        ]
        row["column_chips"] = chips[:6]
        row["column_more"] = max(0, len(chips) - 6)
    context["datasources"] = rows
    context["guardadas_count"] = sum(1 for row in rows if row.get("en_intranet"))
    context["remotas_count"] = sum(1 for row in rows if not row.get("en_intranet"))
    context["raw_json"] = _pretty(
        [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "enIntranet": row.get("en_intranet"),
                "filasLocales": row.get("filas_locales"),
                "columns": row.get("column_labels"),
            }
            for row in rows
        ]
    )
    return render(request, "integraciones/moreapp_datasources.html", context)


@admin_only
def catalogo_datasource_detail_view(request, datasource_id: str):
    try:
        datasource_id = assert_safe_id(datasource_id, "datasourceId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_datasources")

    query = (request.GET.get("query") or "").strip()
    context = {
        "datasource_id": datasource_id,
        "error": "",
        "raw_json": "",
        "datasource": {},
        "columnas": [],
        "filas": None,
        "sin_filas_api": False,
        "fuente": None,
        "filas_locales": [],
        "filas_api": [],
        "filas_api_total": 0,
        "filas_api_leidas": 0,
        "filas_api_truncadas": False,
        "query": query,
        "tiene_filtros": bool(query),
    }
    try:
        data = get_datasource(datasource_id)
        datasource = data if isinstance(data, dict) else {}
        row = _datasource_row(datasource)
        columnas = list(row.get("columns") or [])
        filas = None
        packed: Dict[str, Any] = {}
        try:
            packed = list_datasource_entry_rows(datasource_id)
        except MoreAppApiError:
            packed = {}
            try:
                entries = get_datasource_entries(datasource_id)
            except MoreAppApiError:
                entries = {}
            packed = {
                "total": (entries or {}).get("numberOfEntries") if isinstance(entries, dict) else None,
                "columns": (entries or {}).get("dataKeyList") if isinstance(entries, dict) else [],
                "rows": [],
                "truncated": False,
            }
        extra_cols = _column_rows(packed.get("columns"))
        if extra_cols and not columnas:
            columnas = extra_cols
            row["column_labels"] = ", ".join(col["label"] for col in columnas if col.get("label"))
            row["column_count"] = len(columnas)
        filas = packed.get("total")
        row["columns"] = columnas
        filas_api = _filas_api_para_tabla(list(packed.get("rows") or []), columnas)
        for item in filas_api:
            item["search_haystack"] = _fila_search_haystack(item)
        fuente = MoreAppFuenteInterna.objects.filter(datasource_id=datasource_id).first()
        filas_locales = []
        if fuente:
            local_qs = list(fuente.filas.all().order_by("entry_id")[:300])
            filas_locales = _filas_para_tabla(local_qs, columnas)
            for item in filas_locales:
                item["search_haystack"] = _fila_search_haystack(item)
        context.update(
            {
                "datasource": row,
                "columnas": columnas,
                "filas": filas,
                "sin_filas_api": not bool(packed.get("rows")),
                "fuente": fuente,
                "filas_locales": filas_locales,
                "filas_api": filas_api,
                "filas_api_total": packed.get("total") or 0,
                "filas_api_leidas": len(packed.get("rows") or []),
                "filas_api_truncadas": bool(packed.get("truncated")),
                "raw_json": _pretty(
                    {
                        "id": datasource.get("id"),
                        "name": datasource.get("name"),
                        "searchType": datasource.get("searchType"),
                        "enabled": datasource.get("enabled"),
                        "lastUpdated": row.get("last_updated"),
                        "columnMapping": columnas,
                        "numberOfEntries": filas,
                        "filasLeidas": len(packed.get("rows") or []),
                        "enIntranet": bool(fuente),
                    }
                ),
            }
        )
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
        fuente = MoreAppFuenteInterna.objects.filter(datasource_id=datasource_id).first()
        if fuente:
            context["datasource"] = {
                "id": fuente.datasource_id,
                "name": fuente.nombre,
                "columns": fuente.columnas if isinstance(fuente.columnas, list) else [],
                "last_updated": "",
                "search_type": "",
            }
            context["columnas"] = context["datasource"]["columns"]
            context["fuente"] = fuente
            filas_locales = _filas_para_tabla(
                list(fuente.filas.all().order_by("entry_id")[:300]),
                context["columnas"],
            )
            for item in filas_locales:
                item["search_haystack"] = _fila_search_haystack(item)
            context["filas_locales"] = filas_locales
    return render(request, "integraciones/moreapp_datasource.html", context)


def _snapshot_fuente(datasource_id: str) -> Dict[str, Any]:
    data = get_datasource(datasource_id)
    datasource = data if isinstance(data, dict) else {}
    row = _datasource_row(datasource)
    columnas = list(row.get("columns") or [])
    filas = None
    try:
        entries = get_datasource_entries(datasource_id)
    except MoreAppApiError:
        entries = {}
    if isinstance(entries, dict) and entries.get("numberOfEntries") is not None:
        filas = entries.get("numberOfEntries")
        extra_cols = _column_rows(entries.get("dataKeyList"))
        if extra_cols and not columnas:
            columnas = extra_cols
    return {
        "nombre": row.get("name") or datasource_id,
        "columnas": columnas,
        "filas_moreapp": filas,
    }


@require_POST
@admin_only
def catalogo_guardar_fuente_view(request, datasource_id: str):
    try:
        datasource_id = assert_safe_id(datasource_id, "datasourceId")
        snapshot = _snapshot_fuente(datasource_id)
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_datasources")
    except MoreAppApiError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_datasource", datasource_id=datasource_id)

    fuente, created = MoreAppFuenteInterna.objects.update_or_create(
        datasource_id=datasource_id,
        defaults={
            "nombre": snapshot["nombre"],
            "columnas": snapshot["columnas"],
            "filas_moreapp": snapshot["filas_moreapp"],
            "actualizado_por": request.user,
        },
    )
    if created:
        messages.success(
            request,
            "Se guardó «%s» en la intranet. El resto de listas de MoreApp no se copia." % fuente.nombre,
        )
    else:
        messages.success(request, "Se actualizó la configuración de «%s»." % fuente.nombre)
    return redirect("moreapp_api_datasource", datasource_id=datasource_id)


@require_POST
@admin_only
def catalogo_quitar_fuente_view(request, datasource_id: str):
    try:
        datasource_id = assert_safe_id(datasource_id, "datasourceId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_datasources")
    fuente = MoreAppFuenteInterna.objects.filter(datasource_id=datasource_id).first()
    if fuente:
        nombre = fuente.nombre
        fuente.delete()
        messages.success(request, "Se quitó «%s» de la intranet. Las filas locales también se eliminaron." % nombre)
    return redirect("moreapp_api_datasources")


@require_POST
@admin_only
def catalogo_importar_fuente_view(request, datasource_id: str):
    try:
        datasource_id = assert_safe_id(datasource_id, "datasourceId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_datasources")
    fuente = MoreAppFuenteInterna.objects.filter(datasource_id=datasource_id).first()
    if not fuente:
        messages.error(request, "Primero guarda esta lista en la intranet. No se importan bases que no hayas elegido.")
        return redirect("moreapp_api_datasource", datasource_id=datasource_id)
    uploaded = request.FILES.get("archivo")
    if not uploaded:
        messages.error(request, "Selecciona un Excel, CSV o JSON exportado desde MoreApp.")
        return redirect("moreapp_api_datasource", datasource_id=datasource_id)
    reemplazar = (request.POST.get("reemplazar") or "").strip() in ("1", "true", "on")
    try:
        filas = parse_uploaded_fuente(uploaded, fuente.columnas)
        if not filas:
            raise ValueError("El archivo no trae filas para importar.")
        creadas, actualizadas = upsert_filas(fuente, filas, reemplazar=reemplazar)
    except (ValueError, json.JSONDecodeError) as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_api_datasource", datasource_id=datasource_id)
    except Exception as exc:  # noqa: BLE001
        messages.error(request, "No se pudo leer el archivo: %s" % exc)
        return redirect("moreapp_api_datasource", datasource_id=datasource_id)
    messages.success(
        request,
        "Importación de «%s»: %s nueva(s), %s actualizada(s)." % (fuente.nombre, creadas, actualizadas),
    )
    return redirect("moreapp_api_datasource", datasource_id=datasource_id)


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


_FUENTES_USUARIO_MOREAPP = {
    "tecnicos": {
        "slug": "tecnicos",
        "titulo": "Técnicos",
        "descripcion": "Filas vivas de la data source Técnicos. No se copian a la intranet.",
    },
    "certelec": {
        "slug": "certelec",
        "titulo": "Certelec Técnicos",
        "descripcion": "Filas vivas de la data source Certelec Técnicos. No se copian a la intranet.",
    },
}


def _datasource_es_fuente_usuario(item: Dict[str, Any], slug: str) -> bool:
    name = _fold_text(item.get("name"))
    if slug == "certelec":
        return "certelec" in name
    if slug == "tecnicos":
        return "tecnic" in name and "certelec" not in name
    return False


def _resolver_fuente_usuario(slug: str):
    meta = _FUENTES_USUARIO_MOREAPP.get(slug)
    if not meta:
        raise MoreAppApiConfigError("Fuente de usuarios no válida.")
    for item in _as_list(list_datasources()):
        if isinstance(item, dict) and _datasource_es_fuente_usuario(item, slug):
            return meta, item
    return meta, None


@admin_only
def catalogo_usuarios_view(request):
    query = (request.GET.get("query") or "").strip()
    context = {
        "usuarios": [],
        "tecnicos": [],
        "error": "",
        "query": query,
        "tiene_filtros": bool(query),
        "activos": 0,
        "deshabilitados": 0,
        "enlazados": 0,
        "seccion_usuarios": "moreapp",
    }
    try:
        tecnicos = listar_tecnicos_moreapp()
        raw = list_users()
        rows = aplicar_vinculos_a_usuarios(
            [_user_row(item) for item in _as_list(raw) if isinstance(item, dict)],
            tecnicos=tecnicos,
        )
        if query:
            needle = _fold_text(query)
            rows = [
                row
                for row in rows
                if needle in _fold_text(row.get("nombre"))
                or needle in _fold_text(row.get("email"))
                or needle in _fold_text(row.get("username"))
                or needle in _fold_text(row.get("tecnico_nombre"))
            ]
        context["usuarios"] = rows
        context["activos"] = sum(1 for row in rows if not row.get("disabled"))
        context["deshabilitados"] = sum(1 for row in rows if row.get("disabled"))
        context["enlazados"] = sum(1 for row in rows if row.get("enlazado"))
        context["tecnicos"] = tecnicos
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
        context["tecnicos"] = listar_tecnicos_moreapp()
    return render(request, "integraciones/moreapp_usuarios.html", context)


def _es_ajax_catalogo(request) -> bool:
    return (
        (request.headers.get("X-Requested-With") or "") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "").lower()
    )


@admin_only
@require_POST
def catalogo_usuarios_vincular_view(request):
    email = (request.POST.get("email") or "").strip()
    tecnico_id = (request.POST.get("tecnico_id") or "").strip()
    tecnico_nombre = (request.POST.get("tecnico_nombre") or "").strip()
    moreapp_user_id = (request.POST.get("moreapp_user_id") or "").strip()
    moreapp_nombre = (request.POST.get("moreapp_nombre") or "").strip()
    obj, error = guardar_vinculo(
        email=email,
        tecnico_entry_id=tecnico_id,
        tecnico_nombre=tecnico_nombre,
        moreapp_user_id=moreapp_user_id,
        moreapp_nombre=moreapp_nombre,
        actualizado_por=request.user,
    )
    if error:
        if _es_ajax_catalogo(request):
            return JsonResponse({"ok": False, "error": error}, status=400)
        messages.error(request, error)
        return redirect("usuarios_moreapp")
    if obj is not None:
        nombre = obj.tecnico_nombre
        mensaje = "La cuenta %s quedó enlazada con %s." % (email, nombre)
        tecnico_id_out = obj.tecnico_entry_id
    else:
        nombre = ""
        mensaje = "Se quitó el técnico de %s." % email
        tecnico_id_out = ""
    if _es_ajax_catalogo(request):
        return JsonResponse(
            {
                "ok": True,
                "email": (email or "").strip().lower(),
                "tecnico_id": tecnico_id_out or None,
                "tecnico_nombre": nombre,
                "mensaje": mensaje,
            }
        )
    messages.success(request, mensaje)
    return redirect("usuarios_moreapp")


@admin_only
def catalogo_usuarios_fuente_view(request, fuente: str):
    query = (request.GET.get("query") or "").strip()
    slug = (fuente or "").strip().lower()
    context = {
        "error": "",
        "query": query,
        "tiene_filtros": bool(query),
        "seccion_usuarios": slug,
        "titulo": "",
        "descripcion": "",
        "columnas": [],
        "filas": [],
        "total": 0,
        "truncadas": False,
        "datasource_name": "",
    }
    try:
        meta, item = _resolver_fuente_usuario(slug)
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect("usuarios_moreapp")
    context["titulo"] = meta["titulo"]
    context["descripcion"] = meta["descripcion"]
    if not item:
        context["error"] = "No se encontró la data source «%s» en MoreApp." % meta["titulo"]
        messages.error(request, context["error"])
        return render(request, "integraciones/moreapp_usuarios_fuente.html", context)
    context["datasource_name"] = str(item.get("name") or meta["titulo"])
    columnas = _column_rows(item.get("columnMapping") or item.get("dataKeyList"))
    packed: Dict[str, Any] = {}
    try:
        packed = list_datasource_entry_rows(str(item.get("id") or ""))
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
        packed = {}
    extra_cols = _column_rows(packed.get("columns"))
    if extra_cols and not columnas:
        columnas = extra_cols
    filas = _filtrar_filas_tabla(_filas_api_para_tabla(list(packed.get("rows") or []), columnas), query)
    context.update(
        {
            "columnas": columnas,
            "filas": filas,
            "total": packed.get("total") or 0,
            "truncadas": bool(packed.get("truncated")),
        }
    )
    return render(request, "integraciones/moreapp_usuarios_fuente.html", context)
