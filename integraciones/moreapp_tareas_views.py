"""Crear y listar tareas MoreApp (aviso en la app, aparecen en Tareas)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from web.decorators import admin_or_administrativo

from .models import MoreAppTareaEnviada
from .moreapp_api import (
    MoreAppApiConfigError,
    MoreAppApiError,
    create_task,
    get_form,
    list_all_forms,
    list_users,
)
from .moreapp_catalogo_views import _as_list, _extract_version_fields, _form_row, _user_row
from .moreapp_http import assert_safe_id
from .moreapp_registros_views import _campos_desde_formulario

_SKIP_PREFILL = {
    "pin",
    "signature",
    "drawing",
    "file",
    "lookup",
    "search",
    "catalogue",
    "catalog",
    "header",
    "image",
    "subform",
    "photo",
    "location",
}


def _dt_from_local(raw: str):
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(text, fmt)
            return timezone.make_aware(naive, timezone.get_current_timezone())
        except ValueError:
            continue
    return None


def _millis(aware) -> Optional[int]:
    if aware is None:
        return None
    return int(aware.timestamp() * 1000)


def _campos_precargables(campos: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows = []
    seen = set()
    for campo in campos:
        widget = str(campo.get("widget") or "")
        key = str(campo.get("data_name") or "").strip()
        if not key or key in seen or widget in _SKIP_PREFILL:
            continue
        seen.add(key)
        rows.append(
            {
                "key": key,
                "label": str(campo.get("label") or key),
                "widget": widget,
            }
        )
    return rows


def _formularios_activos() -> List[Dict[str, Any]]:
    rows = []
    for item in list_all_forms():
        if not isinstance(item, dict):
            continue
        row = _form_row(item)
        if str(row.get("status") or "").upper() == "TRASH":
            continue
        rows.append(row)
    return rows


def _group_ids_de_usuario(item: Dict[str, Any]) -> List[str]:
    raw_groups = item.get("groups") if isinstance(item.get("groups"), list) else []
    ids = []
    seen = set()
    for group in raw_groups:
        if isinstance(group, dict):
            gid = str(group.get("id") or group.get("groupId") or "").strip()
        else:
            gid = str(group or "").strip()
        if gid and gid not in seen:
            seen.add(gid)
            ids.append(gid)
    return ids


def _grupo_etiqueta(nombre: str, group_id: str, miembros: int) -> str:
    n = miembros
    sufijo = "%s persona%s" % (n, "" if n == 1 else "s")
    if nombre and nombre != group_id:
        return "%s · %s" % (nombre, sufijo)
    short = group_id[-6:] if len(group_id) > 6 else group_id
    return "Grupo %s · %s" % (short, sufijo)


def _grupos_desde_usuarios(raw_users: Any) -> List[Dict[str, str]]:
    grupos: Dict[str, Dict[str, str]] = {}
    counts: Dict[str, int] = {}
    for item in _items_de_lista(raw_users, ("users",)):
        if not isinstance(item, dict):
            continue
        for gid in _group_ids_de_usuario(item):
            counts[gid] = counts.get(gid, 0) + 1
            if gid in grupos:
                continue
            raw_groups = item.get("groups") if isinstance(item.get("groups"), list) else []
            nombre = gid
            for group in raw_groups:
                if isinstance(group, dict) and str(group.get("id") or group.get("groupId") or "") == gid:
                    nombre = str(group.get("name") or group.get("label") or gid)
                    break
            grupos[gid] = {"id": gid, "nombre": nombre}
    rows = []
    for gid, row in grupos.items():
        n = counts.get(gid, 0)
        rows.append({"id": gid, "nombre": _grupo_etiqueta(row.get("nombre") or gid, gid, n)})
    return rows


def _emails_de_grupos(usuarios: List[Dict[str, Any]], group_ids: List[str]) -> List[str]:
    wanted = {item for item in group_ids if item}
    emails: List[str] = []
    seen = set()
    for user in usuarios:
        ids = set(user.get("group_ids") or [])
        if not wanted.intersection(ids):
            continue
        email = str(user.get("email") or "").strip()
        if email and email not in seen:
            seen.add(email)
            emails.append(email)
    return emails


def _usuarios_moreapp() -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    raw = list_users()
    rows = []
    for item in _items_de_lista(raw, ("users",)):
        if not isinstance(item, dict):
            continue
        row = _user_row(item)
        row["group_ids"] = _group_ids_de_usuario(item)
        if row.get("disabled") or not row.get("email"):
            continue
        rows.append(row)
    return rows, _grupos_desde_usuarios(raw)


def _items_de_lista(raw: Any, extra_keys: Tuple[str, ...] = ()) -> List[Any]:
    items = _as_list(raw)
    if items:
        return items
    if isinstance(raw, dict):
        for key in extra_keys:
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def _coord(raw: str):
    text = (raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _payload_tarea(
    *,
    recipients: List[str],
    message: str,
    data: Dict[str, Any],
    envio: str,
    programada,
    limite,
    ubicacion: str,
    lat: str,
    lng: str,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "recipients": list(recipients),
        "message": message,
        "publishInfo": {"type": "IMMEDIATE"},
    }
    if data:
        payload["data"] = data
    if envio == "SCHEDULED" and programada is not None:
        payload["publishInfo"] = {"type": "SCHEDULED", "value": _millis(programada)}
    if limite is not None:
        payload["dueDate"] = _millis(limite)
    lat_n = _coord(lat)
    lng_n = _coord(lng)
    if ubicacion or (lat_n is not None and lng_n is not None):
        loc: Dict[str, Any] = {}
        if ubicacion:
            loc["name"] = ubicacion
        if lat_n is not None and lng_n is not None:
            loc["lat"] = lat_n
            loc["lng"] = lng_n
        payload["location"] = loc
    return payload


@admin_or_administrativo
def tareas_list_view(request):
    return render(
        request,
        "integraciones/moreapp_tareas.html",
        {
            "tareas": MoreAppTareaEnviada.objects.select_related("creado_por")[:80],
        },
    )


@require_GET
@admin_or_administrativo
def tarea_campos_view(request, form_id: str):
    try:
        form_id = assert_safe_id(form_id, "formId")
        formulario = get_form(form_id)
        campos = _campos_desde_formulario(formulario if isinstance(formulario, dict) else {})
        if not campos and isinstance(formulario, dict):
            campos = _extract_version_fields(formulario)
        return JsonResponse({"ok": True, "campos": _campos_precargables(campos)})
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        return JsonResponse({"ok": False, "error": str(exc), "campos": []}, status=400)


@require_http_methods(["GET", "POST"])
@admin_or_administrativo
def tarea_crear_view(request):
    context = {
        "formularios": [],
        "usuarios": [],
        "grupos": [],
        "error": "",
        "form_id": (request.POST.get("form_id") or request.GET.get("form_id") or "").strip(),
        "mensaje": (request.POST.get("mensaje") or "").strip(),
        "envio": (request.POST.get("envio") or "IMMEDIATE").strip() or "IMMEDIATE",
        "programada_para": (request.POST.get("programada_para") or "").strip(),
        "fecha_limite": (request.POST.get("fecha_limite") or "").strip(),
        "ubicacion": (request.POST.get("ubicacion") or "").strip(),
        "latitud": (request.POST.get("latitud") or "").strip(),
        "longitud": (request.POST.get("longitud") or "").strip(),
        "usuarios_sel": [item.strip() for item in request.POST.getlist("usuarios") if item.strip()],
        "grupos_sel": [item.strip() for item in request.POST.getlist("grupos") if item.strip()],
    }
    try:
        context["formularios"] = _formularios_activos()
        usuarios, grupos = _usuarios_moreapp()
        context["usuarios"] = usuarios
        context["grupos"] = grupos
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
        return render(request, "integraciones/moreapp_tarea_crear.html", context)

    if request.method != "POST":
        return render(request, "integraciones/moreapp_tarea_crear.html", context)

    form_id = context["form_id"]
    mensaje = context["mensaje"][:500]
    envio = "SCHEDULED" if context["envio"] == "SCHEDULED" else "IMMEDIATE"
    recipients = [item.strip() for item in request.POST.getlist("usuarios") if item.strip()]
    groups = [item.strip() for item in request.POST.getlist("grupos") if item.strip()]
    programada = _dt_from_local(context["programada_para"]) if envio == "SCHEDULED" else None
    limite = _dt_from_local(context["fecha_limite"])
    nombres = {row["id"]: row["name"] for row in context["formularios"]}
    permitidos = set()
    try:
        form_id = assert_safe_id(form_id, "formId")
        formulario = get_form(form_id)
        campos = _campos_desde_formulario(formulario if isinstance(formulario, dict) else {})
        permitidos = {item["key"] for item in _campos_precargables(campos)}
        if not nombres.get(form_id) and isinstance(formulario, dict):
            nombres[form_id] = _form_row(formulario).get("name") or form_id
    except (MoreAppApiConfigError, MoreAppApiError):
        permitidos = set()

    data = {}
    for key, value in request.POST.items():
        if not key.startswith("prefill__"):
            continue
        field = key[len("prefill__") :]
        text = (value or "").strip()
        if field in permitidos and text:
            data[field] = text

    if not form_id:
        messages.error(request, "Elige el formulario que hay que llenar.")
        return render(request, "integraciones/moreapp_tarea_crear.html", context)
    if not recipients and not groups:
        messages.error(request, "Asigna la tarea a uno o varios usuarios, o a un grupo.")
        return render(request, "integraciones/moreapp_tarea_crear.html", context)
    group_emails = _emails_de_grupos(context["usuarios"], groups)
    all_recipients: List[str] = []
    seen_emails = set()
    for email in recipients + group_emails:
        if email and email not in seen_emails:
            seen_emails.add(email)
            all_recipients.append(email)
    if not all_recipients:
        messages.error(request, "El grupo elegido no tiene usuarios MoreApp activos con correo.")
        return render(request, "integraciones/moreapp_tarea_crear.html", context)
    if not mensaje:
        messages.error(request, "Escribe un mensaje corto para quien reciba la tarea.")
        return render(request, "integraciones/moreapp_tarea_crear.html", context)
    if envio == "SCHEDULED" and programada is None:
        messages.error(request, "Indica la fecha y hora programadas de envío.")
        return render(request, "integraciones/moreapp_tarea_crear.html", context)

    payload = _payload_tarea(
        recipients=all_recipients,
        message=mensaje,
        data=data,
        envio=envio,
        programada=programada,
        limite=limite,
        ubicacion=context["ubicacion"][:255],
        lat=context["latitud"],
        lng=context["longitud"],
    )
    tarea = MoreAppTareaEnviada(
        form_id=form_id,
        form_name=nombres.get(form_id) or form_id,
        mensaje=mensaje,
        destinatarios=recipients,
        grupos=groups,
        envio=envio,
        programada_para=programada,
        fecha_limite=limite,
        ubicacion=context["ubicacion"][:255],
        latitud=context["latitud"][:40],
        longitud=context["longitud"][:40],
        datos_precarga=data,
        creado_por=request.user,
    )
    try:
        created = create_task(form_id, payload)
        task_id = ""
        if isinstance(created, dict):
            task_id = str(created.get("id") or created.get("taskId") or "")
            if not task_id and isinstance(created.get("data"), dict):
                task_id = str(created["data"].get("id") or "")
        tarea.task_id = task_id[:80]
        tarea.save()
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        tarea.error = str(exc)
        tarea.save()
        messages.error(request, str(exc))
        return render(request, "integraciones/moreapp_tarea_crear.html", context)

    messages.success(
        request,
        "Tarea creada. MoreApp avisa dentro de la app (no por correo) y aparece en Tareas del celular o tablet.",
    )
    return redirect("moreapp_tareas_list")
