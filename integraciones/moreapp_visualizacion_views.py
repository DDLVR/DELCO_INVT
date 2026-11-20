"""Endpoints internos de la API MoreApp: visualización y extracción."""

from __future__ import annotations

import json

from django.http import HttpResponse
from django.views.decorators.http import require_GET, require_http_methods

from web.decorators import admin_only

from .moreapp_api import (
    download_registration_file,
    get_datasource,
    get_form,
    get_form_version,
    get_submission,
    get_user,
    list_datasources,
    list_exportable_fields,
    list_form_versions,
    list_forms,
    list_submissions,
    list_users,
)
from .moreapp_api import assert_safe_id, json_error, json_ok


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


@require_http_methods(["POST"])
@admin_only
def v1_datos_submissions_list(request, form_id: str):
    operacion = "submissions.list"
    try:
        form_id = assert_safe_id(form_id, "formId")
        payload = json.loads(request.body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            payload = {}
        page = int(payload.pop("page", 0) or 0)
        data = list_submissions(form_id, page=page, payload=payload)
        return json_ok(data, modulo="datos", operacion=operacion)
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="datos", operacion=operacion)


@require_GET
@admin_only
def v1_datos_submission_detail(request, submission_id: str):
    operacion = "submissions.detail"
    try:
        submission_id = assert_safe_id(submission_id, "submissionId")
        data = get_submission(submission_id)
        return json_ok(data, modulo="datos", operacion=operacion)
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="datos", operacion=operacion)


@require_GET
@admin_only
def v1_datos_file_download(request, file_id: str):
    operacion = "files.download"
    try:
        file_id = assert_safe_id(file_id, "fileId")
        archivo = download_registration_file(file_id)
        response = HttpResponse(
            archivo["content"],
            content_type=archivo.get("content_type") or "application/octet-stream",
        )
        filename = archivo.get("filename") or file_id
        response["Content-Disposition"] = 'attachment; filename="%s"' % filename.replace('"', "")
        return response
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="datos", operacion=operacion)


@require_GET
@admin_only
def v1_datos_users_list(request):
    operacion = "users.list"
    try:
        data = list_users()
        return json_ok(data, modulo="datos", operacion=operacion)
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="datos", operacion=operacion)


@require_GET
@admin_only
def v1_datos_user_detail(request, user_id: str):
    operacion = "users.detail"
    try:
        user_id = assert_safe_id(user_id, "userId")
        data = get_user(user_id)
        return json_ok(data, modulo="datos", operacion=operacion)
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="datos", operacion=operacion)


@require_GET
@admin_only
def v1_datos_export_fields(request, form_id: str):
    operacion = "export.fields"
    try:
        form_id = assert_safe_id(form_id, "formId")
        data = list_exportable_fields(form_id)
        return json_ok(data, modulo="datos", operacion=operacion)
    except Exception as exc:  # noqa: BLE001
        return json_error(exc, modulo="datos", operacion=operacion)
