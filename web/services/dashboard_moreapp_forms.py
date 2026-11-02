# coding: utf-8
"""Gráficas del dashboard a partir de registros MoreApp (formularios asignados)."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Tuple
from unicodedata import combining, normalize

from django.conf import settings

_ESTADO_KEYS = ("estado", "Estado", "resultado", "Resultado", "efectividad")
_DIAG_KEYS = (
    "diagnostico",
    "Diagnostico",
    "Diagnostico_Mantenimiento",
    "diagnosticoMantenimiento",
)
_SAMPLE_PAGES = 1
_PAGE_SIZE = 50
_TOP_DIAG = 8
_ESTADOS_EFECTIVIDAD = ("EJECUTADO", "INCIDENCIA")
_DIAG_PATHS = ("diagnostico", "tipoDeIncidencia")
# Valores reales del formulario (conteo exacto por filtro MoreApp).
_DIAG_SEMILLA = (
    ("diagnostico", "MODEM - DESPROGRAMADO"),
    ("diagnostico", "MODEM - OBSOLETO/FALLA SIN REPUESTO"),
    ("diagnostico", "MODEM - NO CUENTA CON MODEM EN TERRENO"),
    ("diagnostico", "MODEM - FALLA FRANCA"),
    ("diagnostico", "MEDIDOR - NO COMPATIBLE CON TELEMEDIDA"),
    ("diagnostico", "MEDIDOR - NO COMUNICA/SI REGISTRA"),
    ("diagnostico", "MEDIDOR - SIN MEDIDOR"),
    ("diagnostico", "MEDIDOR - MEDIDOR EN TERRENO DISTINTO A SIST."),
    ("diagnostico", "SIMCARD - SIN COBERTURA"),
    ("diagnostico", "SIMCARD - SIN PLAN DE DATOS"),
    ("diagnostico", "SIMCARD - SUCIA"),
    ("diagnostico", "SIM no tiene Datos"),
    ("diagnostico", "No tiene telemetria"),
    ("diagnostico", "Peaje"),
    ("tipoDeIncidencia", "ESTADO VISITA - CERRADO"),
    ("tipoDeIncidencia", "ESTADO VISITA - DESHABITADO"),
    ("tipoDeIncidencia", "ESTADO VISITA - NO PERMITE"),
    ("tipoDeIncidencia", "ESTADO CLIENTES - CLIENTE DIRECTO"),
    ("tipoDeIncidencia", "ESTADO CLIENTES - SIN SUMNISTRO"),
    ("tipoDeIncidencia", "ESTADO CLIENTES - RETIRADO"),
    ("tipoDeIncidencia", "MEDIDOR - SIN MEDIDOR"),
    ("tipoDeIncidencia", "STOPWORK"),
    ("tipoDeIncidencia", "No permite"),
    ("tipoDeIncidencia", "Cerrado habitado"),
    ("tipoDeIncidencia", "Cerrado deshabitado"),
    ("tipoDeIncidencia", "Sin medidor"),
)


def _fold(text: Any) -> str:
    raw = normalize("NFKD", str(text or ""))
    return "".join(ch for ch in raw if not combining(ch)).casefold()


def _es_telemetria(nombre: str) -> bool:
    blob = _fold(nombre)
    return "telemetr" in blob or "efectividad" in blob


def _lookup_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dict):
        for key in ("name", "label", "value", "text"):
            text = str(value.get(key) or "").strip()
            if text:
                return text[:120]
        return str(value.get("id") or "").strip()[:120]
    if isinstance(value, list):
        parts = [_lookup_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    return str(value).strip()[:120]


def _campo(data: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    for key in keys:
        if key in data:
            text = _lookup_text(data.get(key))
            if text:
                return text
    return ""


def _items(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("elements", "content", "items", "submissions"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        data = raw.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _total_size(raw: Any) -> int:
    if isinstance(raw, dict):
        try:
            return int(raw.get("totalSize") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _vacio() -> Dict[str, Any]:
    return {
        "por_formulario": [],
        "telemetria_estado": [],
        "telemetria_diagnostico": [],
        "telemetria_muestra": 0,
        "telemetria_total": 0,
        "efectividad_pct": None,
        "telemetria_conteo_completo": False,
        "telemetria_diag_completo": False,
        "error": "",
    }


def _contar_campo(form_id: str, path: str, valor: str, list_submissions) -> int:
    """totalSize filtrado por un campo data.* (conteo real en MoreApp)."""
    raw = list_submissions(
        form_id,
        0,
        {
            "pageSize": 1,
            "query": [{"path": "data.%s" % path, "type": "string", "value": valor}],
        },
    )
    return _total_size(raw)


def _contar_estado(form_id: str, valor: str, list_submissions) -> int:
    return _contar_campo(form_id, "estado", valor, list_submissions)


def _etiquetas_desde_items(items: Iterable[Dict[str, Any]]) -> List[Tuple[str, str]]:
    vistos = set()
    pares: List[Tuple[str, str]] = []
    for item in items:
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        for path in _DIAG_PATHS:
            valor = _lookup_text(data.get(path))
            if not valor:
                continue
            clave = (path, valor)
            if clave in vistos:
                continue
            vistos.add(clave)
            pares.append(clave)
    return pares


def _contar_diagnosticos(form_id: str, extra: Iterable[Tuple[str, str]], list_submissions) -> Counter:
    pares = list(_DIAG_SEMILLA)
    vistos = set(pares)
    for par in extra:
        if par not in vistos:
            vistos.add(par)
            pares.append(par)
    conteo: Counter = Counter()
    if not pares:
        return conteo

    def _uno(path_valor):
        path, valor = path_valor
        return valor, _contar_campo(form_id, path, valor, list_submissions)

    workers = 8 if len(pares) > 8 else max(1, len(pares))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = [pool.submit(_uno, par) for par in pares]
        for futuro in as_completed(futuros):
            valor, cantidad = futuro.result()
            if cantidad:
                conteo[valor] = max(conteo.get(valor, 0), int(cantidad))
    return conteo


def build_dashboard_formularios_moreapp() -> Dict[str, Any]:
    if not bool(getattr(settings, "MOREAPP_API_ENABLED", False)):
        return _vacio()

    from integraciones.models import MoreAppFormularioAsignado
    from integraciones.moreapp_api import MoreAppApiConfigError, MoreAppApiError, list_submissions

    asignados = list(
        MoreAppFormularioAsignado.objects.values("form_id", "form_name").distinct()
    )
    if not asignados:
        return _vacio()

    por_formulario: List[Dict[str, Any]] = []
    estado_counter: Counter = Counter()
    estado_real: Counter = Counter()
    diag_counter: Counter = Counter()
    diag_real: Counter = Counter()
    muestra = 0
    total_tele = 0
    error = ""
    conteo_completo = False
    diag_completo = False

    for row in asignados:
        form_id = str(row.get("form_id") or "").strip()
        nombre = str(row.get("form_name") or form_id).strip() or form_id
        if not form_id:
            continue
        try:
            raw = list_submissions(
                form_id,
                0,
                {"pageSize": _PAGE_SIZE, "sort": [{"key": "info.date", "direction": -1}]},
            )
        except (MoreAppApiConfigError, MoreAppApiError) as exc:
            error = str(exc)
            continue
        total = _total_size(raw)
        por_formulario.append({"nombre": nombre, "form_id": form_id, "total": total, "c": total})
        try:
            from integraciones.moreapp_api_ingest import ingest_submission_items

            ingest_submission_items(_items(raw), form_name=nombre, aplicar_operativo=False)
        except Exception:
            pass
        if not _es_telemetria(nombre):
            continue
        total_tele += total
        try:
            for valor in _ESTADOS_EFECTIVIDAD:
                estado_real[valor] += _contar_estado(form_id, valor, list_submissions)
            conteo_completo = True
        except (MoreAppApiConfigError, MoreAppApiError) as exc:
            error = str(exc)
            conteo_completo = False
        pages = [raw]
        for page in range(1, _SAMPLE_PAGES):
            try:
                pages.append(
                    list_submissions(
                        form_id,
                        page,
                        {"pageSize": _PAGE_SIZE, "sort": [{"key": "info.date", "direction": -1}]},
                    )
                )
            except (MoreAppApiConfigError, MoreAppApiError):
                break
        for page_raw in pages:
            for item in _items(page_raw):
                data = item.get("data") if isinstance(item.get("data"), dict) else {}
                if not data:
                    continue
                muestra += 1
                estado = _campo(data, _ESTADO_KEYS) or "(sin estado)"
                estado_counter[estado] += 1
                diag = _campo(data, _DIAG_KEYS) or _lookup_text(data.get("tipoDeIncidencia"))
                if diag:
                    diag_counter[diag] += 1
        try:
            extra = _etiquetas_desde_items(_items(raw))
            parcial = _contar_diagnosticos(form_id, extra, list_submissions)
            if sum(parcial.values()) > 0:
                diag_real.update(parcial)
                diag_completo = True
        except (MoreAppApiConfigError, MoreAppApiError) as exc:
            error = str(exc)
            diag_completo = False

    por_formulario.sort(key=lambda item: int(item.get("total") or 0), reverse=True)
    if conteo_completo and sum(estado_real.values()) > 0:
        estado_chart = Counter({k: v for k, v in estado_real.items() if v})
        resto = total_tele - sum(estado_chart.values())
        if resto > 0:
            estado_chart["(sin estado)"] += resto
    else:
        estado_chart = estado_counter
        conteo_completo = False
    ejecutado = sum(n for label, n in estado_chart.items() if "ejecut" in _fold(label))
    incidencia = sum(n for label, n in estado_chart.items() if "inciden" in _fold(label))
    base = ejecutado + incidencia
    efectividad_pct = round((ejecutado * 100.0) / base, 1) if base else None

    diag_chart = diag_real if diag_completo and sum(diag_real.values()) > 0 else diag_counter
    if diag_chart is diag_counter:
        diag_completo = False
    top = diag_chart.most_common(_TOP_DIAG)
    usados = set(name for name, _n in top)
    resto = sum(n for name, n in diag_chart.items() if name not in usados)
    diagnosticos = [{"categoria": name, "count": n} for name, n in top]
    if resto:
        diagnosticos.append({"categoria": "Otros", "count": resto})

    return {
        "por_formulario": por_formulario,
        "telemetria_estado": [{"categoria": k, "count": v} for k, v in estado_chart.most_common()],
        "telemetria_diagnostico": diagnosticos,
        "telemetria_muestra": muestra,
        "telemetria_total": total_tele,
        "efectividad_pct": efectividad_pct,
        "telemetria_conteo_completo": conteo_completo,
        "telemetria_diag_completo": diag_completo,
        "error": error,
    }
