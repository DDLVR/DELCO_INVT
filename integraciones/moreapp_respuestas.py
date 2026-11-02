"""Formato completo de respuestas MoreApp: campos, grupos, fotos y búsquedas."""

from __future__ import annotations

import json
import re
from os.path import splitext
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
    "csv",
    "txt",
)
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_TEXT_EXT = {".txt", ".csv", ".log", ".json", ".xml"}
_IMAGE_HINTS = (
    "foto",
    "photo",
    "image",
    "imagen",
    "firma",
    "signature",
    "dibujo",
    "drawing",
    "panoram",
    "caratula",
    "evidencia",
    "fachada",
)
_TEXT_HINTS = ("csv", "txt", "log", "formato")
_TEXT_PRINTABLE = set("\t\n\r") | set(chr(c) for c in range(32, 127))


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


def _archivo_url(file_id: str, download: bool = False) -> str:
    if not file_id:
        return ""
    try:
        href = reverse("moreapp_api_registro_archivo", args=[file_id])
    except NoReverseMatch:
        return ""
    if download:
        return href + ("&" if "?" in href else "?") + "download=1"
    return href


def _kind_archivo(nombre: str, content_type: str, field_key: str = "") -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    ext = splitext(nombre or "")[1].lower()
    key = (field_key or "").casefold()
    if ctype.startswith("image/") or ext in _IMAGE_EXT:
        return "image"
    if ctype == "application/pdf" or ext == ".pdf":
        return "pdf"
    if ctype.startswith("text/") or "csv" in ctype or "json" in ctype or "xml" in ctype or ext in _TEXT_EXT:
        return "text"
    if any(hint in key for hint in _TEXT_HINTS) and not any(hint in key for hint in _IMAGE_HINTS):
        return "text"
    if any(hint in key for hint in _IMAGE_HINTS):
        return "image"
    return "file"


def _parece_texto(sample: str) -> bool:
    if not sample or not sample.strip():
        return False
    ok = sum(1 for ch in sample if ch in _TEXT_PRINTABLE or ord(ch) >= 160)
    return (ok / float(len(sample))) >= 0.85


def sniff_archivo(content: bytes, filename: str = "", content_type: str = "", field_key: str = "") -> Tuple[str, str, str]:
    nombre = (filename or "").strip() or "archivo"
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype in ("application/octet-stream", "binary/octet-stream", "application/download"):
        ctype = ""
    kind = _kind_archivo(nombre, ctype, field_key)
    raw = content or b""
    head = raw[:16]
    if kind == "file" and raw:
        if head.startswith(b"\xff\xd8\xff"):
            kind, ctype = "image", "image/jpeg"
        elif head.startswith(b"\x89PNG"):
            kind, ctype = "image", "image/png"
        elif head.startswith(b"%PDF"):
            kind, ctype = "pdf", "application/pdf"
        else:
            decoded = ""
            for encoding in ("utf-8", "latin-1"):
                try:
                    decoded = raw[:4096].decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if _parece_texto(decoded):
                kind = "text"
                ext = splitext(nombre)[1].lower()
                if ext == ".csv" or ("," in decoded[:200] and "\n" in decoded[:400]):
                    ctype = "text/csv; charset=utf-8"
                else:
                    ctype = "text/plain; charset=utf-8"
    if kind == "image" and not str(ctype).startswith("image/"):
        ctype = "image/jpeg"
    elif kind == "pdf":
        ctype = "application/pdf"
    elif kind == "text" and not str(ctype).startswith("text/") and "csv" not in str(ctype):
        ctype = "text/plain; charset=utf-8"
    elif not ctype:
        ctype = "application/octet-stream"
    ext = splitext(nombre)[1].lower()
    if kind == "text" and not ext:
        nombre = nombre + (".csv" if "csv" in ctype else ".txt")
    elif kind == "pdf" and ext != ".pdf":
        nombre = nombre + ".pdf"
    return kind, ctype, nombre


