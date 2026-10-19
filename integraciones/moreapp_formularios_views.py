"""Listado de formularios asignados y guardado de asignaciones desde el popup del catálogo."""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from web.decorators import admin_only, any_intranet_user

from .models import MoreAppFormularioAsignado
from .moreapp_api import MoreAppApiConfigError, MoreAppApiError, list_all_forms
from .moreapp_asignaciones import (
    asignaciones_por_form,
    enriquecer_fila,
    fila_asignada,
    usuarios_asignables,
)
from .moreapp_catalogo_views import _catalogo_return_url, _fold_text, _form_row
from .moreapp_http import assert_safe_id


@any_intranet_user
def formularios_list_view(request):
    query = (request.GET.get("query") or "").strip()
    es_admin = getattr(request.user, "rol", "") == "ADMIN"
    context = {
        "conexion": None,
        "formularios": [],
        "error": "",
        "query": query,
        "es_admin": es_admin,
        "tiene_filtros": bool(query),
    }
    if es_admin:
        asignados_ids = set(MoreAppFormularioAsignado.objects.values_list("form_id", flat=True))
    else:
        asignados_ids = set(
            MoreAppFormularioAsignado.objects.filter(usuario=request.user).values_list("form_id", flat=True)
        )
    if not asignados_ids:
        return render(request, "integraciones/moreapp_formularios.html", context)

    por_form = asignaciones_por_form()
    try:
        raw = list_all_forms()
        rows = [_form_row(item) for item in raw if isinstance(item, dict)]
        seen = set()
        visibles = []
        for row in rows:
            form_id = str(row.get("id") or "")
            seen.add(form_id)
            if form_id not in asignados_ids:
                continue
            visibles.append(enriquecer_fila(row, por_form.get(form_id, [])))
        for form_id in asignados_ids:
            if form_id in seen:
                continue
            asignados = por_form.get(form_id, [])
            nombre = asignados[0].form_name if asignados else form_id
            visibles.append(fila_asignada(form_id, nombre, asignados))
        if query:
            needle = _fold_text(query)
            visibles = [row for row in visibles if needle in _fold_text(row.get("name"))]
        context["conexion"] = {"ok": True, "forms_detected_in_first_call": len(visibles)}
        context["formularios"] = visibles
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        rows = []
        for form_id in asignados_ids:
            asignados = por_form.get(form_id, [])
            nombre = asignados[0].form_name if asignados else form_id
            rows.append(fila_asignada(form_id, nombre, asignados))
        if query:
            needle = _fold_text(query)
            rows = [row for row in rows if needle in _fold_text(row.get("name"))]
        context["formularios"] = rows
        context["error"] = str(exc)
    return render(request, "integraciones/moreapp_formularios.html", context)


@require_http_methods(["GET", "POST"])
@admin_only
def formulario_asignar_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return redirect(_catalogo_return_url(request))

    if request.method != "POST":
        return redirect(_catalogo_return_url(request))

    nombre = (request.POST.get("nombre") or "").strip()[:255]
    if not nombre:
        prev = MoreAppFormularioAsignado.objects.filter(form_id=form_id).first()
        nombre = (prev.form_name if prev else "") or form_id

    usuarios = list(usuarios_asignables())
    ids_raw = request.POST.getlist("usuarios")
    ids = []
    for value in ids_raw:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    permitidos = {user.pk: user for user in usuarios}
    with transaction.atomic():
        keep = set()
        for uid in ids:
            user = permitidos.get(uid)
            if user is None:
                continue
            obj, _created = MoreAppFormularioAsignado.objects.update_or_create(
                usuario=user,
                form_id=form_id,
                defaults={"form_name": nombre, "asignado_por": request.user},
            )
            keep.add(obj.pk)
        MoreAppFormularioAsignado.objects.filter(form_id=form_id).exclude(pk__in=keep).delete()
    count = len(keep)
    if count:
        messages.success(
            request,
            "Formulario asignado a %s usuario%s." % (count, "" if count == 1 else "s"),
        )
    else:
        messages.success(request, "Se quitaron las asignaciones de este formulario.")
    return redirect(_catalogo_return_url(request))
