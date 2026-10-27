"""PDF y campos rellenados de una tarea MoreApp (solo lectura)."""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from django.utils.text import get_valid_filename

from .models import MoreAppTareaEnviada
from .moreapp_cuentas import etiquetas_destinatarios

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


def _informe_pdf_bytes(tarea: MoreAppTareaEnviada) -> Optional[Tuple[bytes, str]]:
    registro = getattr(tarea, "integracion", None)
    if registro is None:
        return None
    try:
        from ordenes_trabajo.models import InformeCliente
        from ordenes_trabajo.utils import _buscar_pdfs_en_carpeta
    except Exception:
        return None
    informe = (
        InformeCliente.objects.filter(registro_moreapp_id=registro.pk)
        .exclude(archivo="")
        .order_by("-id")
        .first()
    )
    if informe and informe.archivo:
        try:
            informe.archivo.open("rb")
            try:
                raw = informe.archivo.read()
            finally:
                informe.archivo.close()
            if raw:
                return raw, informe.nombre_archivo or os.path.basename(informe.archivo.name)
        except Exception:
            pass
    for path in _buscar_pdfs_en_carpeta(getattr(registro, "ruta_carpeta", "") or ""):
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            if raw:
                return raw, os.path.basename(path)
        except OSError:
            continue
    return None


def tarea_permite_pdf(tarea: MoreAppTareaEnviada) -> bool:
    return tarea.estado == MoreAppTareaEnviada.ESTADO_COMPLETADA


def nombre_archivo_pdf_tarea(tarea: MoreAppTareaEnviada) -> str:
    return get_valid_filename("tarea_moreapp_%s.pdf" % tarea.pk)


def pdf_bytes_tarea(tarea: MoreAppTareaEnviada) -> Tuple[bytes, str]:
    existente = _informe_pdf_bytes(tarea)
    if existente:
        return existente
    return generar_pdf_tarea(tarea), nombre_archivo_pdf_tarea(tarea)


def _fmt(dt) -> str:
    if not dt:
        return "—"
    try:
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "—"


def generar_pdf_tarea(tarea: MoreAppTareaEnviada) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return _pdf_minimo(tarea)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title="Tarea MoreApp #%s" % tarea.pk,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TareaPdfTitle", parent=styles["Heading1"], fontSize=14, spaceAfter=8)
    label = ParagraphStyle("TareaPdfLabel", parent=styles["Normal"], textColor=colors.HexColor("#64748b"), fontSize=8)
    body = ParagraphStyle("TareaPdfBody", parent=styles["Normal"], fontSize=10, leading=13)
    from xml.sax.saxutils import escape as xml_escape

    story = [
        Paragraph("Tarea MoreApp #%s" % tarea.pk, title),
        Paragraph(xml_escape(tarea.form_name or tarea.form_id or "Formulario"), body),
        Spacer(1, 8),
    ]
    meta = [
        ["Estado", tarea.get_estado_display()],
        ["Mensaje", tarea.mensaje or "—"],
        ["CUENTA", tarea.cuenta or "—"],
        ["Creada", _fmt(tarea.fecha_creacion)],
        ["Asignada", _fmt(tarea.fecha_asignacion)],
        ["Completada", _fmt(tarea.fecha_completado)],
        ["Destinatarios", ", ".join(getattr(tarea, "destinatarios_visibles", None) or etiquetas_destinatarios(tarea.destinatarios or [])) or "—"],
    ]
    table = Table(meta, colWidths=[4 * cm, 13 * cm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Contenido rellenado", label))
    campos = campos_rellenados_tarea(tarea)
    if not campos:
        story.append(Paragraph("Sin campos con valor.", body))
    else:
        rows = [[item["label"], item["text"][:400]] for item in campos[:40]]
        campos_table = Table(rows, colWidths=[5 * cm, 12 * cm])
        campos_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ]
            )
        )
        story.append(campos_table)
    doc.build(story)
    return buffer.getvalue()


def _pdf_minimo(tarea: MoreAppTareaEnviada) -> bytes:
    lines = [
        "Tarea MoreApp #%s" % tarea.pk,
        tarea.form_name or tarea.form_id or "",
        tarea.mensaje or "",
        "Estado: %s" % tarea.estado,
        "CUENTA: %s" % (tarea.cuenta or "—"),
    ]
    for item in campos_rellenados_tarea(tarea)[:20]:
        lines.append("%s: %s" % (item["label"], item["text"]))
    content = " | ".join(part for part in lines if part).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objects = [
        "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
    ]
    stream = "BT /F1 10 Tf 50 750 Td (%s) Tj ET" % content[:1800]
    objects.append(
        "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append("4 0 obj<< /Length {} >>stream\n{}\nendstream endobj\n".format(len(stream), stream))
    objects.append("5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj.encode("latin-1", errors="replace"))
    xref_pos = out.tell()
    out.write("xref\n0 {}\n".format(len(offsets)).encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write("{:010d} 00000 n \n".format(off).encode("ascii"))
    out.write(
        "trailer<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(len(offsets), xref_pos).encode("ascii")
    )
    return out.getvalue()
