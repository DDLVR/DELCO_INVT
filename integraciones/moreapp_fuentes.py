"""Importación de filas para data sources MoreApp elegidas (no se copian todas)."""

from __future__ import annotations

import csv
import json
import unicodedata
from io import TextIOWrapper
from typing import Any, Dict, List, Tuple

from django.utils import timezone

from .models import MoreAppFuenteFila, MoreAppFuenteInterna

_MAX_FILAS = 8000


def fold_header(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    folded = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
    return "".join(ch for ch in folded if ch.isalnum())


def _cell_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _column_ids(columnas: Any) -> List[str]:
    ids: List[str] = []
    if not isinstance(columnas, list):
        return ids
    for item in columnas:
        if isinstance(item, dict):
            col_id = str(item.get("id") or item.get("key") or "").strip()
        else:
            col_id = str(item or "").strip()
        if col_id and col_id not in ids:
            ids.append(col_id)
    if "id" not in ids:
        ids.insert(0, "id")
    return ids


def _header_map(headers: List[str], columnas: Any) -> Dict[int, str]:
    aliases: Dict[str, str] = {}
    if isinstance(columnas, list):
        for item in columnas:
            if not isinstance(item, dict):
                continue
            col_id = str(item.get("id") or item.get("key") or "").strip()
            label = str(item.get("label") or item.get("name") or col_id).strip()
            if col_id:
                aliases[fold_header(col_id)] = col_id
            if label:
                aliases[fold_header(label)] = col_id or label
    mapping: Dict[int, str] = {}
    used = set()
    for idx, header in enumerate(headers):
        key = fold_header(header)
        col_id = aliases.get(key) or str(header or "").strip()
        if not col_id or col_id in used:
            continue
        mapping[idx] = col_id
        used.add(col_id)
    return mapping


def _rows_from_dicts(items: List[Any], columnas: Any) -> List[Dict[str, str]]:
    col_ids = _column_ids(columnas)
    aliases = {}
    if isinstance(columnas, list):
        for item in columnas:
            if not isinstance(item, dict):
                continue
            col_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
            if col_id:
                aliases[fold_header(col_id)] = col_id
            if label:
                aliases[fold_header(label)] = col_id or label
    rows: List[Dict[str, str]] = []
    for item in items[:_MAX_FILAS]:
        if not isinstance(item, dict):
            continue
        valores: Dict[str, str] = {}
        for key, value in item.items():
            col_id = aliases.get(fold_header(key)) or str(key)
            valores[col_id] = _cell_text(value)
        if not any(valores.values()):
            continue
        if "id" not in valores or not valores.get("id"):
            for col_id in col_ids:
                if valores.get(col_id):
                    valores["id"] = fold_header(valores[col_id]) or valores[col_id]
                    break
        rows.append(valores)
    return rows


def parse_json_bytes(raw: bytes, columnas: Any) -> List[Dict[str, str]]:
    payload = json.loads(raw.decode("utf-8-sig"))
    if isinstance(payload, dict):
        for key in ("data", "items", "elements", "content"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError("El JSON debe ser una lista de filas.")
    return _rows_from_dicts(payload, columnas)


def parse_csv_file(uploaded, columnas: Any) -> List[Dict[str, str]]:
    wrapper = TextIOWrapper(uploaded, encoding="utf-8-sig", newline="")
    try:
        reader = csv.reader(wrapper)
        headers = next(reader, [])
        mapping = _header_map([str(h or "") for h in headers], columnas)
        items: List[Dict[str, str]] = []
        for line in reader:
            if len(items) >= _MAX_FILAS:
                break
            valores: Dict[str, str] = {}
            for idx, col_id in mapping.items():
                if idx < len(line):
                    valores[col_id] = _cell_text(line[idx])
            if any(valores.values()):
                items.append(valores)
        return _rows_from_dicts(items, columnas)
    finally:
        try:
            wrapper.detach()
        except Exception:
            pass


def parse_excel_file(uploaded, columnas: Any) -> List[Dict[str, str]]:
    import openpyxl

    wb = openpyxl.load_workbook(uploaded, data_only=True, read_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            return []
        mapping = _header_map([_cell_text(h) for h in header_row], columnas)
        items: List[Dict[str, str]] = []
        for line in rows_iter:
            if len(items) >= _MAX_FILAS:
                break
            valores: Dict[str, str] = {}
            for idx, col_id in mapping.items():
                if idx < len(line):
                    valores[col_id] = _cell_text(line[idx])
            if any(valores.values()):
                items.append(valores)
        return _rows_from_dicts(items, columnas)
    finally:
        wb.close()


def parse_uploaded_fuente(uploaded, columnas: Any) -> List[Dict[str, str]]:
    name = (getattr(uploaded, "name", "") or "").lower()
    if name.endswith(".json"):
        return parse_json_bytes(uploaded.read(), columnas)
    if name.endswith(".csv"):
        return parse_csv_file(uploaded, columnas)
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return parse_excel_file(uploaded, columnas)
    raise ValueError("Usa un archivo Excel (.xlsx), CSV o JSON.")


def upsert_filas(
    fuente: MoreAppFuenteInterna,
    filas: List[Dict[str, str]],
    *,
    reemplazar: bool,
) -> Tuple[int, int]:
    if reemplazar:
        fuente.filas.all().delete()
    creadas = 0
    actualizadas = 0
    seen = set()
    for idx, valores in enumerate(filas, start=1):
        entry_id = str(valores.get("id") or "").strip() or ("fila-%s" % idx)
        if entry_id in seen:
            entry_id = "%s-%s" % (entry_id, idx)
        seen.add(entry_id)
        payload = dict(valores)
        payload["id"] = entry_id
        _, created = MoreAppFuenteFila.objects.update_or_create(
            fuente=fuente,
            entry_id=entry_id[:120],
            defaults={"valores": payload},
        )
        if created:
            creadas += 1
        else:
            actualizadas += 1
    fuente.fecha_importacion = timezone.now()
    fuente.save(update_fields=["fecha_importacion", "fecha_actualizacion"])
    return creadas, actualizadas
