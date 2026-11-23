"""PDF y campos rellenados de una tarea MoreApp (solo lectura)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from django.utils.text import get_valid_filename

from .models import MoreAppTareaEnviada

_SKIP_PROCESADOS = {
    "resultado_operativo",
    "geo",
    "fotos",
    "location",
    "form_name",
    "formulario_canonico",
}

_LABELS = {
    "cliente_codigo": "N° cliente",
    "cliente_nombre": "Cliente",
    "cliente_direccion": "Dirección",
    "cliente_comuna": "Comuna",
    "actividad": "Actividad",
    "trabajo": "Trabajo",
    "estado": "Estado",
    "tecnico_responsable": "Técnico",
    "fecha_trabajo": "Fecha de trabajo",
    "fecha_registro": "Fecha de registro",
    "serial_number": "Serie medidor",
}


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


def _flatten(data: Any, prefix: str = "") -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(data, dict):
        cuenta = _texto(data.get("CUENTA") or data.get("cuenta") or data.get("cliente"))
        if cuenta and not prefix:
            out.append({"label": "CUENTA", "text": cuenta})
        for key, val in data.items():
            label = str(key or "").strip()
            if not label or label.startswith("_"):
                continue
            path = "%s · %s" % (prefix, label) if prefix else label
            text = _texto(val)
            if text:
                out.append({"label": path, "text": text})
            elif isinstance(val, dict):
                out.extend(_flatten(val, path))
            elif isinstance(val, list) and val and not isinstance(val[0], (dict, list)):
                joined = ", ".join(_texto(item) for item in val if _texto(item))
                if joined:
                    out.append({"label": path, "text": joined})
    return out


def campos_rellenados_tarea(tarea: MoreAppTareaEnviada) -> List[Dict[str, str]]:
    """Campos con valor del informe vinculado o, si no hay, de la precarga."""
    registro = getattr(tarea, "integracion", None)
    seen = set()
    out: List[Dict[str, str]] = []

    def _add(label: str, text: str) -> None:
        value = (text or "").strip()
        if not value:
            return
        key = (label.strip().lower(), value.lower())
        if key in seen:
            return
        seen.add(key)
        out.append({"label": label, "text": value[:500]})

    if registro is not None:
        procesados = registro.datos_procesados if isinstance(registro.datos_procesados, dict) else {}
        for key, val in procesados.items():
            if key in _SKIP_PROCESADOS or isinstance(val, (dict, list)):
                continue
            _add(_LABELS.get(key) or str(key).replace("_", " ").title(), _texto(val))
        data = registro.datos_recibidos if isinstance(registro.datos_recibidos, dict) else {}
        bloque = data.get("data") if isinstance(data.get("data"), dict) else {}
        for item in _flatten(bloque):
            _add(item["label"], item["text"])
        return out

    precarga = tarea.datos_precarga if isinstance(tarea.datos_precarga, dict) else {}
    for item in _flatten(precarga):
        _add(item["label"], item["text"])
    return out


def tarea_permite_pdf(tarea: MoreAppTareaEnviada) -> bool:
    return tarea.estado == MoreAppTareaEnviada.ESTADO_COMPLETADA


def nombre_archivo_pdf_tarea(tarea: MoreAppTareaEnviada) -> str:
    return get_valid_filename("tarea_moreapp_%s.pdf" % tarea.pk)


class InformeMoreAppNoDisponible(Exception):
    """La tarea no tiene todavía el PDF que genera MoreApp al completar el formulario."""


def _file_id_informe(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    mails = item.get("mailStatuses")
    if not isinstance(mails, list):
        return ""
    for mail in mails:
        if not isinstance(mail, dict):
            continue
        file_id = str(mail.get("pdfFileId") or "").strip()
        if file_id:
            return file_id
    return ""


def _envio_guardado(tarea: MoreAppTareaEnviada) -> Optional[Dict[str, Any]]:
    registro = getattr(tarea, "integracion", None)
    if registro is None:
        return None
    data = getattr(registro, "datos_recibidos", None)
    return data if isinstance(data, dict) else None


def _submission_id(tarea: MoreAppTareaEnviada) -> str:
    registro = getattr(tarea, "integracion", None)
    if registro is None:
        return ""
    return str(getattr(registro, "moreapp_submission_id", "") or "").strip()


def _envio_moreapp(tarea: MoreAppTareaEnviada) -> Optional[Dict[str, Any]]:
    """Envío de MoreApp: el guardado, el id del informe, o el que corresponde a la tarea."""
    from .moreapp_api import (
        MoreAppApiConfigError,
        MoreAppApiError,
        assert_safe_id,
        get_submission,
        list_submissions,
    )

    guardado = _envio_guardado(tarea)
    if _file_id_informe(guardado):
        return guardado
    sid = _submission_id(tarea)
    if sid:
        try:
            return get_submission(assert_safe_id(sid, "submissionId"))
        except (MoreAppApiConfigError, MoreAppApiError, ValueError):
            return guardado
    form_id = str(tarea.form_id or "").strip()
    task_id = str(tarea.task_id or "").strip()
    if not form_id or not task_id:
        return guardado
    try:
        raw = list_submissions(
            assert_safe_id(form_id, "formId"),
            0,
            {
                "pageSize": 5,
                "query": [{"path": "meta.taskId", "type": "string", "value": task_id}],
            },
        )
    except (MoreAppApiConfigError, MoreAppApiError, ValueError):
        return guardado
    elements = raw.get("elements") if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    for item in elements or []:
        if not isinstance(item, dict):
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        if str(meta.get("taskId") or "").strip() == task_id:
            return item
    return guardado


def _nombre_informe(filename: str, tarea: MoreAppTareaEnviada) -> str:
    from urllib.parse import unquote

    nombre = unquote(str(filename or "")).replace('"', "").replace("\\", "/").split("/")[-1].strip()
    if not nombre.lower().endswith(".pdf"):
        return nombre_archivo_pdf_tarea(tarea)
    try:
        nombre.encode("latin-1")
    except UnicodeEncodeError:
        return nombre_archivo_pdf_tarea(tarea)
    return nombre


def pdf_bytes_tarea(tarea: MoreAppTareaEnviada) -> Tuple[bytes, str]:
    """PDF que MoreApp genera al completar el formulario."""
    from .moreapp_api import (
        MoreAppApiConfigError,
        MoreAppApiError,
        assert_safe_id,
        download_registration_file,
    )

    file_id = _file_id_informe(_envio_moreapp(tarea))
    if file_id:
        try:
            archivo = download_registration_file(assert_safe_id(file_id, "fileId"))
        except (MoreAppApiConfigError, MoreAppApiError, ValueError):
            archivo = None
        raw = (archivo or {}).get("content") or b""
        if raw.startswith(b"%PDF"):
            return raw, _nombre_informe((archivo or {}).get("filename") or "", tarea)
    raise InformeMoreAppNoDisponible(
        "MoreApp todavía no entrega el informe de este formulario."
    )

