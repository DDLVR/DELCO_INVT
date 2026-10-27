"""Formato completo de respuestas MoreApp: campos, grupos, fotos y búsquedas."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

from django.urls import NoReverseMatch, reverse

from .moreapp_tareas_pdf import _LABELS as _LABELS_PROCESADOS
from .moreapp_tareas_pdf import _SKIP_PROCESADOS

_SKIP_PROCESADOS_EXTRA = _SKIP_PROCESADOS | {
    "fotos_disponibles",
    "fotos_total",
    "fotos_locales",
}

_GRIDFS_PREFIX = "gridfs://registrationFiles/"
_SKIP_KEYS = {"id", "uid", "_id", "uniqueId", "fileId"}
_LOCATION_KEYS = {"lat", "lng", "latitude", "longitude", "coordinates", "formattedValue", "address"}
_FILE_HINTS = (
    "foto",
    "photo",
    "image",
    "imagen",
    "firma",
    "signature",
    "archivo",
    "file",
    "dibujo",
    "drawing",
    "panoram",
    "evidencia",
)


def _texto(value: Any) -> str:
    if value is None or value is False:
        return ""
    if isinstance(value, bool):
        return "Sí"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def etiqueta_campo(key: str, labels: Optional[Dict[str, str]] = None) -> str:
    nombre = str(key or "").strip()
    if not nombre:
        return "Campo"
    if labels and nombre in labels:
        return labels[nombre]
    if nombre in _LABELS_PROCESADOS:
        return _LABELS_PROCESADOS[nombre]
    texto = re.sub(r"([a-z])([A-Z])", r"\1 \2", nombre)
    texto = texto.replace("_", " ").replace("-", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:1].upper() + texto[1:] if texto else nombre


def _es_archivo(value: Any) -> bool:
    if isinstance(value, str) and value.startswith("gridfs://"):
        return True
    if not isinstance(value, dict):
        return False
    raw_id = str(value.get("id") or value.get("fileId") or value.get("uniqueId") or "")
    if raw_id.startswith("gridfs://"):
        return True
    return bool(
        value.get("contentType")
        or value.get("filename")
        or value.get("fileName")
        or value.get("url")
        or value.get("downloadUrl")
    )


def _file_id(value: Any) -> str:
    if isinstance(value, str) and value.startswith(_GRIDFS_PREFIX):
        return value[len(_GRIDFS_PREFIX) :].strip()
    if isinstance(value, str) and value.startswith("gridfs://"):
        return value.split("/")[-1].strip()
    if not isinstance(value, dict):
        return ""
    raw = str(value.get("id") or value.get("fileId") or value.get("uniqueId") or "")
    if raw.startswith(_GRIDFS_PREFIX):
        return raw[len(_GRIDFS_PREFIX) :].strip()
    if raw.startswith("gridfs://"):
        return raw.split("/")[-1].strip()
    if re.match(r"^[0-9a-fA-F-]{16,}$", raw):
        return raw
    return ""


def _archivo_url(file_id: str) -> str:
    if not file_id:
        return ""
    try:
        return reverse("moreapp_api_registro_archivo", args=[file_id])
    except NoReverseMatch:
        return ""


def _fila_archivo(value: Any, fotos_locales: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    file_id = _file_id(value)
    nombre = ""
    content_type = ""
    url = ""
    media_url = ""
    if isinstance(value, dict):
        nombre = str(value.get("filename") or value.get("fileName") or value.get("name") or "")
        content_type = str(value.get("contentType") or value.get("mimeType") or "")
        url = str(value.get("url") or value.get("downloadUrl") or value.get("href") or "")
    is_image = (not content_type) or content_type.startswith("image/") or bool(file_id)
    if fotos_locales and file_id:
        for foto in fotos_locales:
            if str(foto.get("gridfs_id") or "") == file_id or str(foto.get("gridfs_ref") or "").endswith(file_id):
                media_url = str(foto.get("media_url") or "")
                url = media_url or url or str(foto.get("url") or "")
                nombre = nombre or str(foto.get("nombre_archivo") or "")
                break
    href = media_url or url or _archivo_url(file_id)
    return {
        "id": file_id,
        "name": nombre or file_id,
        "content_type": content_type,
        "is_image": "1" if is_image else "",
        "url": href,
        "media_url": media_url,
    }


def _es_ubicacion(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    coords = value.get("coordinates") if isinstance(value.get("coordinates"), dict) else {}
    if value.get("lat") is not None or value.get("latitude") is not None:
        return True
    if coords.get("latitude") is not None or coords.get("lat") is not None:
        return True
    keys = set(value.keys())
    return bool(keys) and keys.issubset(_LOCATION_KEYS | {"location", "accuracy", "altitude"})


def _texto_ubicacion(value: Dict[str, Any]) -> str:
    coords = value.get("coordinates") if isinstance(value.get("coordinates"), dict) else {}
    lat = value.get("lat", value.get("latitude", coords.get("latitude", coords.get("lat"))))
    lng = value.get("lng", value.get("longitude", coords.get("longitude", coords.get("lng"))))
    formatted = _texto(value.get("formattedValue") or value.get("address"))
    loc = value.get("location") if isinstance(value.get("location"), dict) else {}
    if not formatted and loc:
        formatted = ", ".join(
            part
            for part in (
                _texto(loc.get("road")),
                _texto(loc.get("postcode")),
                _texto(loc.get("city")),
                _texto(loc.get("country")),
            )
            if part
        )
    if lat is not None and lng is not None:
        maps = "https://www.google.com/maps?q=%s,%s" % (lat, lng)
        extra = formatted or ("%s, %s" % (lat, lng))
        return extra + "\n" + maps
    return formatted


def _campo_base(key: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    return {
        "key": key,
        "label": etiqueta_campo(key, labels),
        "text": "",
        "files": [],
        "children": [],
        "rows": [],
        "wide": False,
    }


def _marcar_ancho(campo: Dict[str, Any]) -> Dict[str, Any]:
    if (
        campo.get("files")
        or campo.get("children")
        or campo.get("rows")
        or len(str(campo.get("text") or "")) > 80
        or "\n" in str(campo.get("text") or "")
    ):
        campo["wide"] = True
    return campo


def _valor_a_campo(
    key: str,
    value: Any,
    labels: Optional[Dict[str, str]] = None,
    fotos_locales: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    campo = _campo_base(key, labels)
    if value in (None, ""):
        return campo
    if isinstance(value, bool):
        campo["text"] = "Sí" if value else "No"
        return campo
    if _es_archivo(value):
        archivo = _fila_archivo(value, fotos_locales)
        if archivo.get("id") or archivo.get("url"):
            campo["files"] = [archivo]
        return _marcar_ancho(campo)
    if isinstance(value, list):
        files: List[Dict[str, str]] = []
        textos: List[str] = []
        filas: List[List[Dict[str, Any]]] = []
        for item in value:
            if _es_archivo(item) or (isinstance(item, str) and item.startswith("gridfs://")):
                archivo = _fila_archivo(item, fotos_locales)
                if archivo.get("id") or archivo.get("url"):
                    files.append(archivo)
            elif isinstance(item, dict):
                filas.append(_campos_desde_dict(item, labels, fotos_locales, incluir_vacios=False))
            elif item not in (None, ""):
                textos.append(_texto(item))
        campo["files"] = files
        campo["rows"] = [fila for fila in filas if fila]
        campo["text"] = ", ".join(part for part in textos if part)
        return _marcar_ancho(campo)
    if isinstance(value, dict):
        if _es_ubicacion(value):
            campo["text"] = _texto_ubicacion(value)
            return _marcar_ancho(campo)
        campo["children"] = _campos_desde_dict(value, labels, fotos_locales, incluir_vacios=False)
        if not campo["children"]:
            campo["text"] = _texto_resumen_dict(value)
        return _marcar_ancho(campo)
    campo["text"] = _texto(value)
    return _marcar_ancho(campo)


def _texto_resumen_dict(value: Dict[str, Any]) -> str:
    partes = []
    for key, val in value.items():
        if key in _SKIP_KEYS or val in (None, "") or isinstance(val, (dict, list)):
            continue
        partes.append("%s: %s" % (etiqueta_campo(key), _texto(val)))
        if len(partes) >= 4:
            break
    if partes:
        return " · ".join(partes)
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _campos_desde_dict(
    data: Dict[str, Any],
    labels: Optional[Dict[str, str]] = None,
    fotos_locales: Optional[List[Dict[str, Any]]] = None,
    *,
    incluir_vacios: bool = False,
    orden: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows: List[Dict[str, Any]] = []
    seen = set()
    claves = list(orden) if orden else []
    for key in data.keys():
        if key not in claves:
            claves.append(key)
    for key in claves:
        nombre = str(key or "").strip()
        if not nombre or nombre in seen:
            continue
        if nombre in _SKIP_KEYS:
            continue
        seen.add(nombre)
        if nombre not in data:
            if incluir_vacios:
                rows.append(_campo_base(nombre, labels))
            continue
        campo = _valor_a_campo(nombre, data.get(nombre), labels, fotos_locales)
        if not incluir_vacios and not (
            campo.get("text") or campo.get("files") or campo.get("children") or campo.get("rows")
        ):
            continue
        rows.append(campo)
    return rows


def respuestas_desde_data(
    data: Any,
    labels: Optional[Dict[str, str]] = None,
    fotos_locales: Optional[List[Dict[str, Any]]] = None,
    *,
    incluir_vacios: bool = False,
) -> List[Dict[str, Any]]:
    bloque = data if isinstance(data, dict) else {}
    orden = list(labels.keys()) if labels else None
    return _campos_desde_dict(
        bloque,
        labels,
        fotos_locales,
        incluir_vacios=incluir_vacios and bool(labels),
        orden=orden,
    )


def _fotos_locales_registro(registro) -> List[Dict[str, Any]]:
    procesados = registro.datos_procesados if isinstance(getattr(registro, "datos_procesados", None), dict) else {}
    fotos = procesados.get("fotos") if isinstance(procesados.get("fotos"), list) else []
    return [item for item in fotos if isinstance(item, dict)]


def respuestas_desde_registro(registro) -> List[Dict[str, Any]]:
    """Respuestas completas de un IntegracionMoreApp guardado."""
    if registro is None:
        return []
    procesados = registro.datos_procesados if isinstance(registro.datos_procesados, dict) else {}
    raw = registro.datos_recibidos if isinstance(registro.datos_recibidos, dict) else {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    fotos = _fotos_locales_registro(registro)
    campos = respuestas_desde_data(data, fotos_locales=fotos, incluir_vacios=False)
    vistos = {str(item.get("key") or "").lower() for item in campos}
    extra: List[Dict[str, Any]] = []
    for key, val in procesados.items():
        if key in _SKIP_PROCESADOS_EXTRA or isinstance(val, (dict, list)):
            continue
        texto = _texto(val)
        if not texto:
            continue
        etiqueta = etiqueta_campo(key)
        if key.lower() in vistos or etiqueta.lower() in vistos:
            continue
        extra.append(_marcar_ancho({"key": key, "label": etiqueta, "text": texto, "files": [], "children": [], "rows": [], "wide": False}))
        vistos.add(key.lower())
        vistos.add(etiqueta.lower())
    return extra + campos


def contar_archivos(campos: List[Dict[str, Any]]) -> int:
    total = 0
    for campo in campos or []:
        total += len(campo.get("files") or [])
        total += contar_archivos(campo.get("children") or [])
        for fila in campo.get("rows") or []:
            total += contar_archivos(fila)
    return total


def campo_tiene_valor(campo: Dict[str, Any]) -> bool:
    if campo.get("text") or campo.get("files"):
        return True
    for hijo in campo.get("children") or []:
        if campo_tiene_valor(hijo):
            return True
    for fila in campo.get("rows") or []:
        if any(campo_tiene_valor(item) for item in fila):
            return True
    return False
