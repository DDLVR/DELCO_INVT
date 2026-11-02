"""PDF de un registro MoreApp, incluyendo el contenido de archivos de texto."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Callable, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

from django.utils.text import get_valid_filename

from .moreapp_respuestas import iter_archivos, sniff_archivo, texto_desde_bytes

FetchFile = Callable[[str], Optional[Dict[str, Any]]]


def _campos_texto(campos: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for campo in campos or []:
        label = str(campo.get("label") or campo.get("key") or "Campo")
        text = str(campo.get("text") or "").strip()
        if text:
            out.append((label, text[:800]))
        out.extend(_campos_texto(campo.get("children") or []))
        for fila in campo.get("rows") or []:
            out.extend(_campos_texto(fila))
    return out


def anexar_adjuntos_texto(story, campos: List[Dict[str, Any]], styles, fetch_file: Optional[FetchFile] = None) -> None:
    from reportlab.platypus import Paragraph, Preformatted, Spacer

    bloques: List[Tuple[str, str, str]] = []
    for label, archivo in iter_archivos(campos):
        kind = str(archivo.get("kind") or "")
        nombre = str(archivo.get("name") or archivo.get("id") or "archivo")
        if archivo.get("is_image"):
            bloques.append((label, nombre, ""))
            continue
        body = ""
        file_id = str(archivo.get("id") or "")
        if fetch_file and file_id and (kind in {"text", "file", ""} or archivo.get("is_text")):
            descargado = fetch_file(file_id)
            if descargado:
                raw = descargado.get("content") or b""
                sniffed, _ctype, sniffed_name = sniff_archivo(
                    raw,
                    descargado.get("filename") or nombre,
                    descargado.get("content_type") or "",
                )
                nombre = sniffed_name or nombre
                if sniffed == "text":
                    body = texto_desde_bytes(raw)
                    kind = "text"
        bloques.append((label, nombre, body))
    if not bloques:
        return
    story.append(Spacer(1, 12))
    story.append(Paragraph("Archivos adjuntos", styles["label"]))
    for label, nombre, body in bloques:
        story.append(Paragraph(xml_escape("%s — %s" % (label, nombre)), styles["body"]))
        if body:
            story.append(Preformatted(body[:6000], styles["mono"]))
        story.append(Spacer(1, 6))


def nombre_archivo_pdf_registro(form_name: str, submission_id: str) -> str:
    base = get_valid_filename((form_name or "registro").strip() or "registro")
    return "%s_%s.pdf" % (base[:40], (submission_id or "envio")[:12])


def generar_pdf_registro(
    *,
    form_name: str,
    registro: Dict[str, Any],
    campos: List[Dict[str, Any]],
    fetch_file: Optional[FetchFile] = None,
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return _pdf_minimo_registro(form_name, registro, campos, fetch_file)

    buffer = BytesIO()
    title_txt = form_name or "Registro MoreApp"
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title=title_txt,
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("RegPdfTitle", parent=base["Heading1"], fontSize=14, spaceAfter=8),
        "label": ParagraphStyle("RegPdfLabel", parent=base["Normal"], textColor=colors.HexColor("#64748b"), fontSize=8),
        "body": ParagraphStyle("RegPdfBody", parent=base["Normal"], fontSize=10, leading=13),
        "mono": ParagraphStyle(
            "RegPdfMono",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.5,
            leading=9.5,
            backColor=colors.HexColor("#f8fafc"),
        ),
    }
    story = [
        Paragraph(xml_escape(title_txt), styles["title"]),
        Paragraph("Informe del envío MoreApp", styles["body"]),
        Spacer(1, 8),
    ]
    meta = [
        ["Envío", str(registro.get("id") or "—")],
        ["Fecha", str(registro.get("created") or "—")],
        ["Técnico", str(registro.get("tecnico") or registro.get("user") or "—")],
        ["N° cliente", str(registro.get("cliente") or "—")],
        ["Estado", str(registro.get("status") or "—")],
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
    story.append(Paragraph("Respuestas", styles["label"]))
    filas = _campos_texto(campos)
    if not filas:
        story.append(Paragraph("Sin campos con valor.", styles["body"]))
    else:
        rows = [[item[0], item[1][:400]] for item in filas[:80]]
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
    anexar_adjuntos_texto(story, campos, styles, fetch_file)
    doc.build(story)
    return buffer.getvalue()


def _pdf_minimo_registro(
    form_name: str,
    registro: Dict[str, Any],
    campos: List[Dict[str, Any]],
    fetch_file: Optional[FetchFile] = None,
) -> bytes:
    lines = [
        form_name or "Registro MoreApp",
        "Envío %s" % (registro.get("id") or ""),
        "Fecha %s" % (registro.get("created") or ""),
        "Técnico %s" % (registro.get("tecnico") or ""),
    ]
    for label, text in _campos_texto(campos)[:30]:
        lines.append("%s: %s" % (label, text))
    if fetch_file:
        for label, archivo in iter_archivos(campos):
            file_id = str(archivo.get("id") or "")
            if not file_id:
                continue
            descargado = fetch_file(file_id)
            if not descargado:
                continue
            raw = descargado.get("content") or b""
            sniffed, _ctype, nombre = sniff_archivo(raw, descargado.get("filename") or "", descargado.get("content_type") or "")
            if sniffed != "text":
                continue
            lines.append("%s (%s): %s" % (label, nombre, texto_desde_bytes(raw)[:400]))
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
