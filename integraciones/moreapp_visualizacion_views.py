"""Endpoints internos para Fase 1 (Visualización) de MoreApp."""

from __future__ import annotations

from django.views.decorators.http import require_GET

from web.decorators import admin_only

from .moreapp_api import (
    get_datasource,
    get_form,
    get_form_version,
    list_datasources,
    list_form_versions,
    list_forms,
)
from .moreapp_http import assert_safe_id, json_error, json_ok


@require_GET
@admin_only
def v1_visualizacion_forms_list(request):
    try:
        page = int(request.GET.get("page", "0") or 0)
        query = (request.GET.get("query") or "").strip()
        data = list_forms(page=page, query_text=query)
        return json_ok(data, modulo="visualizacion", operacion="forms.list")
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="visualizacion", operacion="forms.list")


@require_GET
@admin_only
def v1_visualizacion_form_detail(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
        data = get_form(form_id)
        return json_ok(data, modulo="visualizacion", operacion="forms.detail")
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="visualizacion", operacion="forms.detail")


@require_GET
@admin_only
def v1_visualizacion_form_versions(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
        page = int(request.GET.get("page", "0") or 0)
        size = int(request.GET.get("size", "10") or 10)
        branding_id = (request.GET.get("brandingId") or "").strip()
        data = list_form_versions(form_id, page=page, size=size, branding_id=branding_id)
        return json_ok(data, modulo="visualizacion", operacion="forms.versions.list")
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="visualizacion", operacion="forms.versions.list")


@require_GET
@admin_only
def v1_visualizacion_form_version_detail(request, form_id: str, form_version_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
        form_version_id = assert_safe_id(form_version_id, "formVersionId")
        branding_id = (request.GET.get("brandingId") or "").strip()
        data = get_form_version(form_id, form_version_id, branding_id=branding_id)
        return json_ok(data, modulo="visualizacion", operacion="forms.versions.detail")
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="visualizacion", operacion="forms.versions.detail")


@require_GET
@admin_only
def v1_visualizacion_datasources_list(request):
    try:
        data = list_datasources()
        return json_ok(data, modulo="visualizacion", operacion="datasources.list")
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="visualizacion", operacion="datasources.list")


@require_GET
@admin_only
def v1_visualizacion_datasource_detail(request, datasource_id: str):
    try:
        datasource_id = assert_safe_id(datasource_id, "datasourceId")
        data = get_datasource(datasource_id)
        return json_ok(data, modulo="visualizacion", operacion="datasources.detail")
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="visualizacion", operacion="datasources.detail")
