"""ZIP de archivos TXT del formulario Lectura (solo registros efectivos)."""

from __future__ import annotations

from io import BytesIO
from os.path import splitext
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from unicodedata import combining, normalize
from zipfile import ZIP_DEFLATED, ZipFile

from django.utils.text import get_valid_filename

from .moreapp_fechas import iso_day_moreapp
from .moreapp_respuestas import iter_archivos, respuestas_desde_data, sniff_archivo

ESTADO_EFECTIVO = "EJECUTADO"
ZIP_PAGE_SIZE = 50
ZIP_MAX_PAGES = 20
ZIP_MAX_FILES = 400
ZIP_MAX_SELECTED = 80
FetchFile = Callable[[str], Optional[Dict[str, Any]]]


def _fold(value: Any) -> str:
    raw = normalize("NFKD", str(value or ""))
    return "".join(ch for ch in raw if not combining(ch)).casefold().strip()


def es_formulario_lectura(nombre: str) -> bool:
    blob = _fold(nombre)
    return blob == "lectura" or blob.startswith("lectura ")


def _texto_estado(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dict):
        for key in ("name", "label", "value", "text"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return str(value.get("id") or "").strip()
    return str(value).strip()


def estado_es_efectivo(item: Dict[str, Any]) -> bool:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    return _fold(_texto_estado(data.get("estado"))) == _fold(ESTADO_EFECTIVO)


def _cliente_item(item: Dict[str, Any]) -> str:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    for key in ("cliente", "numCliente", "numeroCliente", "num_cliente"):
        value = data.get(key)
        if value not in (None, ""):
            if isinstance(value, dict):
                value = value.get("CLIENTE") or value.get("cliente") or value.get("value") or ""
            text = str(value).strip()
            if text:
                return text
    nested = data.get("clienteParaMantenimiento")
    if isinstance(nested, dict):
        for key in ("CLIENTE", "cliente"):
            text = str(nested.get(key) or "").strip()
            if text:
                return text
    return "scliente"


def _fecha_item(item: Dict[str, Any]) -> str:
    info = item.get("info") if isinstance(item.get("info"), dict) else {}
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    return iso_day_moreapp(info.get("date") or info.get("created") or meta.get("created") or item.get("created")) or "sin-fecha"


def candidatos_txt(item: Dict[str, Any]) -> List[Dict[str, str]]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    out: List[Dict[str, str]] = []
    vistos = set()
    for label, archivo in iter_archivos(respuestas_desde_data(data, incluir_vacios=False)):
        if archivo.get("is_image"):
            continue
        file_id = str(archivo.get("id") or "").strip()
        if not file_id or file_id in vistos:
            continue
        vistos.add(file_id)
        out.append(
            {
                "id": file_id,
                "label": str(label or "archivo"),
                "name": str(archivo.get("name") or file_id),
                "kind": str(archivo.get("kind") or ""),
            }
        )
    return out


def _entrada_zip(fecha: str, cliente: str, label: str, filename: str, file_id: str) -> str:
    base = get_valid_filename(filename or file_id) or "archivo.txt"
    stem, ext = splitext(base)
    if not ext:
        ext = ".txt"
    pieza = get_valid_filename("%s_%s_%s" % (cliente or "scliente", label or "txt", stem))[:80]
    return "%s/%s%s" % (fecha or "sin-fecha", pieza or file_id[:12], ext)


def armar_zip_txt(
    items: Iterable[Dict[str, Any]],
    fetch_file: FetchFile,
    *,
    meta: Optional[Dict[str, Any]] = None,
    max_files: int = ZIP_MAX_FILES,
) -> Tuple[bytes, int, int, bool]:
    buffer = BytesIO()
    usados: Dict[str, int] = {}
    vistos_id = set()
    archivos = 0
    registros = 0
    truncado = False
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        for item in items:
            if not estado_es_efectivo(item):
                continue
            registros += 1
            fecha = _fecha_item(item)
            cliente = _cliente_item(item)
            for candidato in candidatos_txt(item):
                if archivos >= max_files:
                    truncado = True
                    break
                file_id = candidato["id"]
                if file_id in vistos_id:
                    continue
                descargado = fetch_file(file_id)
                if not descargado:
                    continue
                raw = descargado.get("content") or b""
                kind, _ctype, nombre = sniff_archivo(
                    raw,
                    descargado.get("filename") or candidato.get("name") or file_id,
                    descargado.get("content_type") or "",
                    candidato.get("label") or "",
                )
                if kind != "text":
                    continue
                vistos_id.add(file_id)
                entrada = _entrada_zip(fecha, cliente, candidato.get("label") or "", nombre, file_id)
                if entrada in usados:
                    usados[entrada] += 1
                    stem, ext = splitext(entrada)
                    entrada = "%s_%s%s" % (stem, usados[entrada], ext)
                else:
                    usados[entrada] = 1
                zf.writestr(entrada, raw)
                archivos += 1
            if truncado:
                break
        lineas = [
            "Formulario Lectura — TXT efectivos",
            "Filtro: estado = %s" % ESTADO_EFECTIVO,
        ]
        if meta:
            for key in ("desde", "hasta", "registros_api", "truncado_paginas"):
                if meta.get(key) not in (None, ""):
                    lineas.append("%s: %s" % (key, meta.get(key)))
        lineas.append("Registros efectivos con TXT: %s" % registros)
        lineas.append("Archivos incluidos: %s" % archivos)
        if truncado:
            lineas.append("AVISO: se alcanzó el máximo de archivos; acota el rango de fechas.")
        zf.writestr("README.txt", "\n".join(lineas) + "\n")
    return buffer.getvalue(), archivos, registros, truncado
