"""Endpoints internos para Fase 2 (Acceso y extracción) de MoreApp."""

from __future__ import annotations

import json

from django.http import HttpResponse
from django.views.decorators.http import require_GET, require_http_methods

from web.decorators import admin_only

from .moreapp_api import (
    download_registration_file,
    get_submission,
    get_user,
    list_exportable_fields,
    list_submissions,
    list_users,
)
from .moreapp_http import assert_safe_id, json_error, json_ok


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