def texto_desde_bytes(content: bytes, limit: int = 80000) -> str:
    raw = (content or b"")[:limit]
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _fila_archivo(
    value: Any,
    fotos_locales: Optional[List[Dict[str, Any]]] = None,
    field_key: str = "",
) -> Dict[str, str]:
    file_id = _file_id(value)
    nombre = ""
    content_type = ""
    url = ""
    media_url = ""
    if isinstance(value, dict):
        nombre = str(value.get("filename") or value.get("fileName") or value.get("name") or "")
        content_type = str(value.get("contentType") or value.get("mimeType") or "")
        url = str(value.get("url") or value.get("downloadUrl") or value.get("href") or "")
    if fotos_locales and file_id:
        for foto in fotos_locales:
            if str(foto.get("gridfs_id") or "") == file_id or str(foto.get("gridfs_ref") or "").endswith(file_id):
                media_url = str(foto.get("media_url") or "")
                url = media_url or url or str(foto.get("url") or "")
                nombre = nombre or str(foto.get("nombre_archivo") or "")
                break
    kind = _kind_archivo(nombre, content_type, field_key)
    href = media_url or url or _archivo_url(file_id)
    download_url = _archivo_url(file_id, download=True) if file_id else href
    return {
        "id": file_id,
        "name": nombre or file_id,
        "content_type": content_type,
        "kind": kind,
        "is_image": "1" if kind == "image" else "",
        "is_text": "1" if kind == "text" else "",
        "url": href,
        "download_url": download_url,
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
        archivo = _fila_archivo(value, fotos_locales, field_key=key)
        if archivo.get("id") or archivo.get("url"):
            campo["files"] = [archivo]
        return _marcar_ancho(campo)
    if isinstance(value, list):
        files: List[Dict[str, str]] = []
        textos: List[str] = []
        filas: List[List[Dict[str, Any]]] = []
        for item in value:
            if _es_archivo(item) or (isinstance(item, str) and item.startswith("gridfs://")):
                archivo = _fila_archivo(item, fotos_locales, field_key=key)
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


def iter_archivos(campos: List[Dict[str, Any]]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for campo in campos or []:
        label = str(campo.get("label") or campo.get("key") or "Archivo")
        for archivo in campo.get("files") or []:
            yield label, archivo
        yield from iter_archivos(campo.get("children") or [])
        for fila in campo.get("rows") or []:
            yield from iter_archivos(fila)


def contar_archivos(campos: List[Dict[str, Any]]) -> int:
    return sum(1 for _label, _archivo in iter_archivos(campos))


def contar_fotos(campos: List[Dict[str, Any]]) -> int:
    return sum(1 for _label, archivo in iter_archivos(campos) if archivo.get("is_image"))


def enriquecer_archivos(campos: List[Dict[str, Any]], fetch_file, max_files: int = 8) -> None:
    """Completa tipo/nombre/preview descargando adjuntos que no se reconocen como foto."""
    revisados = 0
    for _label, archivo in iter_archivos(campos):
        if revisados >= max_files:
            break
        if archivo.get("is_image"):
            continue
        file_id = str(archivo.get("id") or "")
        if not file_id:
            continue
        revisados += 1
        try:
            descargado = fetch_file(file_id)
        except Exception:
            descargado = None
        if not descargado:
            continue
        raw = descargado.get("content") or b""
        kind, ctype, nombre = sniff_archivo(
            raw,
            descargado.get("filename") or archivo.get("name") or file_id,
            descargado.get("content_type") or archivo.get("content_type") or "",
        )
        archivo["kind"] = kind
        archivo["content_type"] = ctype
        archivo["name"] = nombre
        archivo["is_image"] = "1" if kind == "image" else ""
        archivo["is_text"] = "1" if kind == "text" else ""
        if kind == "text":
            archivo["preview"] = texto_desde_bytes(raw)[:12000]


def archivos_no_imagen(campos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for label, archivo in iter_archivos(campos):
        if archivo.get("is_image"):
            continue
        fila = dict(archivo)
        fila["label"] = label
        out.append(fila)
    return out


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
