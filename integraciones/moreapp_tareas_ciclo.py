"""Ciclo de vida de tareas MoreApp: eventos, alertas, completado y métricas."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import MoreAppTareaAlerta, MoreAppTareaEnviada, MoreAppTareaEvento

VENTANA_MATCH_DIAS = 14
_COMPLETED_STATUSES = {
    "completed",
    "complete",
    "done",
    "closed",
    "finished",
    "submitted",
    "resolved",
}


def cuenta_desde_precarga(data: Any) -> str:
    from .moreapp_tareas_lote import cuenta_de_fila

    if not isinstance(data, dict):
        return ""
    found = cuenta_de_fila(data)
    if found:
        return found[:80]
    for value in data.values():
        if isinstance(value, dict):
            nested = cuenta_de_fila(value)
            if nested:
                return nested[:80]
    return ""


def _norm(value: Any) -> str:
    from .moreapp_fuentes import fold_header

    return fold_header(str(value or ""))


def registrar_evento(
    tarea: MoreAppTareaEnviada,
    tipo: str,
    *,
    origen: str = MoreAppTareaEvento.ORIGEN_INTRANET,
    detalle: Optional[Dict[str, Any]] = None,
) -> MoreAppTareaEvento:
    return MoreAppTareaEvento.objects.create(
        tarea=tarea,
        tipo=tipo,
        origen=origen,
        detalle=detalle if isinstance(detalle, dict) else {},
    )


def _alerta_unica(
    tarea: MoreAppTareaEnviada,
    tipo: str,
    *,
    usuario=None,
    broadcast: bool = False,
) -> MoreAppTareaAlerta:
    qs = MoreAppTareaAlerta.objects.filter(tarea=tarea, tipo=tipo, broadcast=broadcast)
    if usuario is not None:
        qs = qs.filter(usuario=usuario)
    else:
        qs = qs.filter(usuario__isnull=True)
    existente = qs.first()
    if existente:
        return existente
    return MoreAppTareaAlerta.objects.create(
        tarea=tarea,
        tipo=tipo,
        usuario=usuario,
        broadcast=broadcast,
    )


def emitir_alertas(tarea: MoreAppTareaEnviada, tipo: str) -> None:
    if tarea.creado_por_id:
        _alerta_unica(tarea, tipo, usuario=tarea.creado_por, broadcast=False)
    _alerta_unica(tarea, tipo, usuario=None, broadcast=True)
    _invalidar_caches()


def _invalidar_caches() -> None:
    try:
        from web.moreapp_avisos import invalidar_caches_aviso_moreapp

        invalidar_caches_aviso_moreapp()
    except Exception:
        pass


def registrar_ciclo_envio(tarea: MoreAppTareaEnviada) -> None:
    """Eventos y alertas al persistir un envío (éxito o error)."""
    if not tarea.cuenta:
        tarea.cuenta = cuenta_desde_precarga(tarea.datos_precarga)
    if tarea.error:
        tarea.estado = MoreAppTareaEnviada.ESTADO_ERROR
        tarea.save(update_fields=["cuenta", "estado"])
        registrar_evento(
            tarea,
            MoreAppTareaEvento.TIPO_ERROR_ENVIO,
            detalle={"error": (tarea.error or "")[:180]},
        )
        return
    ahora = timezone.now()
    tarea.estado = MoreAppTareaEnviada.ESTADO_ASIGNADA
    tarea.fecha_asignacion = tarea.fecha_asignacion or ahora
    tarea.save(update_fields=["cuenta", "estado", "fecha_asignacion"])
    registrar_evento(tarea, MoreAppTareaEvento.TIPO_CREADA)
    registrar_evento(tarea, MoreAppTareaEvento.TIPO_ASIGNADA)
    emitir_alertas(tarea, MoreAppTareaAlerta.TIPO_CREACION)


def completar_tarea(
    tarea: MoreAppTareaEnviada,
    *,
    origen: str,
    integracion=None,
    detalle: Optional[Dict[str, Any]] = None,
    cuando=None,
) -> bool:
    if tarea.estado == MoreAppTareaEnviada.ESTADO_COMPLETADA:
        return False
    if tarea.estado == MoreAppTareaEnviada.ESTADO_ERROR:
        return False
    ahora = cuando or timezone.now()
    if timezone.is_naive(ahora):
        ahora = timezone.make_aware(ahora, timezone.get_current_timezone())
    tarea.estado = MoreAppTareaEnviada.ESTADO_COMPLETADA
    tarea.fecha_completado = ahora
    tarea.ultima_sync = timezone.now()
    update = ["estado", "fecha_completado", "ultima_sync"]
    if integracion is not None:
        tarea.integracion = integracion
        update.append("integracion")
    tarea.save(update_fields=update)
    registrar_evento(
        tarea,
        MoreAppTareaEvento.TIPO_COMPLETADA,
        origen=origen,
        detalle=detalle or {},
    )
    emitir_alertas(tarea, MoreAppTareaAlerta.TIPO_COMPLETADO)
    return True


def _form_id_informe(registro) -> str:
    data = registro.datos_recibidos if isinstance(getattr(registro, "datos_recibidos", None), dict) else {}
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    return str(
        info.get("formId")
        or info.get("form_id")
        or data.get("formId")
        or ""
    ).strip()


def _form_name_informe(registro) -> str:
    procesados = registro.datos_procesados if isinstance(getattr(registro, "datos_procesados", None), dict) else {}
    data = registro.datos_recibidos if isinstance(getattr(registro, "datos_recibidos", None), dict) else {}
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    return str(
        getattr(registro, "nombre_formulario", "")
        or procesados.get("form_name")
        or info.get("formName")
        or ""
    ).strip()


def _cuenta_informe(registro) -> str:
    procesados = registro.datos_procesados if isinstance(getattr(registro, "datos_procesados", None), dict) else {}
    data = registro.datos_recibidos if isinstance(getattr(registro, "datos_recibidos", None), dict) else {}
    campos = data.get("data") if isinstance(data.get("data"), dict) else {}
    candidatos = [
        procesados.get("cliente_codigo"),
        procesados.get("cliente"),
        cuenta_desde_precarga(procesados),
        cuenta_desde_precarga(campos),
    ]
    for item in candidatos:
        value = str(item or "").strip()
        if value:
            return value[:80]
    return ""


def _misma_form(tarea: MoreAppTareaEnviada, registro) -> bool:
    form_id = _form_id_informe(registro)
    if form_id and form_id == (tarea.form_id or ""):
        return True
    nombre = _norm(_form_name_informe(registro))
    if nombre and nombre == _norm(tarea.form_name):
        return True
    return False


def intentar_completar_por_informe(registro) -> Optional[MoreAppTareaEnviada]:
    """Empareja un IntegracionMoreApp nuevo con una tarea ASIGNADA. Idempotente."""
    if registro is None:
        return None
    ya = MoreAppTareaEnviada.objects.filter(integracion_id=registro.pk).first()
    if ya:
        return None
    cuenta = _cuenta_informe(registro)
    candidatas = list(
        MoreAppTareaEnviada.objects.filter(estado=MoreAppTareaEnviada.ESTADO_ASIGNADA).order_by(
            "fecha_creacion"
        )
    )
    mismas = [item for item in candidatas if _misma_form(item, registro)]
    if not mismas:
        return None
    elegida = None
    if cuenta:
        wanted = _norm(cuenta)
        por_cuenta = [item for item in mismas if _norm(item.cuenta) == wanted]
        if len(por_cuenta) == 1:
            elegida = por_cuenta[0]
        elif len(por_cuenta) > 1:
            elegida = por_cuenta[0]
    if elegida is None:
        limite = timezone.now() - timedelta(days=VENTANA_MATCH_DIAS)
        recientes = [
            item
            for item in mismas
            if item.fecha_creacion and item.fecha_creacion >= limite
        ]
        if cuenta:
            return None
        if len(recientes) == 1:
            elegida = recientes[0]
        else:
            return None
    if not elegida:
        return None
    ok = completar_tarea(
        elegida,
        origen=MoreAppTareaEvento.ORIGEN_INFORME,
        integracion=registro,
        detalle={"submission_id": str(getattr(registro, "moreapp_submission_id", "") or "")[:80]},
        cuando=getattr(registro, "fecha_recepcion", None),
    )
    return elegida if ok else None


def _items_tareas(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if not isinstance(raw, dict):
        return []
    for key in ("elements", "data", "tasks", "content", "items"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("content") or value.get("items")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _task_id_item(item: Dict[str, Any]) -> str:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    return str(
        item.get("id")
        or item.get("taskId")
        or item.get("task_id")
        or data.get("id")
        or ""
    ).strip()


def _task_status_item(item: Dict[str, Any]) -> str:
    raw = item.get("status") or item.get("state") or item.get("taskStatus") or ""
    if isinstance(raw, dict):
        raw = raw.get("name") or raw.get("value") or raw.get("status") or ""
    return str(raw or "").strip().lower()


def _task_completed_at(item: Dict[str, Any]):
    for key in ("completedAt", "completed_at", "dateCompleted", "finishedAt", "completedDate"):
        raw = item.get(key)
        if not raw:
            continue
        if hasattr(raw, "tzinfo"):
            return raw
        parsed = parse_datetime(str(raw))
        if parsed:
            return parsed
        try:
            millis = int(raw)
            if millis > 10**12:
                millis = millis / 1000.0
            from datetime import datetime, timezone as dt_tz

            return datetime.fromtimestamp(millis, tz=dt_tz.utc)
        except (TypeError, ValueError, OSError):
            continue
    return None


def _tarea_api_completada(item: Dict[str, Any]) -> bool:
    status = _task_status_item(item)
    if status in _COMPLETED_STATUSES:
        return True
    if item.get("completed") is True or item.get("isCompleted") is True:
        return True
    if _task_completed_at(item) is not None and status in ("", "completed"):
        return True
    return False


def consultar_estado_tarea_api(tarea: MoreAppTareaEnviada, max_pages: int = 8) -> Dict[str, Any]:
    """Busca la tarea en MoreApp y dice si el destinatario ya la terminó."""
    from .moreapp_api import MoreAppApiConfigError, MoreAppApiError, list_form_tasks

    result: Dict[str, Any] = {
        "found": False,
        "status": "",
        "completada": False,
        "error": "",
        "item": None,
    }
    if not (tarea.form_id or "").strip() or not (tarea.task_id or "").strip():
        result["error"] = "Esta tarea no tiene un ID de MoreApp para consultar."
        return result
    wanted = str(tarea.task_id).strip()
    page = 0
    try:
        while page < max_pages:
            raw = list_form_tasks(tarea.form_id, page=page)
            items = _items_tareas(raw)
            if not items:
                break
            for item in items:
                if _task_id_item(item) == wanted:
                    result["found"] = True
                    result["status"] = _task_status_item(item)
                    result["completada"] = _tarea_api_completada(item)
                    result["item"] = item
                    return result
            if len(items) < 20:
                break
            page += 1
    except (MoreAppApiConfigError, MoreAppApiError) as exc:
        result["error"] = str(exc)[:240]
    return result


def revisar_tarea_desde_api(tarea: MoreAppTareaEnviada) -> Dict[str, Any]:
    """Consulta MoreApp y, si está COMPLETED, marca la tarea local."""
    result = consultar_estado_tarea_api(tarea)
    MoreAppTareaEnviada.objects.filter(pk=tarea.pk).update(ultima_sync=timezone.now())
    if result.get("completada") and result.get("found"):
        completar_tarea(
            tarea,
            origen=MoreAppTareaEvento.ORIGEN_API,
            detalle={"task_id": tarea.task_id, "status": result.get("status") or ""},
            cuando=_task_completed_at(result.get("item") or {}),
        )
        tarea.refresh_from_db()
    return result


def sincronizar_tareas_desde_api(max_pages: int = 8) -> Dict[str, int]:
    from .moreapp_api import MoreAppApiConfigError, MoreAppApiError, list_form_tasks

    stats = {"revisadas": 0, "completadas": 0, "errores": 0}
    abiertas = MoreAppTareaEnviada.objects.filter(
        estado=MoreAppTareaEnviada.ESTADO_ASIGNADA
    ).exclude(task_id="")
    form_ids = list(abiertas.values_list("form_id", flat=True).distinct())
    por_task: Dict[str, List[MoreAppTareaEnviada]] = {}
    for tarea in abiertas:
        por_task.setdefault(tarea.task_id, []).append(tarea)
    for form_id in form_ids:
        page = 0
        vistos = set()
        while page < max_pages:
            try:
                raw = list_form_tasks(form_id, page=page)
            except (MoreAppApiConfigError, MoreAppApiError):
                stats["errores"] += 1
                break
            items = _items_tareas(raw)
            if not items:
                break
            for item in items:
                task_id = _task_id_item(item)
                if not task_id:
                    continue
                vistos.add(task_id)
                stats["revisadas"] += 1
                if not _tarea_api_completada(item):
                    continue
                for tarea in por_task.get(task_id, []):
                    if completar_tarea(
                        tarea,
                        origen=MoreAppTareaEvento.ORIGEN_API,
                        detalle={"task_id": task_id, "status": _task_status_item(item)},
                        cuando=_task_completed_at(item),
                    ):
                        stats["completadas"] += 1
            if len(items) < 20:
                break
            page += 1
        MoreAppTareaEnviada.objects.filter(
            form_id=form_id,
            estado=MoreAppTareaEnviada.ESTADO_ASIGNADA,
        ).update(ultima_sync=timezone.now())
    return stats


def marcar_alertas_leidas(user) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    ahora = timezone.now()
    filtro = Q(usuario=user)
    if getattr(user, "rol", None) in ("ADMIN", "ADMINISTRATIVO"):
        filtro = filtro | Q(broadcast=True)
    qs = MoreAppTareaAlerta.objects.filter(leida_en__isnull=True).filter(filtro)
    return qs.update(leida_en=ahora)


def conteos_alertas_tareas(user) -> Dict[str, int]:
    vacio = {
        "tareas_alertas": 0,
        "tareas_creacion": 0,
        "tareas_completado": 0,
    }
    if user is None or not getattr(user, "is_authenticated", False):
        return vacio
    qs = MoreAppTareaAlerta.objects.filter(leida_en__isnull=True)
    personal = qs.filter(usuario=user)
    rol = getattr(user, "rol", None)
    if rol in ("ADMIN", "ADMINISTRATIVO"):
        visible = qs.filter(Q(usuario=user) | Q(broadcast=True))
    else:
        visible = personal
    creacion = visible.filter(tipo=MoreAppTareaAlerta.TIPO_CREACION).values("tarea_id").distinct().count()
    completado = visible.filter(tipo=MoreAppTareaAlerta.TIPO_COMPLETADO).values("tarea_id").distinct().count()
    return {
        "tareas_alertas": creacion + completado,
        "tareas_creacion": creacion,
        "tareas_completado": completado,
    }


def kpis_tareas() -> Dict[str, Any]:
    ahora = timezone.now()
    hoy = timezone.localdate()
    d7 = ahora - timedelta(days=7)
    d30 = ahora - timedelta(days=30)
    qs = MoreAppTareaEnviada.objects.all()
    abiertas = qs.filter(estado=MoreAppTareaEnviada.ESTADO_ASIGNADA)
    completadas = qs.filter(estado=MoreAppTareaEnviada.ESTADO_COMPLETADA)
    duracion = completadas.filter(
        fecha_completado__isnull=False, fecha_creacion__gte=d30
    ).annotate(
        dur=ExpressionWrapper(
            F("fecha_completado") - F("fecha_creacion"),
            output_field=DurationField(),
        )
    ).aggregate(media=Avg("dur"))
    media = duracion.get("media")
    media_horas = None
    if media is not None:
        media_horas = round(media.total_seconds() / 3600.0, 1)
    por_formulario = list(
        qs.filter(fecha_creacion__gte=d30)
        .values("form_name")
        .annotate(c=Count("id"))
        .order_by("-c")[:8]
    )
    return {
        "hoy_creadas": qs.filter(fecha_creacion__date=hoy).count(),
        "hoy_completadas": completadas.filter(fecha_completado__date=hoy).count(),
        "d7_creadas": qs.filter(fecha_creacion__gte=d7).count(),
        "d7_completadas": completadas.filter(fecha_completado__gte=d7).count(),
        "d30_creadas": qs.filter(fecha_creacion__gte=d30).count(),
        "d30_completadas": completadas.filter(fecha_completado__gte=d30).count(),
        "abiertas": abiertas.count(),
        "errores": qs.filter(estado=MoreAppTareaEnviada.ESTADO_ERROR).count(),
        "vencidas": abiertas.filter(fecha_limite__lt=ahora).count(),
        "media_horas": media_horas,
        "por_formulario": por_formulario,
    }
