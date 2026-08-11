"""PDF de resumen de orden de trabajo completada (solo lectura; no altera datos)."""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from django.utils.text import get_valid_filename

from ordenes_trabajo.observaciones_html import observaciones_a_reportlab
from ordenes_trabajo.utils import ESTADOS_TERMINADOS

logger = logging.getLogger(__name__)

ESTADOS_PDF_COMPLETADO = ESTADOS_TERMINADOS


def orden_permite_pdf_completado(orden) -> bool:
    return getattr(orden, 'estado', None) in ESTADOS_PDF_COMPLETADO


def _fmt_fecha(dt) -> str:
    if not dt:
        return '—'
    try:
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return '—'


def _leer_bytes_archivo(field_file) -> Optional[bytes]:
    if not field_file:
        return None
    try:
        field_file.open('rb')
        try:
            return field_file.read()
        finally:
            field_file.close()
    except Exception as exc:
        logger.warning('No se pudo leer archivo para PDF OT: %s', exc)
        return None


def generar_pdf_trabajo_completado(orden) -> bytes:
    """
    Genera un PDF con la información relevante de la OT.
    Usa solo datos existentes; no modifica la orden ni archivos originales.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return _pdf_minimo(orden)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title='OT #{} — trabajo completado'.format(orden.id),
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'OtPdfTitle',
        parent=styles['Heading1'],
        fontSize=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a3a5c'),
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        'OtPdfSub',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#666666'),
        spaceAfter=12,
    )
    label_style = ParagraphStyle(
        'OtPdfLabel',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#555555'),
        fontName='Helvetica-Bold',
    )
    value_style = ParagraphStyle(
        'OtPdfValue',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_LEFT,
        leading=12,
    )
    section_style = ParagraphStyle(
        'OtPdfSection',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#1a3a5c'),
        spaceBefore=10,
        spaceAfter=6,
    )

    story = []
    story.append(Paragraph('DELCO — Orden de trabajo completada', title_style))
    story.append(Paragraph(
        'OT #{} · {} · {}'.format(
            orden.id,
            orden.get_estado_display(),
            orden.get_tipo_trabajo_display(),
        ),
        sub_style,
    ))

    cliente = orden.cliente
    tecnico = orden.tecnico_responsable
    proyecto = (orden.proyecto_carga_administrativa or '').strip() or '—'
    if proyecto == '—' and cliente and getattr(cliente, 'proyecto', None):
        # Solo como referencia visual si el campo OT está vacío (no escribe en BD)
        proyecto = '{} (cliente)'.format(cliente.proyecto)

    filas = [
        [Paragraph('Identificación', label_style), Paragraph('OT #{}'.format(orden.id), value_style)],
        [Paragraph('Título', label_style), Paragraph(_esc(orden.titulo), value_style)],
        [Paragraph('Estado', label_style), Paragraph(_esc(orden.get_estado_display()), value_style)],
        [Paragraph('Tipo', label_style), Paragraph(_esc(orden.get_tipo_trabajo_display()), value_style)],
        [Paragraph('Proyecto / Carga administrativa', label_style), Paragraph(_esc(proyecto), value_style)],
        [
            Paragraph('Técnico responsable', label_style),
            Paragraph(_esc(tecnico.nombre_interno if tecnico else '—'), value_style),
        ],
        [Paragraph('Fecha creación', label_style), Paragraph(_fmt_fecha(orden.fecha_creacion), value_style)],
        [Paragraph('Fecha asignación', label_style), Paragraph(_fmt_fecha(orden.fecha_asignacion), value_style)],
        [Paragraph('Inicio ejecución', label_style), Paragraph(_fmt_fecha(orden.fecha_inicio_ejecucion), value_style)],
        [Paragraph('Fin ejecución', label_style), Paragraph(_fmt_fecha(orden.fecha_fin_ejecucion), value_style)],
        [Paragraph('Validación', label_style), Paragraph(_fmt_fecha(orden.fecha_validacion), value_style)],
    ]

    if cliente:
        filas.extend([
            [Paragraph('Cliente Nº', label_style), Paragraph(_esc(cliente.numero_cliente), value_style)],
            [
                Paragraph('Nombre cliente', label_style),
                Paragraph(_esc(getattr(cliente, 'customer_name', None) or '—'), value_style),
            ],
            [
                Paragraph('Dirección', label_style),
                Paragraph(_esc(getattr(cliente, 'installation_address', None) or getattr(cliente, 'direccion', None) or '—'), value_style),
            ],
            [Paragraph('Comuna', label_style), Paragraph(_esc(getattr(cliente, 'comuna', None) or '—'), value_style)],
        ])
    else:
        filas.append([Paragraph('Cliente', label_style), Paragraph('—', value_style)])

    # Equipos
    medidor = orden.medidor
    sim = orden.simcard
    modem = orden.modem
    filas.extend([
        [
            Paragraph('Medidor', label_style),
            Paragraph(_esc(medidor.serie if medidor else '—'), value_style),
        ],
        [
            Paragraph('SIM', label_style),
            Paragraph(_esc(getattr(sim, 'imei', None) or getattr(sim, 'iccid', None) or ('—' if not sim else str(sim))), value_style),
        ],
        [
            Paragraph('Módem', label_style),
            Paragraph(_esc(modem.serie if modem else '—'), value_style),
        ],
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

    # Observaciones (con formato)
    story.append(Paragraph('Observaciones técnicas', section_style))
    obs_markup = observaciones_a_reportlab(orden.observaciones_tecnicas or '')
    if obs_markup:
        story.append(Paragraph(obs_markup, value_style))
    else:
        story.append(Paragraph('<i>Sin observaciones</i>', value_style))

    if orden.observacion_validacion:
        story.append(Paragraph('Observación de validación', section_style))
        story.append(Paragraph(_esc(orden.observacion_validacion), value_style))

    # Fotografías / adjuntos imagen (máx. 6 para no inflar el PDF)
    adjuntos = list(orden.adjuntos.all().order_by('-fecha_hora')[:12])
    imagenes = []
    docs = []
    for adj in adjuntos:
        if getattr(adj, 'es_imagen', False) and adj.archivo:
            raw = _leer_bytes_archivo(adj.archivo)
            if raw:
                imagenes.append((adj, raw))
        else:
            docs.append(adj)

    if imagenes:
        story.append(Paragraph('Fotografías / evidencias', section_style))
        for adj, raw in imagenes[:6]:
            try:
                img_buf = BytesIO(raw)
                img = Image(img_buf, width=7.5 * cm, height=5.5 * cm)
                caption = Paragraph(
                    _esc('{} · {}'.format(adj.nombre_archivo, _fmt_fecha(adj.fecha_hora))),
                    ParagraphStyle('cap', parent=value_style, fontSize=7, textColor=colors.grey),
                )
                story.append(KeepTogether([img, caption, Spacer(1, 6)]))
            except Exception as exc:
                logger.warning('No se pudo incrustar imagen en PDF OT #%s: %s', orden.id, exc)
                story.append(Paragraph(_esc('(Imagen no disponible: {})'.format(adj.nombre_archivo)), value_style))

    if docs:
        story.append(Paragraph('Documentos asociados', section_style))
        for adj in docs:
            story.append(Paragraph(
                '• {} ({}){}'.format(
                    _esc(adj.nombre_archivo),
                    _esc(adj.get_tipo_display()),
                    ' — URL externa' if adj.url_externa and not adj.archivo else '',
                ),
                value_style,
            ))

    # Informes PDF vinculados (referencia, sin embeber PDF dentro de PDF)
    informes = list(orden.informes.all().order_by('-fecha_subida')[:10]) if hasattr(orden, 'informes') else []
    if informes:
        story.append(Paragraph('Informes PDF vinculados', section_style))
        for inf in informes:
            story.append(Paragraph(
                '• {} ({})'.format(
                    _esc(inf.nombre_archivo),
                    _esc(getattr(inf, 'get_origen_display', lambda: inf.origen)()),
                ),
                value_style,
            ))

    # Firmas de comprobante de cambio (si existen)
    comprobantes = []
    if hasattr(orden, 'comprobantes_cambio_medidor'):
        comprobantes = list(orden.comprobantes_cambio_medidor.all()[:3])
    for comp in comprobantes:
        story.append(Paragraph('Comprobante de cambio de medidor', section_style))
        firmas = []
        for campo, etiqueta in (('firma_cliente', 'Firma cliente'), ('firma_tecnico', 'Firma técnico')):
            f = getattr(comp, campo, None)
            raw = _leer_bytes_archivo(f) if f else None
            if raw:
                try:
                    img = Image(BytesIO(raw), width=5 * cm, height=2.2 * cm)
                    firmas.append([Paragraph(etiqueta, label_style), img])
                except Exception:
                    firmas.append([Paragraph(etiqueta, label_style), Paragraph('(no disponible)', value_style)])
        if firmas:
            t_firmas = Table(firmas, colWidths=[4 * cm, 8 * cm])
            t_firmas.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_firmas)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        '<font size="7" color="#888888">Documento generado automáticamente desde DELCO. '
        'No modifica los datos ni archivos originales de la orden.</font>',
        value_style,
    ))

    doc.build(story)
    return buffer.getvalue()


def _esc(valor) -> str:
    from xml.sax.saxutils import escape
    if valor is None:
        return '—'
    text = str(valor).strip()
    if not text:
        return '—'
    return escape(text)


def _pdf_minimo(orden) -> bytes:
    """PDF mínimo sin reportlab (texto plano embebido)."""
    lines = [
        'DELCO - Orden de trabajo completada',
        'OT #{}'.format(orden.id),
        'Titulo: {}'.format(orden.titulo or ''),
        'Estado: {}'.format(orden.get_estado_display()),
        'Proyecto/Carga: {}'.format(orden.proyecto_carga_administrativa or ''),
        'Tecnico: {}'.format(
            orden.tecnico_responsable.nombre_interno if orden.tecnico_responsable else ''
        ),
        'Observaciones: {}'.format(orden.observaciones_tecnicas or ''),
    ]
    content = '\n'.join(lines)
    # PDF mínimo válido
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


def nombre_archivo_pdf_ot(orden) -> str:
    return get_valid_filename('OT_{}_completada.pdf'.format(orden.id))
