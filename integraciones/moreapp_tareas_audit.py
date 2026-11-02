# coding: utf-8
"""Auditoría de una tarea MoreApp: un registro que se actualiza, no una fila por clic."""

from __future__ import annotations

from typing import Any, Dict, Optional

ENTITY_TAREA = "MoreAppTarea"


def snapshot_tarea(tarea) -> Dict[str, Any]:
    dest = tarea.destinatarios if isinstance(getattr(tarea, "destinatarios", None), list) else []
    grupos = tarea.grupos if isinstance(getattr(tarea, "grupos", None), list) else []
    return {
        "id": tarea.pk,
        "formulario": (tarea.form_name or tarea.form_id or "")[:255],
        "titulo": (tarea.titulo or "")[:200],
        "mensaje": (tarea.mensaje or "")[:500],
        "cuenta": (tarea.cuenta or "")[:80],
        "estado": tarea.estado or "",
        "error": (tarea.error or "")[:300],
        "destinatarios": dest[:20],
        "grupos": grupos[:20],
        "observaciones": (tarea.observaciones or "")[:500],
        "tipo_trabajo": tarea.tipo_trabajo or "",
        "task_id": (tarea.task_id or "")[:80],
    }


def registrar_auditoria_tarea(tarea, accion: str, actor_id: Optional[int] = None, extra: Optional[dict] = None) -> None:
    if tarea is None or not getattr(tarea, "pk", None):
        return
    from web.services.audit import upsert_activity_audit

    if actor_id is None:
        actor_id = getattr(tarea, "creado_por_id", None)
    upsert_activity_audit(
        actor_id=actor_id,
        entity=ENTITY_TAREA,
        entity_id=str(tarea.pk),
        accion=accion,
        snapshot=snapshot_tarea(tarea),
        extra=extra or {},
    )
