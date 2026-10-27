"""Cruce manual entre correos MoreApp y técnicos de la data source Técnicos."""

from __future__ import annotations

import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.db import transaction

from .models import MoreAppCuentaTecnico


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower().strip()


def _es_fuente_tecnicos(item: Dict[str, Any]) -> bool:
    name = _fold(item.get("name"))
    return "tecnic" in name and "certelec" not in name


def _nombre_fila_tecnico(row: Dict[str, Any]) -> str:
    preferred: List[str] = []
    other: List[str] = []
    for key, value in row.items():
        folded = _fold(key)
        if not folded or folded == "id":
            continue
        text = str(value or "").strip()
        if not text:
            continue
        if "nombre" in folded or folded in ("name", "tecnico"):
            preferred.append(text)
        else:
            other.append(text)
    if preferred:
        return preferred[0]
    if other:
        return other[0]
    return ""


def listar_tecnicos_moreapp() -> List[Dict[str, str]]:
    from .moreapp_api import (
        MoreAppApiConfigError,
        MoreAppApiError,
        list_datasource_entry_rows,
        list_datasources,
    )

    try:
        datasource = None
        raw = list_datasources()
        items = raw if isinstance(raw, list) else []
        for item in items:
            if isinstance(item, dict) and _es_fuente_tecnicos(item):
                datasource = item
                break
        if datasource is None:
            return []
        packed = list_datasource_entry_rows(str(datasource.get("id") or ""))
    except (MoreAppApiConfigError, MoreAppApiError):
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for row in packed.get("rows") or []:
        if not isinstance(row, dict):
            continue
        nombre = _nombre_fila_tecnico(row)
        entry_id = str(row.get("id") or "").strip() or nombre
        if not nombre or entry_id in seen:
            continue
        seen.add(entry_id)
        out.append({"id": entry_id, "nombre": nombre})
    out.sort(key=lambda item: _fold(item.get("nombre")))
    return out


def vinculos_por_email(emails: Optional[Iterable[str]] = None) -> Dict[str, MoreAppCuentaTecnico]:
    qs = MoreAppCuentaTecnico.objects.all()
    if emails is not None:
        wanted = [str(item or "").strip().lower() for item in emails if str(item or "").strip()]
        if not wanted:
            return {}
        qs = qs.filter(email__in=wanted)
    return {item.email.lower(): item for item in qs}


def aplicar_vinculos_a_usuarios(
    rows: List[Dict[str, Any]],
    tecnicos: Optional[Iterable[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    vinculos = vinculos_por_email(str(item.get("email") or "") for item in rows)
    nombres_vivos = {
        str(item.get("id") or ""): str(item.get("nombre") or "").strip()
        for item in (tecnicos or [])
        if str(item.get("id") or "").strip()
    }
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        email = str(item.get("email") or "").strip().lower()
        item["nombre_moreapp"] = str(item.get("nombre") or "")
        vinculo = vinculos.get(email)
        if vinculo is not None and vinculo.tecnico_entry_id:
            nombre = nombres_vivos.get(vinculo.tecnico_entry_id) or vinculo.tecnico_nombre
            item["tecnico_id"] = vinculo.tecnico_entry_id
            item["tecnico_nombre"] = nombre
            item["enlazado"] = True
            item["nombre"] = nombre
        else:
            item["tecnico_id"] = ""
            item["tecnico_nombre"] = ""
            item["enlazado"] = False
        out.append(item)
    out.sort(
        key=lambda item: (
            0 if item.get("enlazado") else 1,
            (item.get("nombre") or "").lower(),
            (item.get("email") or "").lower(),
        )
    )
    return out


def etiquetas_destinatarios(emails: Iterable[str]) -> List[str]:
    items = [str(item or "").strip() for item in emails or [] if str(item or "").strip()]
    if not items:
        return []
    vinculos = vinculos_por_email(items)
    out: List[str] = []
    for email in items:
        vinculo = vinculos.get(email.lower())
        if vinculo is not None and vinculo.tecnico_nombre:
            out.append(vinculo.tecnico_nombre)
        else:
            out.append(email)
    return out


def anotar_destinatarios_visibles(tareas: Iterable[Any]) -> None:
    filas = list(tareas or [])
    correos: List[str] = []
    for tarea in filas:
        correos.extend(str(item or "").strip() for item in (getattr(tarea, "destinatarios", None) or []))
    vinculos = vinculos_por_email(correos)
    for tarea in filas:
        visibles: List[str] = []
        for email in getattr(tarea, "destinatarios", None) or []:
            texto = str(email or "").strip()
            if not texto:
                continue
            vinculo = vinculos.get(texto.lower())
            if vinculo is not None and vinculo.tecnico_nombre:
                visibles.append(vinculo.tecnico_nombre)
            else:
                visibles.append(texto)
        tarea.destinatarios_visibles = visibles


def emails_que_coinciden_tecnico(texto: str) -> List[str]:
    needle = (texto or "").strip()
    if not needle:
        return []
    return list(
        MoreAppCuentaTecnico.objects.filter(tecnico_nombre__icontains=needle).values_list("email", flat=True)
    )


def email_por_nombre_tecnico(nombre: str) -> str:
    raw = (nombre or "").strip()
    if not raw or "@" in raw:
        return ""
    needle = _fold(raw)
    matches: List[str] = []
    seen = set()
    for vinculo in MoreAppCuentaTecnico.objects.all():
        if _fold(vinculo.tecnico_nombre) == needle:
            email = (vinculo.email or "").strip().lower()
            if email and email not in seen:
                seen.add(email)
                matches.append(email)
    if len(matches) == 1:
        return matches[0]
    return ""


def guardar_vinculo(
    *,
    email: str,
    tecnico_entry_id: str = "",
    tecnico_nombre: str = "",
    moreapp_user_id: str = "",
    moreapp_nombre: str = "",
    actualizado_por=None,
    tecnicos: Optional[Iterable[Dict[str, str]]] = None,
) -> Tuple[Optional[MoreAppCuentaTecnico], str]:
    correo = (email or "").strip().lower()
    if not correo or "@" not in correo:
        return None, "El correo MoreApp no es válido."
    entry_id = str(tecnico_entry_id or "").strip()
    with transaction.atomic():
        if not entry_id:
            MoreAppCuentaTecnico.objects.filter(email=correo).delete()
            return None, ""
        catalogo = list(tecnicos) if tecnicos is not None else listar_tecnicos_moreapp()
        found = next((item for item in catalogo if str(item.get("id") or "") == entry_id), None)
        nombre = str((found or {}).get("nombre") or tecnico_nombre or "").strip()
        if found is None and not nombre:
            return None, "Ese técnico no está en la data source Técnicos de MoreApp."
        if not nombre:
            nombre = entry_id
        MoreAppCuentaTecnico.objects.filter(tecnico_entry_id=entry_id).exclude(email=correo).delete()
        obj, _created = MoreAppCuentaTecnico.objects.update_or_create(
            email=correo,
            defaults={
                "tecnico_entry_id": entry_id[:80],
                "tecnico_nombre": nombre[:255],
                "moreapp_user_id": (moreapp_user_id or "")[:80],
                "moreapp_nombre": (moreapp_nombre or "")[:255],
                "actualizado_por": actualizado_por,
            },
        )
        return obj, ""
