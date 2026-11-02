"""Asignación de formularios MoreApp a usuarios internos."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import MoreAppFormularioAsignado

Usuario = get_user_model()


_ROLES_ASIGNABLES = ("ADMIN", "ADMINISTRATIVO")


def usuarios_asignables():
    return (
        Usuario.objects.filter(is_active=True, rol__in=_ROLES_ASIGNABLES)
        .order_by("nombre", "apellido", "nombre_interno")
    )


def asignaciones_por_form() -> Dict[str, List[MoreAppFormularioAsignado]]:
    grouped: Dict[str, List[MoreAppFormularioAsignado]] = defaultdict(list)
    qs = MoreAppFormularioAsignado.objects.select_related("usuario").order_by(
        "usuario__nombre", "usuario__apellido"
    )
    for item in qs:
        grouped[item.form_id].append(item)
    return grouped


def enriquecer_fila(row: Dict[str, Any], asignados: List[MoreAppFormularioAsignado]) -> Dict[str, Any]:
    row["asignados_count"] = len(asignados)
    row["asignados"] = [
        item.usuario.nombre_interno or ("%s %s" % (item.usuario.nombre, item.usuario.apellido)).strip()
        for item in asignados
    ]
    row["asignados_ids"] = [item.usuario_id for item in asignados]
    return row


def fila_asignada(form_id: str, nombre: str, asignados: List[MoreAppFormularioAsignado]) -> Dict[str, Any]:
    return enriquecer_fila(
        {
            "id": form_id,
            "name": nombre or form_id,
            "status": "",
            "status_badge": "secondary",
            "description": "",
            "published_version": "",
            "latest_status": "",
            "latest_updated": "",
            "icon": "clipboard",
        },
        asignados,
    )


def ids_formularios_en_registros(usuario=None, todos: bool = False):
    qs = MoreAppFormularioAsignado.objects.all()
    if usuario is not None and not todos:
        qs = qs.filter(usuario=usuario)
    return set(qs.values_list("form_id", flat=True))


def formulario_esta_en_registros(form_id: str) -> bool:
    if not form_id:
        return False
    return MoreAppFormularioAsignado.objects.filter(form_id=form_id).exists()


def volver_listado_name(user, origen: str = "") -> str:
    if origen == "reportes":
        return "reportes_moreapp_list"
    if getattr(user, "rol", "") == "ADMIN":
        return "moreapp_api_catalogo"
    return "moreapp_formularios_list"


def volver_listado_url(user) -> str:
    return reverse(volver_listado_name(user))
