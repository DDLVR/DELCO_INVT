"""Crear y listar tareas MoreApp (aviso en la app, aparecen en Tareas)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from clientes.models import Cliente
from web.decorators import admin_or_administrativo

from .models import MoreAppTareaEnviada
from .moreapp_api import (
    MoreAppApiConfigError,
    MoreAppApiError,
    create_task,
    get_form,
    group_names_by_id,
    list_all_forms,
    list_datasource_entry_rows,
    list_users,
)
from .moreapp_catalogo_views import _as_list, _extract_version_fields, _form_row, _user_row
from .moreapp_http import assert_safe_id
from .moreapp_registros_views import _campos_desde_formulario
from .moreapp_tareas_lote import (
    MAX_CANTIDAD,
    MAX_FILAS_LISTADO,
    MAX_LOTE,
    destino_listado,
    fila_cliente_en_fuente,
    parse_fecha_lote,
    parse_filas_listado,
    parse_lote_archivo,
    parse_ubicacion_lote,
    plantilla_xlsx,
    resolver_destinatario,
    resolver_formulario,
    split_destinatarios,
    unicos,
)

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


def _tiene_version_publicada(row: Dict[str, Any]) -> bool:
    version = str(row.get("published_version") or "").strip()
    if version:
        return True
    published = row.get("publishedVersion")
    if isinstance(published, dict):
        return bool(str(published.get("formVersion") or "").strip())
    return bool(str(published or "").strip())


def _formularios_activos() -> List[Dict[str, Any]]:
    rows = []
    for item in list_all_forms():
        if not isinstance(item, dict):
            continue
        row = _form_row(item)
        if str(row.get("status") or "").upper() == "TRASH":
            continue
        if not _tiene_version_publicada(row):
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


def _parece_id_moreapp(valor: str) -> bool:
    text = (valor or "").strip().lower()
    if not text:
        return False
    return all(ch in "0123456789abcdef" for ch in text) and len(text) >= 6


def _nombre_corto_usuario(item: Dict[str, Any]) -> str:
    settings_user = item.get("settings") if isinstance(item.get("settings"), dict) else {}
    full = " ".join(
        part
        for part in (
            str(settings_user.get("firstName") or "").strip(),
            str(settings_user.get("lastName") or "").strip(),
        )
        if part
    )
    for candidate in (
        settings_user.get("displayName"),
        settings_user.get("name"),
        full,
        item.get("username"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _grupo_etiqueta(nombre: str, group_id: str, miembros: int, ejemplos: List[str]) -> str:
    n = miembros
    sufijo = "%s persona%s" % (n, "" if n == 1 else "s")
    if nombre and nombre != group_id and not _parece_id_moreapp(nombre):
        return "%s · %s" % (nombre, sufijo)
    extra = ", ".join(ejemplos[:3])
    if extra:
        return "%s · %s" % (sufijo, extra)
    return "Grupo · %s" % sufijo


def _detalle_grupo(miembros: int, ejemplos: List[str]) -> str:
    n = miembros
    sufijo = "%s persona%s" % (n, "" if n == 1 else "s")
    extra = ", ".join(ejemplos[:3])
    if extra:
        return "%s · %s" % (sufijo, extra)
    return sufijo


def _nombres_grupos_guardados(group_ids: List[Any]) -> List[str]:
    ids: List[str] = []
    for item in group_ids or []:
        if isinstance(item, dict):
            gid = str(item.get("id") or "").strip()
        else:
            gid = str(item or "").strip()
        if gid:
            ids.append(gid)
    official = group_names_by_id()
    labels = []
    for gid in ids:
        name = str(official.get(gid) or "").strip()
        if name and name != gid and not _parece_id_moreapp(name):
            labels.append(name)
    return labels


def _grupos_desde_usuarios(raw_users: Any) -> List[Dict[str, Any]]:
    grupos: Dict[str, Dict[str, str]] = {}
    counts: Dict[str, int] = {}
    ejemplos: Dict[str, List[str]] = {}
    official = group_names_by_id()
    for item in _items_de_lista(raw_users, ("users",)):
        if not isinstance(item, dict):
            continue
        visible = _nombre_corto_usuario(item)
        for gid in _group_ids_de_usuario(item):
            counts[gid] = counts.get(gid, 0) + 1
            if visible:
                names = ejemplos.setdefault(gid, [])
                if visible not in names and len(names) < 3:
                    names.append(visible)
            if gid in grupos:
                continue
            raw_groups = item.get("groups") if isinstance(item.get("groups"), list) else []
            nombre = str(official.get(gid) or "")
            if not nombre:
                for group in raw_groups:
                    if isinstance(group, dict) and str(group.get("id") or group.get("groupId") or "") == gid:
                        nombre = str(group.get("name") or group.get("label") or "")
                        break
            grupos[gid] = {"id": gid, "nombre": nombre}
    rows = []
    for gid, row in grupos.items():
        n = counts.get(gid, 0)
        sample = ejemplos.get(gid) or []
        api_name = str(row.get("nombre") or "").strip()
        if api_name == gid or _parece_id_moreapp(api_name):
            api_name = ""
        rows.append(
            {
                "id": gid,
                "nombre": _grupo_etiqueta(api_name, gid, n, sample),
                "detalle": _detalle_grupo(n, sample) if api_name else "",
            }
        )
    rows.sort(key=lambda item: (0 if item.get("detalle") else 1, (item.get("nombre") or "").lower()))
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
        "data": data if isinstance(data, dict) else {},
        "publishInfo": {"type": "IMMEDIATE"},
    }
    if envio == "SCHEDULED" and programada is not None:
        payload["publishInfo"] = {"type": "SCHEDULED", "value": _millis(programada)}
    if limite is not None:
        payload["dueDate"] = _millis(limite)
    lat_n = _coord(lat)
    lng_n = _coord(lng)
    if lat_n is not None and lng_n is not None:
        formatted = ubicacion or ("%s, %s" % (lat_n, lng_n))
        payload["location"] = {
            "formattedValue": formatted,
            "coordinates": {"latitude": lat_n, "longitude": lng_n},
        }
    return payload


def _mensaje_error_tarea(exc: Exception) -> str:
    text = str(exc)
    lower = text.lower()
    if "no user has the necessary permissions" in lower:
        return (
            "MoreApp no creó la tarea: nadie de los destinatarios tiene acceso a ese formulario. "
            "Asígnaselo primero en MoreApp (usuarios o grupo) y vuelve a enviar."
        )
    if "published version" in lower:
        return (
            "MoreApp no creó la tarea: ese formulario no tiene una versión publicada. "
            "Publícalo en MoreApp y vuelve a enviar."
        )
    return text


def _error_visible_tarea(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    return _mensaje_error_tarea(MoreAppApiError(text))


def _es_widget(campo: Dict[str, Any], *nombres: str) -> bool:
    widget = str(campo.get("widget") or "").lower()
    compact = "".join(ch for ch in widget if ch.isalnum())
    for nombre in nombres:
        needle = "".join(ch for ch in nombre.lower() if ch.isalnum())
        if widget == nombre.lower() or compact == needle or compact.endswith(needle) or compact.endswith(needle + "widget"):
            return True
    return False


def _campos_formulario(form_id: str, cache: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if form_id in cache:
        return cache[form_id]
    campos: List[Dict[str, Any]] = []
    try:
        formulario = get_form(form_id)
        if isinstance(formulario, dict):
            campos = _campos_desde_formulario(formulario)
            if not campos:
                campos = _extract_version_fields(formulario)
    except (MoreAppApiConfigError, MoreAppApiError):
        campos = []
    cache[form_id] = campos
    return campos


def _precarga_search_cliente(
    campos: List[Dict[str, Any]],
    numero_cliente: str,
    cache: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    numero = (numero_cliente or "").strip()
    if not numero:
        return {}
    search_fields = [item for item in campos if _es_widget(item, "search")]
    if not search_fields:
        return {}
    preferred = []
    for item in search_fields:
        haystack = "%s %s" % (item.get("data_name") or "", item.get("label") or "")
        lower = haystack.lower()
        if "cliente" in lower or "cuenta" in lower:
            preferred.append(item)
    data: Dict[str, Any] = {}
    for campo in preferred or search_fields:
        key = str(campo.get("data_name") or "").strip()
        ds_id = str(campo.get("datasource_id") or "").strip()
        if not key or not ds_id:
            continue
        if ds_id not in cache:
            try:
                payload = list_datasource_entry_rows(ds_id)
                filas = payload.get("rows") if isinstance(payload, dict) else []
                cache[ds_id] = [row for row in filas if isinstance(row, dict)]
            except (MoreAppApiConfigError, MoreAppApiError):
                cache[ds_id] = []
        fila = fila_cliente_en_fuente(cache[ds_id], numero)
        if fila:
            data[key] = fila
            break
    return data


def _destinatarios_finales(
    emails: List[str],
    group_ids: List[str],
    usuarios: List[Dict[str, Any]],
) -> Tuple[List[str], List[str], str]:
    emails_sel = unicos(emails)
    groups_sel = unicos(group_ids)
    all_recipients = unicos(emails_sel + _emails_de_grupos(usuarios, groups_sel))
    if not all_recipients:
        if groups_sel:
            return [], groups_sel, "El grupo elegido no tiene usuarios MoreApp activos con correo."
        return [], groups_sel, "Asigna la tarea a un usuario o grupo de MoreApp."
    return all_recipients, groups_sel, ""


def _enviar_tarea_registrada(
    *,
    form_id: str,
    form_name: str,
    recipients_sel: List[str],
    groups_sel: List[str],
    all_recipients: List[str],
    mensaje: str,
    data: Dict[str, Any],
    envio: str = "IMMEDIATE",
    programada=None,
    limite=None,
    ubicacion: str = "",
    lat: str = "",
    lng: str = "",
    user=None,
    cuenta: str = "",
) -> Tuple[MoreAppTareaEnviada, str]:
    payload = _payload_tarea(
        recipients=all_recipients,
        message=mensaje,
        data=data,
        envio=envio,
        programada=programada,
        limite=limite,
        ubicacion=ubicacion,
        lat=lat,
        lng=lng,
    )
    tarea = MoreAppTareaEnviada(
        form_id=form_id,
        form_name=form_name,
        mensaje=mensaje,
        destinatarios=recipients_sel,
        grupos=groups_sel,
        envio=envio,
        programada_para=programada,
        fecha_limite=limite,
        ubicacion=(ubicacion or "")[:255],
        latitud=(lat or "")[:40],
        longitud=(lng or "")[:40],
        datos_precarga=data,
        creado_por=user,
        cuenta=(cuenta or "")[:80],
    )
    from .moreapp_tareas_ciclo import cuenta_desde_precarga, registrar_ciclo_envio

    if not tarea.cuenta:
        tarea.cuenta = cuenta_desde_precarga(data)
    live = None
    live_pub = False
    try:
        live = get_form(form_id) if form_id else {}
        if isinstance(live, dict):
            live_pub = _tiene_version_publicada(live) or _tiene_version_publicada(_form_row(live))
    except (MoreAppApiConfigError, MoreAppApiError):
        live = None
    if isinstance(live, dict) and not live_pub:
        translated = _mensaje_error_tarea(
            MoreAppApiError("Could not find published version for this form")
        )
        tarea.error = translated
        tarea.save()
        registrar_ciclo_envio(tarea)
        return tarea, translated
    try:
        created = create_task(form_id, payload)
        task_id = ""
        if isinstance(created, dict):
            task_id = str(created.get("id") or created.get("taskId") or "")
            if not task_id and isinstance(created.get("data"), dict):
                task_id = str(created["data"].get("id") or "")
        tarea.task_id = task_id[:80]
        tarea.save()
        registrar_ciclo_envio(tarea)
        return tarea, ""
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        translated = _mensaje_error_tarea(exc)
        tarea.error = translated
        tarea.save()
        registrar_ciclo_envio(tarea)
        return tarea, translated


def _contexto_destinatarios(request):
    context = {
        "formularios": [],
        "usuarios": [],
        "grupos": [],
        "error": "",
        "form_id": (request.POST.get("form_id") or request.GET.get("form_id") or "").strip(),
        "mensaje": (request.POST.get("mensaje") or "").strip(),
        "fecha_limite": (request.POST.get("fecha_limite") or "").strip(),
        "usuarios_sel": [item.strip() for item in request.POST.getlist("usuarios") if item.strip()],
        "grupos_sel": [item.strip() for item in request.POST.getlist("grupos") if item.strip()],
        "resultados": [],
        "max_lote": MAX_LOTE,
    }
    try:
        context["formularios"] = _formularios_activos()
        usuarios, grupos = _usuarios_moreapp()
        context["usuarios"] = usuarios
        context["grupos"] = grupos
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        context["error"] = str(exc)
        messages.error(request, str(exc))
    return context


def _clientes_para_lote() -> List[Cliente]:
    return list(
        Cliente.objects.filter(activo=True)
        .exclude(numero_cliente__in=["", "0"])
        .order_by("numero_cliente")
        .only("id", "numero_cliente", "direccion", "comuna")[:400]
    )


def _render_tareas_list(request, extra: Optional[Dict[str, Any]] = None, *, lote_modal: str = ""):
    context = dict(extra or {})
    context.setdefault("formularios", [])
    context.setdefault("usuarios", [])
    context.setdefault("grupos", [])
    context.setdefault("error", "")
    context.setdefault("form_id", "")
    context.setdefault("mensaje", "")
    context.setdefault("fecha_limite", "")
    context.setdefault("usuarios_sel", [])
    context.setdefault("grupos_sel", [])
    context.setdefault("clientes", [])
    context.setdefault("clientes_sel", [])
    context.setdefault("numeros_extra", "")
    context.setdefault("archivo_nombre", "")
    context.setdefault("resultados", [])
    context.setdefault("max_lote", MAX_LOTE)
    context.setdefault("max_cantidad", MAX_CANTIDAD)
    context.setdefault("max_filas_listado", MAX_FILAS_LISTADO)
    context["lote_modal"] = lote_modal or context.get("lote_modal") or (request.GET.get("lote") or "").strip()
    from .moreapp_tareas_ciclo import (
        conteos_alertas_tareas,
        intervalo_auto_sync_tareas,
        kpis_tareas,
        marcar_alertas_leidas,
        sincronizar_tareas_si_corresponde,
    )

    try:
        sincronizar_tareas_si_corresponde()
    except Exception:
        pass

    user = getattr(request, "user", None)
    context["tareas_aviso"] = conteos_alertas_tareas(user)
    marcar_alertas_leidas(user)

    estado_filtro = (request.GET.get("estado") or "").strip()
    form_filtro = (request.GET.get("formulario") or "").strip()
    cuenta_filtro = (request.GET.get("cuenta") or "").strip()
    buscar = (request.GET.get("buscar") or "").strip()
    fecha_desde = (request.GET.get("fecha_desde") or "").strip()
    fecha_hasta = (request.GET.get("fecha_hasta") or "").strip()
    periodo = (request.GET.get("periodo") or "").strip().lower()

    qs = MoreAppTareaEnviada.objects.select_related("creado_por", "integracion").prefetch_related("eventos")
    if estado_filtro:
        qs = qs.filter(estado=estado_filtro)
    if form_filtro:
        qs = qs.filter(Q(form_name=form_filtro) | Q(form_id=form_filtro))
    if cuenta_filtro:
        qs = qs.filter(cuenta__icontains=cuenta_filtro)
    if buscar:
        qs = qs.filter(
            Q(mensaje__icontains=buscar)
            | Q(form_name__icontains=buscar)
            | Q(cuenta__icontains=buscar)
            | Q(task_id__icontains=buscar)
        )
    ahora = timezone.now()
    if periodo == "7":
        qs = qs.filter(fecha_creacion__gte=ahora - timedelta(days=7))
    elif periodo == "30":
        qs = qs.filter(fecha_creacion__gte=ahora - timedelta(days=30))
    else:
        if fecha_desde:
            try:
                d0 = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
                qs = qs.filter(fecha_creacion__date__gte=d0)
            except ValueError:
                fecha_desde = ""
        if fecha_hasta:
            try:
                d1 = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
                qs = qs.filter(fecha_creacion__date__lte=d1)
            except ValueError:
                fecha_hasta = ""

    resumen_estado = {
        row["estado"]: row["c"] for row in qs.values("estado").annotate(c=Count("id"))
    }
    por_formulario = list(
        qs.exclude(form_name="")
        .values("form_name")
        .annotate(n=Count("id"))
        .order_by("-n")[:8]
    )
    total = qs.count()
    con_informe = qs.filter(integracion__isnull=False).count()
    con_completadas = resumen_estado.get(MoreAppTareaEnviada.ESTADO_COMPLETADA, 0)

    try:
        per_page = int(request.GET.get("per_page") or 50)
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in (25, 50, 100):
        per_page = 50
    page_obj = Paginator(qs, per_page).get_page(request.GET.get("page") or 1)
    tareas = list(page_obj.object_list)
    for tarea in tareas:
        tarea.grupos_nombres = _nombres_grupos_guardados(tarea.grupos)
        tarea.tiene_contenido = bool(tarea.integracion_id) or tarea.estado == MoreAppTareaEnviada.ESTADO_COMPLETADA
        tarea.puede_pdf = tarea.estado == MoreAppTareaEnviada.ESTADO_COMPLETADA

    query_params = request.GET.copy()
    query_params.pop("page", None)
    formularios_filtro = list(
        MoreAppTareaEnviada.objects.exclude(form_name="")
        .values_list("form_name", flat=True)
        .distinct()
        .order_by("form_name")
    )
    context.update(
        {
            "tareas": tareas,
            "page_obj": page_obj,
            "query_string": query_params.urlencode(),
            "kpis_tareas": kpis_tareas(),
            "tareas_auto_refresh_seconds": intervalo_auto_sync_tareas(),
            "estado_filtro": estado_filtro,
            "form_filtro": form_filtro,
            "cuenta_filtro": cuenta_filtro,
            "buscar": buscar,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "periodo": periodo,
            "formularios_filtro": formularios_filtro,
            "estados_filtro": MoreAppTareaEnviada.ESTADO_CHOICES,
            "resumen": {
                "total": total,
                "abiertas": resumen_estado.get(MoreAppTareaEnviada.ESTADO_ASIGNADA, 0),
                "completadas": con_completadas,
                "errores": resumen_estado.get(MoreAppTareaEnviada.ESTADO_ERROR, 0),
                "con_informe": con_informe,
                "por_formulario": por_formulario,
            },
        }
    )
    return render(request, "integraciones/moreapp_tareas.html", context)


def _payload_lote_clientes(context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": not bool(context.get("error")),
        "error": context.get("error") or "",
        "max_lote": context.get("max_lote") or MAX_LOTE,
        "max_cantidad": MAX_CANTIDAD,
        "max_filas_listado": MAX_FILAS_LISTADO,
        "formularios": [
            {"id": item.get("id") or "", "name": item.get("name") or item.get("id") or ""}
            for item in context.get("formularios") or []
        ],
        "usuarios": [
            {
                "email": item.get("email") or "",
                "nombre": item.get("nombre") or item.get("email") or "",
            }
            for item in context.get("usuarios") or []
        ],
        "grupos": [
            {
                "id": item.get("id") or "",
                "nombre": item.get("nombre") or "",
                "detalle": item.get("detalle") or "",
            }
            for item in context.get("grupos") or []
        ],
        "clientes": [
            {
                "id": cliente.pk,
                "numero_cliente": cliente.numero_cliente,
                "direccion": cliente.direccion,
                "comuna": cliente.comuna,
            }
            for cliente in context.get("clientes") or []
        ],
    }


@admin_or_administrativo
def tareas_list_view(request):
    return _render_tareas_list(request)


def _etiqueta_estado_moreapp(status: str) -> str:
    raw = (status or "").strip().lower()
    return {
        "in_progress": "en curso",
        "completed": "completada",
        "revoked": "revocada",
        "declined": "rechazada",
    }.get(raw) or (status or "en curso")


@require_POST
@admin_or_administrativo
def tareas_sincronizar_view(request):
    from .moreapp_tareas_ciclo import sincronizar_tareas_desde_api

    try:
        stats = sincronizar_tareas_desde_api()
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        messages.error(request, str(exc))
        return redirect("moreapp_tareas_list")
    if stats.get("completadas"):
        messages.success(
            request,
            "MoreApp reportó %s tarea%s terminada%s. Ya aparecen como completadas."
            % (
                stats["completadas"],
                "" if stats["completadas"] == 1 else "s",
                "" if stats["completadas"] == 1 else "s",
            ),
        )
    else:
        messages.info(
            request,
            "Ninguna tarea asignada aparece como terminada en MoreApp. Siguen en curso.",
        )
    if stats.get("errores"):
        messages.warning(
            request,
            "No se pudo consultar %s formulario%s en MoreApp."
            % (stats["errores"], "" if stats["errores"] == 1 else "s"),
        )
    return redirect("moreapp_tareas_list")


@require_POST
@admin_or_administrativo
def tarea_revisar_view(request, pk: int):
    from .moreapp_tareas_ciclo import revisar_tarea_desde_api

    tarea = get_object_or_404(MoreAppTareaEnviada, pk=pk)
    if tarea.estado == MoreAppTareaEnviada.ESTADO_COMPLETADA:
        messages.info(request, "Esta tarea ya está marcada como completada.")
        return redirect("moreapp_tarea_detalle", pk=tarea.pk)
    result = revisar_tarea_desde_api(tarea)
    if result.get("error"):
        messages.error(request, result["error"])
    elif result.get("completada"):
        messages.success(
            request,
            "El destinatario ya terminó esta tarea en MoreApp. Quedó marcada como completada.",
        )
    elif result.get("found"):
        messages.info(
            request,
            "Sigue asignada en MoreApp (%s). Aún no la terminan."
            % _etiqueta_estado_moreapp(result.get("status") or ""),
        )
    else:
        messages.warning(
            request,
            "MoreApp no devolvió esta tarea. Puede seguir pendiente o el aviso no llegó a crearse.",
        )
    return redirect("moreapp_tarea_detalle", pk=tarea.pk)


@require_GET
@admin_or_administrativo
def tarea_detalle_view(request, pk: int):
    from .moreapp_tareas_pdf import campos_rellenados_tarea, tarea_permite_pdf

    tarea = get_object_or_404(
        MoreAppTareaEnviada.objects.select_related("creado_por", "integracion").prefetch_related("eventos"),
        pk=pk,
    )
    from .moreapp_tareas_ciclo import intervalo_auto_sync_tareas

    refresh_seconds = intervalo_auto_sync_tareas()
    if tarea.estado == MoreAppTareaEnviada.ESTADO_ASIGNADA and (tarea.task_id or "").strip():
        reciente = False
        if tarea.ultima_sync:
            reciente = (timezone.now() - tarea.ultima_sync).total_seconds() < refresh_seconds
        if not reciente:
            try:
                from .moreapp_tareas_ciclo import revisar_tarea_desde_api

                revisar_tarea_desde_api(tarea)
                tarea.refresh_from_db()
            except (MoreAppApiConfigError, MoreAppApiError):
                pass
    tarea.grupos_nombres = _nombres_grupos_guardados(tarea.grupos)
    registro = tarea.integracion
    error_visible = _error_visible_tarea(tarea.error)
    submission_id = ""
    if registro is not None:
        submission_id = str(registro.moreapp_submission_id or "").strip()
        if len(submission_id) < 8:
            submission_id = ""
    return render(
        request,
        "integraciones/moreapp_tarea_detalle.html",
        {
            "tarea": tarea,
            "error_visible": error_visible,
            "campos_rellenados": campos_rellenados_tarea(tarea),
            "puede_pdf": tarea_permite_pdf(tarea),
            "registro": registro,
            "submission_id": submission_id,
            "tareas_auto_refresh_seconds": refresh_seconds,
        },
    )


@require_GET
@admin_or_administrativo
def tarea_pdf_view(request, pk: int):
    from .moreapp_tareas_pdf import pdf_bytes_tarea, tarea_permite_pdf

    tarea = get_object_or_404(
        MoreAppTareaEnviada.objects.select_related("integracion"),
        pk=pk,
    )
    if not tarea_permite_pdf(tarea):
        messages.warning(request, "El PDF está disponible cuando la tarea ya está completada.")
        return redirect("moreapp_tarea_detalle", pk=tarea.pk)
    pdf_bytes, nombre = pdf_bytes_tarea(tarea)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="%s"' % nombre.replace('"', "")
    return response


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

    elegido = next((item for item in context["formularios"] if str(item.get("id") or "") == form_id), None)
    if not form_id:
        messages.error(request, "Elige el formulario que hay que llenar.")
        return render(request, "integraciones/moreapp_tarea_crear.html", context)
    if not elegido or not _tiene_version_publicada(elegido):
        messages.error(
            request,
            "Ese formulario no tiene una versión publicada en MoreApp. Elige uno publicado o publícalo primero.",
        )
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

    tarea, error = _enviar_tarea_registrada(
        form_id=form_id,
        form_name=nombres.get(form_id) or form_id,
        recipients_sel=recipients,
        groups_sel=groups,
        all_recipients=all_recipients,
        mensaje=mensaje,
        data=data,
        envio=envio,
        programada=programada,
        limite=limite,
        ubicacion=context["ubicacion"][:255],
        lat=context["latitud"],
        lng=context["longitud"],
        user=request.user,
    )
    if error:
        messages.error(request, error)
        return render(request, "integraciones/moreapp_tarea_crear.html", context)

    messages.success(
        request,
        "Tarea creada. MoreApp avisa dentro de la app (no por correo) y aparece en Tareas del celular o tablet.",
    )
    return redirect("moreapp_tareas_list")


@require_GET
@admin_or_administrativo
def tarea_lote_plantilla_view(request):
    response = HttpResponse(
        plantilla_xlsx(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="tareas_moreapp.xlsx"'
    return response


@require_http_methods(["GET", "POST"])
@admin_or_administrativo
def tarea_lote_csv_view(request):
    if request.method != "POST":
        return redirect(reverse("moreapp_tareas_list") + "?lote=csv")
    context = _contexto_destinatarios(request)
    context["archivo_nombre"] = ""
    if context["error"]:
        return _render_tareas_list(request, context, lote_modal="csv")

    archivo = request.FILES.get("archivo")
    if not archivo:
        messages.error(request, "Sube un archivo CSV o Excel con las columnas del lote.")
        return _render_tareas_list(request, context, lote_modal="csv")

    context["archivo_nombre"] = str(getattr(archivo, "name", "") or "")
    try:
        filas, total_filas = parse_lote_archivo(context["archivo_nombre"], archivo.read())
    except ValueError as exc:
        messages.error(request, str(exc))
        return _render_tareas_list(request, context, lote_modal="csv")

    if not filas:
        messages.error(request, "El archivo no tiene filas para enviar.")
        return _render_tareas_list(request, context, lote_modal="csv")
    if total_filas > MAX_LOTE:
        messages.warning(
            request,
            "El archivo tiene %s filas. Solo se enviarán las primeras %s."
            % (total_filas, MAX_LOTE),
        )

    campos_cache: Dict[str, List[Dict[str, Any]]] = {}
    ds_cache: Dict[str, List[Dict[str, Any]]] = {}
    resultados = []
    enviadas = 0
    for idx, fila in enumerate(filas, start=2):
        resultado = {
            "fila": idx,
            "formulario": fila.get("formulario") or "",
            "destinatario": fila.get("destinatario") or "",
            "cliente": fila.get("cliente") or "",
            "ok": False,
            "precarga": False,
            "error": "",
        }
        form = resolver_formulario(fila.get("formulario") or "", context["formularios"])
        if not form:
            resultado["error"] = "Formulario no encontrado o sin versión publicada."
            resultados.append(resultado)
            continue
        form_id = str(form.get("id") or "").strip()
        tokens = split_destinatarios(fila.get("destinatario") or "")
        emails: List[str] = []
        group_ids: List[str] = []
        token_error = ""
        for token in tokens:
            found_emails, found_groups, token_error = resolver_destinatario(
                token, context["usuarios"], context["grupos"]
            )
            if token_error:
                break
            emails.extend(found_emails)
            group_ids.extend(found_groups)
        if token_error:
            resultado["error"] = token_error
            resultados.append(resultado)
            continue
        all_recipients, groups_sel, dest_error = _destinatarios_finales(
            emails, group_ids, context["usuarios"]
        )
        if dest_error:
            resultado["error"] = dest_error
            resultados.append(resultado)
            continue
        mensaje = (fila.get("mensaje") or "").strip()[:500]
        if not mensaje:
            mensaje = "Tarea asignada desde la intranet"
        cliente = (fila.get("cliente") or "").strip()
        if cliente:
            mensaje = ("%s · %s" % (mensaje, cliente))[:500]
        limite = _dt_from_local(parse_fecha_lote(fila.get("fecha") or ""))
        ubicacion, lat, lng = parse_ubicacion_lote(fila.get("ubicacion") or "")
        if cliente and not ubicacion:
            ficha = (
                Cliente.objects.filter(activo=True, numero_cliente=cliente)
                .only("direccion")
                .first()
            )
            if ficha:
                ubicacion = ficha.direccion
        campos = _campos_formulario(form_id, campos_cache)
        data = _precarga_search_cliente(campos, cliente, ds_cache)
        _tarea, error = _enviar_tarea_registrada(
            form_id=form_id,
            form_name=str(form.get("name") or form_id),
            recipients_sel=unicos(emails),
            groups_sel=groups_sel,
            all_recipients=all_recipients,
            mensaje=mensaje,
            data=data,
            limite=limite,
            ubicacion=ubicacion,
            lat=lat,
            lng=lng,
            user=request.user,
            cuenta=cliente,
        )
        resultado["ok"] = not error
        resultado["precarga"] = bool(data)
        resultado["error"] = error
        if resultado["ok"]:
            enviadas += 1
        resultados.append(resultado)

    context["resultados"] = resultados
    fallidas = len(resultados) - enviadas
    if enviadas and not fallidas:
        messages.success(request, "Se enviaron %s tareas a MoreApp." % enviadas)
        return redirect("moreapp_tareas_list")
    if enviadas:
        messages.warning(
            request,
            "Se enviaron %s tareas. %s filas quedaron con error." % (enviadas, fallidas),
        )
    else:
        messages.error(request, "No se pudo enviar ninguna tarea. Revisa el detalle del lote.")
    return _render_tareas_list(request, context, lote_modal="csv")


def _clientes_lote(request) -> Tuple[List[Cliente], int]:
    ids = []
    for raw in request.POST.getlist("clientes"):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    numeros = [
        line.strip()
        for line in (request.POST.get("numeros_extra") or "").splitlines()
        if line.strip()
    ]
    if not ids and not numeros:
        return []
    qs = Cliente.objects.filter(activo=True).exclude(numero_cliente__in=["", "0"])
    if ids and numeros:
        qs = qs.filter(Q(pk__in=ids) | Q(numero_cliente__in=numeros))
    elif ids:
        qs = qs.filter(pk__in=ids)
    else:
        qs = qs.filter(numero_cliente__in=numeros)
    vistos = set()
    out: List[Cliente] = []
    for cliente in qs.order_by("numero_cliente"):
        key = (cliente.numero_cliente or "").strip()
        if key in vistos:
            continue
        vistos.add(key)
        out.append(cliente)
    total = len(out)
    return out[:MAX_LOTE], total


@require_http_methods(["GET", "POST"])
@admin_or_administrativo
def tarea_lote_clientes_view(request):
    if request.method != "POST":
        if (request.GET.get("json") or "").strip() == "1":
            context = _contexto_destinatarios(request)
            context["clientes"] = _clientes_para_lote()
            context["max_lote"] = MAX_LOTE
            status = 200 if not context.get("error") else 400
            return JsonResponse(_payload_lote_clientes(context), status=status)
        return redirect(reverse("moreapp_tareas_list") + "?lote=clientes")
    context = _contexto_destinatarios(request)
    context["numeros_extra"] = (request.POST.get("numeros_extra") or "").strip()
    context["clientes"] = _clientes_para_lote()
    context["clientes_sel"] = [item.strip() for item in request.POST.getlist("clientes") if item.strip()]
    if context["error"]:
        return _render_tareas_list(request, context, lote_modal="clientes")

    form_id = context["form_id"]
    mensaje = context["mensaje"][:500]
    elegido = next((item for item in context["formularios"] if str(item.get("id") or "") == form_id), None)
    clientes, total_clientes = _clientes_lote(request)
    if total_clientes > MAX_LOTE:
        messages.warning(
            request,
            "Hay %s clientes en la selección. Solo se enviarán los primeros %s."
            % (total_clientes, MAX_LOTE),
        )
    all_recipients, groups_sel, dest_error = _destinatarios_finales(
        context["usuarios_sel"], context["grupos_sel"], context["usuarios"]
    )
    if not form_id or not elegido:
        messages.error(request, "Elige un formulario publicado.")
        return _render_tareas_list(request, context, lote_modal="clientes")
    if dest_error:
        messages.error(request, dest_error)
        return _render_tareas_list(request, context, lote_modal="clientes")
    if not mensaje:
        messages.error(request, "Escribe un mensaje corto para quien reciba las tareas.")
        return _render_tareas_list(request, context, lote_modal="clientes")
    if not clientes:
        messages.error(request, "Elige uno o más clientes, o escribe sus números de cuenta.")
        return _render_tareas_list(request, context, lote_modal="clientes")

    try:
        form_id = assert_safe_id(form_id, "formId")
    except MoreAppApiConfigError as exc:
        messages.error(request, str(exc))
        return _render_tareas_list(request, context, lote_modal="clientes")

    limite = _dt_from_local(context["fecha_limite"])
    campos = _campos_formulario(form_id, {})
    ds_cache: Dict[str, List[Dict[str, Any]]] = {}
    resultados = []
    enviadas = 0
    form_name = str(elegido.get("name") or form_id)
    for cliente in clientes:
        numero = (cliente.numero_cliente or "").strip()
        data = _precarga_search_cliente(campos, numero, ds_cache)
        ubicacion = " ".join(
            part for part in (cliente.direccion, cliente.comuna) if part
        ).strip()
        mensaje_item = ("%s · %s" % (mensaje, numero))[:500] if numero else mensaje
        _tarea, error = _enviar_tarea_registrada(
            form_id=form_id,
            form_name=form_name,
            recipients_sel=context["usuarios_sel"],
            groups_sel=groups_sel,
            all_recipients=all_recipients,
            mensaje=mensaje_item,
            data=data,
            limite=limite,
            ubicacion=ubicacion,
            user=request.user,
            cuenta=numero,
        )
        ok = not error
        if ok:
            enviadas += 1
        resultados.append(
            {
                "fila": numero or str(cliente.pk),
                "formulario": form_name,
                "destinatario": ", ".join(all_recipients),
                "cliente": numero,
                "ok": ok,
                "precarga": bool(data),
                "error": error,
            }
        )

    context["resultados"] = resultados
    fallidas = len(resultados) - enviadas
    if enviadas and not fallidas:
        messages.success(request, "Se enviaron %s tareas, una por cliente." % enviadas)
        return redirect("moreapp_tareas_list")
    if enviadas:
        messages.warning(
            request,
            "Se enviaron %s tareas. %s clientes quedaron con error." % (enviadas, fallidas),
        )
    else:
        messages.error(request, "No se pudo enviar ninguna tarea. Revisa el detalle del lote.")
    return _render_tareas_list(request, context, lote_modal="clientes")


@require_http_methods(["GET", "POST"])
@admin_or_administrativo
def tarea_lote_listado_view(request):
    if request.method != "POST":
        if (request.GET.get("json") or "").strip() == "1":
            context = _contexto_destinatarios(request)
            context["clientes"] = []
            context["max_lote"] = MAX_LOTE
            status = 200 if not context.get("error") else 400
            payload = _payload_lote_clientes(context)
            payload.pop("clientes", None)
            return JsonResponse(payload, status=status)
        return redirect(reverse("moreapp_tareas_list") + "?lote=listado")

    context = _contexto_destinatarios(request)
    if context["error"]:
        return _render_tareas_list(request, context, lote_modal="listado")

    filas, parse_error = parse_filas_listado(request.POST)
    if parse_error:
        messages.error(request, parse_error)
        return _render_tareas_list(request, context, lote_modal="listado")

    mensaje = (context.get("mensaje") or "").strip()[:500] or "Tarea asignada desde la intranet"
    limite = _dt_from_local(context.get("fecha_limite") or "")
    resultados = []
    enviadas = 0
    for fila in filas:
        form = resolver_formulario(fila["form_id"], context["formularios"])
        if not form:
            resultados.append(
                {
                    "fila": fila["form_id"],
                    "formulario": fila["form_id"],
                    "destinatario": fila["destinatario"],
                    "cliente": str(fila["cantidad"]),
                    "ok": False,
                    "precarga": False,
                    "error": "Formulario no encontrado o sin versión publicada.",
                }
            )
            continue
        form_id = str(form.get("id") or "").strip()
        try:
            form_id = assert_safe_id(form_id, "formId")
        except MoreAppApiConfigError as exc:
            resultados.append(
                {
                    "fila": form_id,
                    "formulario": str(form.get("name") or form_id),
                    "destinatario": fila["destinatario"],
                    "cliente": str(fila["cantidad"]),
                    "ok": False,
                    "precarga": False,
                    "error": str(exc),
                }
            )
            continue
        _, valor = destino_listado(fila["destinatario"])
        emails, group_ids, token_error = resolver_destinatario(
            valor, context["usuarios"], context["grupos"]
        )
        if token_error:
            resultados.append(
                {
                    "fila": form.get("name") or form_id,
                    "formulario": str(form.get("name") or form_id),
                    "destinatario": fila["destinatario"],
                    "cliente": str(fila["cantidad"]),
                    "ok": False,
                    "precarga": False,
                    "error": token_error,
                }
            )
            continue
        all_recipients, groups_sel, dest_error = _destinatarios_finales(
            emails, group_ids, context["usuarios"]
        )
        if dest_error:
            resultados.append(
                {
                    "fila": form.get("name") or form_id,
                    "formulario": str(form.get("name") or form_id),
                    "destinatario": fila["destinatario"],
                    "cliente": str(fila["cantidad"]),
                    "ok": False,
                    "precarga": False,
                    "error": dest_error,
                }
            )
            continue
        form_name = str(form.get("name") or form_id)
        etiqueta = ", ".join(all_recipients)
        cantidad = fila["cantidad"]
        for indice in range(1, cantidad + 1):
            mensaje_item = mensaje if cantidad == 1 else ("%s · %s/%s" % (mensaje, indice, cantidad))[:500]
            _tarea, error = _enviar_tarea_registrada(
                form_id=form_id,
                form_name=form_name,
                recipients_sel=unicos(emails),
                groups_sel=groups_sel,
                all_recipients=all_recipients,
                mensaje=mensaje_item,
                data={},
                limite=limite,
                user=request.user,
            )
            ok = not error
            if ok:
                enviadas += 1
            resultados.append(
                {
                    "fila": "%s/%s" % (indice, cantidad),
                    "formulario": form_name,
                    "destinatario": etiqueta,
                    "cliente": str(cantidad),
                    "ok": ok,
                    "precarga": False,
                    "error": error,
                }
            )

    context["resultados"] = resultados
    fallidas = len(resultados) - enviadas
    if enviadas and not fallidas:
        messages.success(request, "Se enviaron %s tareas desde el listado." % enviadas)
        return redirect("moreapp_tareas_list")
    if enviadas:
        messages.warning(
            request,
            "Se enviaron %s tareas. %s quedaron con error." % (enviadas, fallidas),
        )
    else:
        messages.error(request, "No se pudo enviar ninguna tarea. Revisa el listado.")
    return _render_tareas_list(request, context, lote_modal="listado")
