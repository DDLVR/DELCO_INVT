"""Permisos de formularios MoreApp (quién puede llenar cada uno)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_TIPOS_FORM = {"form", "forms", "formulario", "registrationform"}
_TIPOS_OTROS = {"datasource", "folder", "group", "customer", "user", "role"}


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _es_tipo_formulario(valor: Any) -> bool:
    text = _texto(valor).lower()
    if not text:
        return True
    if text in _TIPOS_OTROS:
        return False
    return text in _TIPOS_FORM or text.endswith("form")


def _ids_desde_grant(grant: Any) -> List[str]:
    if isinstance(grant, str):
        value = grant.strip()
        return [value] if value else []
    if not isinstance(grant, dict):
        return []
    tipo = grant.get("resourceType") or grant.get("type") or grant.get("resource") or grant.get("kind") or ""
    if not _es_tipo_formulario(tipo):
        return []
    for key in ("resourceId", "formId", "form_id"):
        value = _texto(grant.get(key))
        if value:
            return [value]
    nested = grant.get("form")
    if isinstance(nested, dict):
        value = _texto(nested.get("id") or nested.get("formId"))
        if value:
            return [value]
    if isinstance(nested, str) and nested.strip():
        return [nested.strip()]
    if _es_tipo_formulario(tipo):
        value = _texto(grant.get("id"))
        if value:
            return [value]
    return []


def _ids_desde_forms(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            fid = _texto(item.get("id") or item.get("formId") or item.get("form_id"))
            if fid:
                out.append(fid)
    return out


def ids_formulario_de_usuario(item: Dict[str, Any]) -> Tuple[List[str], bool]:
    """IDs de formulario que el usuario MoreApp puede llenar. El bool indica si la API trajo grants/forms."""
    if not isinstance(item, dict):
        return [], False
    seen = False
    ids: List[str] = []
    found = set()

    def add(values: Iterable[str]) -> None:
        for value in values:
            if value and value not in found:
                found.add(value)
                ids.append(value)

    if "grants" in item:
        seen = True
        grants = item.get("grants")
        if isinstance(grants, list):
            for grant in grants:
                add(_ids_desde_grant(grant))
    if "forms" in item:
        seen = True
        add(_ids_desde_forms(item.get("forms")))
    groups = item.get("groups") if isinstance(item.get("groups"), list) else []
    for group in groups:
        if not isinstance(group, dict):
            continue
        if "grants" in group:
            seen = True
            grants = group.get("grants")
            if isinstance(grants, list):
                for grant in grants:
                    add(_ids_desde_grant(grant))
        if "forms" in group:
            seen = True
            add(_ids_desde_forms(group.get("forms")))
    return ids, seen


def anotar_permisos_usuarios(rows: List[Dict[str, Any]], raw_users: Sequence[Any]) -> bool:
    """Copia form_ids a cada fila de usuario. Devuelve True si MoreApp envió permisos."""
    by_email: Dict[str, Tuple[List[str], bool]] = {}
    by_id: Dict[str, Tuple[List[str], bool]] = {}
    alguno = False
    for item in raw_users or []:
        if not isinstance(item, dict):
            continue
        ids, seen = ids_formulario_de_usuario(item)
        if seen:
            alguno = True
        email = _texto(item.get("emailAddress") or item.get("email")).lower()
        uid = _texto(item.get("id"))
        payload = (ids, seen)
        if email:
            by_email[email] = payload
        if uid:
            by_id[uid] = payload
    for row in rows:
        email = _texto(row.get("email")).lower()
        uid = _texto(row.get("id"))
        ids, seen = by_email.get(email) or by_id.get(uid) or ([], False)
        row["form_ids"] = list(ids)
        row["conoce_permisos"] = bool(seen)
    return alguno


def anotar_permisos_grupos(grupos: List[Dict[str, Any]], usuarios: Sequence[Dict[str, Any]]) -> None:
    por_grupo: Dict[str, set] = defaultdict(set)
    for user in usuarios:
        form_ids = user.get("form_ids") or []
        for gid in user.get("group_ids") or []:
            key = _texto(gid)
            if not key:
                continue
            por_grupo[key].update(form_ids)
    for group in grupos:
        gid = _texto(group.get("id"))
        group["form_ids"] = sorted(por_grupo.get(gid, set()))


def cargar_usuarios_moreapp_con_permisos() -> Tuple[List[Dict[str, Any]], bool]:
    """Usuarios MoreApp activos con form_ids. Si la API falla, lista vacía y False."""
    from .moreapp_api import MoreAppApiConfigError, MoreAppApiError, list_users
    from .moreapp_catalogo_views import _user_row
    from .moreapp_cuentas import aplicar_vinculos_a_usuarios

    try:
        raw = list_users()
    except (MoreAppApiConfigError, MoreAppApiError):
        return [], False
    items: List[Any] = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for key in ("elements", "content", "items", "users"):
            value = raw.get(key)
            if isinstance(value, list):
                items = value
                break
        if not items and raw.get("id"):
            items = [raw]
    rows: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = _user_row(item)
        if row.get("disabled") or not row.get("email"):
            continue
        rows.append(row)
    linked = aplicar_vinculos_a_usuarios(rows)
    return linked, anotar_permisos_usuarios(linked, items)


def accesos_de_formulario(form_id: str, usuarios: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    wanted = _texto(form_id)
    if not wanted:
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for user in usuarios:
        if wanted not in (user.get("form_ids") or []):
            continue
        email = _texto(user.get("email"))
        key = email.lower()
        if not email or key in seen:
            continue
        seen.add(key)
        nombre = _texto(user.get("tecnico_nombre") or user.get("nombre") or email)
        out.append({"email": email, "nombre": nombre})
    out.sort(key=lambda item: (item["nombre"] or item["email"]).lower())
    return out


def anotar_accesos_en_formularios(
    formularios: List[Dict[str, Any]],
    usuarios: Sequence[Dict[str, Any]],
    *,
    conoce_permisos: bool,
) -> None:
    cache: Dict[str, List[Dict[str, str]]] = {}
    for row in formularios:
        form_id = _texto(row.get("id"))
        if form_id not in cache:
            cache[form_id] = accesos_de_formulario(form_id, usuarios)
        accesos = cache[form_id]
        row["moreapp_accesos"] = accesos
        row["moreapp_accesos_count"] = len(accesos)
        row["moreapp_permisos_conocidos"] = bool(conoce_permisos)


def usuario_tiene_formulario(user: Dict[str, Any], form_id: str) -> bool:
    wanted = _texto(form_id)
    if not wanted:
        return False
    return wanted in (user.get("form_ids") or [])


def filtrar_usuarios_de_formulario(
    usuarios: Sequence[Dict[str, Any]],
    form_id: str,
    *,
    conoce_permisos: bool,
) -> List[Dict[str, Any]]:
    if not form_id or not conoce_permisos:
        return list(usuarios)
    return [user for user in usuarios if usuario_tiene_formulario(user, form_id)]


def filtrar_grupos_de_formulario(
    grupos: Sequence[Dict[str, Any]],
    form_id: str,
    *,
    conoce_permisos: bool,
) -> List[Dict[str, Any]]:
    if not form_id or not conoce_permisos:
        return list(grupos)
    wanted = _texto(form_id)
    return [group for group in grupos if wanted in (group.get("form_ids") or [])]


def filtrar_destinatarios_por_formulario(
    emails: Sequence[str],
    usuarios: Sequence[Dict[str, Any]],
    form_id: str,
) -> Tuple[List[str], str]:
    """Si MoreApp envió grants, deja solo correos con ese formulario."""
    wanted = _texto(form_id)
    if not wanted:
        return [item for item in emails if _texto(item)], ""
    if not any(user.get("conoce_permisos") for user in usuarios):
        return [item for item in emails if _texto(item)], ""
    permitidos = {
        _texto(user.get("email")).lower()
        for user in usuarios
        if usuario_tiene_formulario(user, wanted) and _texto(user.get("email"))
    }
    ok: List[str] = []
    rechazados: List[str] = []
    seen = set()
    for raw in emails:
        email = _texto(raw)
        key = email.lower()
        if not email or key in seen:
            continue
        seen.add(key)
        if key in permitidos:
            ok.append(email)
        else:
            rechazados.append(email)
    if ok:
        return ok, ""
    if rechazados:
        muestra = ", ".join(rechazados[:4])
        extra = "…" if len(rechazados) > 4 else ""
        return [], (
            "Ningún destinatario tiene este formulario asignado en MoreApp "
            "(%s%s). Asígnaselo primero en MoreApp y vuelve a enviar."
            % (muestra, extra)
        )
    return [], "Ningún destinatario tiene este formulario asignado en MoreApp."
