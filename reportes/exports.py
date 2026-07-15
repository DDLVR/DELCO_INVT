"""Generación de Excel y PDF para reportes del PDF punto 9."""

from __future__ import annotations

from io import BytesIO
from typing import Iterable, List, Optional, Sequence

import openpyxl
from django.http import HttpResponse
from django.utils import timezone


def _as_cell_text(value) -> str:
    if value is None:
        return ''
    return str(value)


def build_excel_response(filename: str, headers: Sequence[str], rows: Iterable[Sequence]) -> HttpResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Reporte'
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def build_pdf_response(
    filename: str,
    headers: Sequence[str],
    rows: Iterable[Sequence],
    title: Optional[str] = None,
) -> HttpResponse:
    """PDF tabular en landscape A4; celdas largas se truncan para legibilidad."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title or filename,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading2'],
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        'ReportMeta',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        textColor=colors.grey,
        spaceAfter=8,
    )
    cell_style = ParagraphStyle(
        'ReportCell',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
        alignment=TA_LEFT,
        wordWrap='CJK',
    )
    header_style = ParagraphStyle(
        'ReportHeader',
        parent=cell_style,
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
    )

    max_chars = 48 if len(headers) <= 8 else (36 if len(headers) <= 12 else 28)

    def _cell_paragraph(text: str, style) -> Paragraph:
        raw = _as_cell_text(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        if len(raw) > max_chars:
            raw = raw[: max_chars - 1] + '…'
        return Paragraph(raw or '—', style)

    header_row = [_cell_paragraph(h, header_style) for h in headers]
    data: List[List] = [header_row]
    row_list = list(rows)
    for row in row_list:
        cells = list(row) + [''] * max(0, len(headers) - len(row))
        data.append([
            _cell_paragraph(cells[i] if i < len(cells) else '', cell_style)
            for i in range(len(headers))
        ])

    usable_width = page_size[0] - doc.leftMargin - doc.rightMargin
    col_width = usable_width / max(len(headers), 1)
    table = Table(data, colWidths=[col_width] * len(headers), repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f6fa')]),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#c5d0de')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]
        )
    )

    generado = timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')
    story = [
        Paragraph(_as_cell_text(title or 'Reporte operativo'), title_style),
        Paragraph(f'DelcoChile · Generado {generado} · {len(row_list)} registro(s)', meta_style),
        Spacer(1, 4),
        table,
    ]
    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
