"""PDF de resumen de carga administrativa (solo lectura; no altera datos)."""
from __future__ import annotations

from io import BytesIO

from django.utils.text import get_valid_filename

from ordenes_trabajo.observaciones_html import observaciones_a_flowables


def _fmt_fecha(dt) -> str:
    if not dt:
        return '—'
    try:
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return '—'


def _esc(valor) -> str:
    from xml.sax.saxutils import escape
    if valor is None:
        return '—'
    text = str(valor).strip()
    if not text:
        return '—'
    return escape(text)


def generar_pdf_carga_administrativa(carga) -> bytes:
    """
    Genera un PDF con los datos de la carga y observaciones formateadas
    (incluyendo tablas con cuadrícula).
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return _pdf_minimo(carga)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title='ID {} — {}'.format(carga.id, (carga.titulo or '')[:60]),
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CargaPdfTitle',
        parent=styles['Heading1'],
        fontSize=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a3a5c'),
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        'CargaPdfSub',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#666666'),
        spaceAfter=12,
    )
    label_style = ParagraphStyle(
        'CargaPdfLabel',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#555555'),
        fontName='Helvetica-Bold',
    )
    value_style = ParagraphStyle(
        'CargaPdfValue',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_LEFT,
        leading=12,
    )
    section_style = ParagraphStyle(
        'CargaPdfSection',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#1a3a5c'),
        spaceBefore=10,
        spaceAfter=6,
    )

    story = []
    story.append(Paragraph('DELCO — Carga administrativa', title_style))
    story.append(Paragraph(
        'ID {} · {} · {}'.format(
            carga.id,
            carga.get_estado_display(),
            carga.get_tipo_display(),
        ),
        sub_style,
    ))

    cliente = getattr(carga, 'cliente', None)
    asignado = (getattr(carga, 'asignado_display', None) or '').strip() or '—'
    creado = carga.creado_por.nombre_interno if carga.creado_por_id else '—'

    filas = [
        [Paragraph('Identificación', label_style), Paragraph('ID {}'.format(carga.id), value_style)],
        [Paragraph('Título (Nº cliente)', label_style), Paragraph(_esc(carga.titulo), value_style)],
        [Paragraph('Estado', label_style), Paragraph(_esc(carga.get_estado_display()), value_style)],
        [Paragraph('Tipo', label_style), Paragraph(_esc(carga.get_tipo_display()), value_style)],
        [Paragraph('Prioridad', label_style), Paragraph(_esc(carga.get_prioridad_display()), value_style)],
        [Paragraph('Asignada a', label_style), Paragraph(_esc(asignado), value_style)],
        [Paragraph('Creada por', label_style), Paragraph(_esc(creado), value_style)],
        [Paragraph('Fecha creación', label_style), Paragraph(_fmt_fecha(carga.fecha_creacion), value_style)],
        [Paragraph('Fecha asignación', label_style), Paragraph(_fmt_fecha(carga.fecha_asignacion), value_style)],
        [Paragraph('Fecha completada', label_style), Paragraph(_fmt_fecha(carga.fecha_completada), value_style)],
        [Paragraph('Proyecto', label_style), Paragraph(_esc(carga.proyecto or '—'), value_style)],
    ]

    if cliente:
        filas.extend([
            [Paragraph('Cliente Nº', label_style), Paragraph(_esc(cliente.numero_cliente), value_style)],
            [
                Paragraph('Nombre cliente', label_style),
                Paragraph(_esc(getattr(cliente, 'customer_name', None) or '—'), value_style),
            ],
        ])
    else:
        filas.append([Paragraph('Cliente', label_style), Paragraph('—', value_style)])

    if carga.orden_id:
        filas.append([
            Paragraph('Orden de trabajo', label_style),
            Paragraph(
                _esc('OT #{} — {}'.format(carga.orden_id, getattr(carga.orden, 'titulo', '') or '')),
                value_style,
            ),
        ])

    if carga.descripcion:
        filas.append([
            Paragraph('Descripción', label_style),
            Paragraph(_esc(carga.descripcion).replace('\n', '<br/>'), value_style),
        ])

    tabla = Table(filas, colWidths=[5.2 * cm, 12.2 * cm])
    tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f1f8')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#2c5282')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#c5d4e3')),
    ]))
    story.append(tabla)

    story.append(Paragraph('Observaciones / resultado', section_style))
    obs_flow = observaciones_a_flowables(carga.observaciones or '', styles)
    if obs_flow:
        story.extend(obs_flow)
    else:
        story.append(Paragraph('<i>Sin observaciones</i>', value_style))

    adjuntos = []
    if hasattr(carga, 'adjuntos'):
        try:
            adjuntos = list(carga.adjuntos.filter(eliminado=False).order_by('-fecha_hora')[:20])
        except Exception:
            adjuntos = []

    if adjuntos:
        story.append(Paragraph('Evidencias / adjuntos', section_style))
        for adj in adjuntos:
            story.append(Paragraph(
                '• {} ({}){}'.format(
                    _esc(adj.nombre_archivo),
                    _esc(adj.get_tipo_display()),
                    ' · {}'.format(_fmt_fecha(adj.fecha_hora)) if adj.fecha_hora else '',
                ),
                value_style,
            ))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        '<font size="7" color="#888888">Documento generado automáticamente desde DELCO. '
        'No modifica los datos ni archivos originales de la carga.</font>',
        value_style,
    ))

    doc.build(story)
    return buffer.getvalue()


def _pdf_minimo(carga) -> bytes:
    lines = [
        'DELCO - Carga administrativa',
        'ID {}'.format(carga.id),
        'Titulo (N cliente): {}'.format(carga.titulo or ''),
        'Estado: {}'.format(carga.get_estado_display()),
        'Tipo: {}'.format(carga.get_tipo_display()),
        'Asignado: {}'.format(getattr(carga, 'asignado_display', None) or ''),
        'Observaciones: {}'.format(carga.observaciones or ''),
    ]
    content = '\n'.join(lines)
    objects = []
    objects.append('1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n')
    objects.append('2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n')
    stream = 'BT /F1 10 Tf 50 750 Td ({}) Tj ET'.format(
        content.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')[:1800]
    )
    objects.append(
        '3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        '/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n'
    )
    objects.append(
        '4 0 obj<< /Length {} >>stream\n{}\nendstream endobj\n'.format(len(stream), stream)
    )
    objects.append('5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n')

    out = BytesIO()
    out.write(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj.encode('latin-1', errors='replace'))
    xref_pos = out.tell()
    out.write('xref\n0 {}\n'.format(len(offsets)).encode('ascii'))
    out.write(b'0000000000 65535 f \n')
    for off in offsets[1:]:
        out.write('{:010d} 00000 n \n'.format(off).encode('ascii'))
    out.write(
        'trailer<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n'.format(
            len(offsets), xref_pos
        ).encode('ascii')
    )
    return out.getvalue()


def nombre_archivo_pdf_carga(carga) -> str:
    return get_valid_filename('Carga_{}_administrativa.pdf'.format(carga.id))
