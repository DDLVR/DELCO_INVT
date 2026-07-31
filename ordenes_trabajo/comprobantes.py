"""Generación y armado de comprobantes digitales de cambio de medidor."""
from __future__ import annotations

import base64
import re
from datetime import datetime
from io import BytesIO
from typing import Optional

from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import get_valid_filename

from web.services.audit import AuditEvent, register_audit_event


def _png_sobre_fondo_blanco(raw: bytes) -> bytes:
    """Convierte PNG (con transparencia) a RGB sobre blanco para que reportlab no pinte negro."""
    try:
        from PIL import Image as PILImage
    except ImportError:
        return raw
    try:
        with PILImage.open(BytesIO(raw)) as im:
            if im.mode in ('RGBA', 'LA'):
                fondo = PILImage.new('RGB', im.size, (255, 255, 255))
                alpha = im.split()[-1]
                rgba = im.convert('RGBA')
                fondo.paste(rgba, mask=alpha)
                out = BytesIO()
                fondo.save(out, format='PNG')
                return out.getvalue()
            if im.mode == 'P':
                im = im.convert('RGBA')
                fondo = PILImage.new('RGB', im.size, (255, 255, 255))
                fondo.paste(im, mask=im.split()[-1])
                out = BytesIO()
                fondo.save(out, format='PNG')
                return out.getvalue()
            rgb = im.convert('RGB')
            out = BytesIO()
            rgb.save(out, format='PNG')
            return out.getvalue()
    except Exception:
        return raw


def _decode_data_url(data_url: str) -> Optional[bytes]:
    """Convierte data:image/png;base64,... a bytes."""
    if not data_url:
        return None
    text = data_url.strip()
    match = re.match(r'^data:image/(?:png|jpeg|jpg);base64,(.+)$', text, re.I | re.S)
    if not match:
        return None
    try:
        raw = base64.b64decode(match.group(1))
    except Exception:
        return None
    return _png_sobre_fondo_blanco(raw)


def _guardar_firma(comprobante, field_name: str, data_url: str, prefijo: str) -> bool:
    raw = _decode_data_url(data_url)
    if not raw:
        return False
    nombre = get_valid_filename(
        f'{prefijo}_ot{comprobante.orden_id}_{timezone.now():%Y%m%d%H%M%S}.png'
    )
    getattr(comprobante, field_name).save(nombre, ContentFile(raw), save=False)
    return True


def generar_pdf_comprobante(comprobante) -> bytes:
    """Genera el PDF del comprobante (reportlab si está; si no, PDF mínimo)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return _generar_pdf_minimo(comprobante)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f'Comprobante cambio medidor OT #{comprobante.orden_id}',
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TituloComp',
        parent=styles['Heading1'],
        fontSize=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1F4E79'),
        spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        'SubComp',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#666666'),
        spaceAfter=14,
    )
    label_style = ParagraphStyle(
        'LabelComp',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#444444'),
        alignment=TA_LEFT,
    )
    value_style = ParagraphStyle(
        'ValueComp',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_LEFT,
    )

    cliente = comprobante.cliente
    fecha_txt = timezone.localtime(comprobante.fecha_cambio).strftime('%d/%m/%Y %H:%M')
    story = [
        Paragraph('DelcoChile Telecomunicaciones', title_style),
        Paragraph('Comprobante digital de cambio de medidor', sub_style),
        Paragraph(
            f'OT #{comprobante.orden_id} · Generado '
            f'{timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")}',
            sub_style,
        ),
        Spacer(1, 0.3 * cm),
    ]

    datos_cliente = [
        [Paragraph('<b>Datos del cliente</b>', value_style), ''],
        [Paragraph('N° cliente', label_style), Paragraph(str(cliente.numero_cliente or '—'), value_style)],
        [Paragraph('Nombre', label_style), Paragraph(str(cliente.customer_name or '—'), value_style)],
        [
            Paragraph('Dirección', label_style),
            Paragraph(
                str(cliente.installation_address or cliente.direccion or '—'),
                value_style,
            ),
        ],
        [Paragraph('Comuna', label_style), Paragraph(str(cliente.comuna or '—'), value_style)],
        [Paragraph('Fecha del cambio', label_style), Paragraph(fecha_txt, value_style)],
    ]
    t1 = Table(datos_cliente, colWidths=[5 * cm, 12 * cm])
    t1.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#E8EEF5')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#DDDDDD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t1)
    story.append(Spacer(1, 0.5 * cm))

    datos_medidor = [
        [Paragraph('<b>Medidores</b>', value_style), ''],
        [
            Paragraph('Medidor retirado', label_style),
            Paragraph(
                f'{comprobante.medidor_retirado_serie or "—"}'
                + (f' ({comprobante.medidor_retirado_marca})' if comprobante.medidor_retirado_marca else ''),
                value_style,
            ),
        ],
        [
            Paragraph('Medidor instalado', label_style),
            Paragraph(
                f'{comprobante.medidor_instalado_serie}'
                + (f' ({comprobante.medidor_instalado_marca})' if comprobante.medidor_instalado_marca else ''),
                value_style,
            ),
        ],
        [
            Paragraph('Técnico', label_style),
            Paragraph(
                comprobante.tecnico.nombre_interno if comprobante.tecnico_id else '—',
                value_style,
            ),
        ],
    ]
    t2 = Table(datos_medidor, colWidths=[5 * cm, 12 * cm])
    t2.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#E8EEF5')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#DDDDDD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t2)

    if comprobante.observaciones:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph('<b>Observaciones</b>', value_style))
        story.append(Paragraph(comprobante.observaciones.replace('\n', '<br/>'), label_style))

    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph('<b>Firmas</b>', value_style))
    story.append(Spacer(1, 0.3 * cm))

    def _firma_flowable(archivo, label_sin, style_lbl):
        if not archivo:
            return Paragraph(f'<i>{label_sin}</i>', style_lbl)
        try:
            path = archivo.path
            with open(path, 'rb') as fh:
                raw = _png_sobre_fondo_blanco(fh.read())
            tmp = BytesIO(raw)
            # Mantener proporción pero con tamaño legible en el PDF
            return Image(tmp, width=7 * cm, height=2.5 * cm, kind='proportional')
        except Exception:
            return Paragraph('<i>(firma adjunta — no se pudo incrustar en PDF)</i>', style_lbl)

    firma_cli = _firma_flowable(comprobante.firma_cliente, 'Sin firma', label_style)
    firma_tec = _firma_flowable(comprobante.firma_tecnico, 'Opcional — sin firma', label_style)

    nombre_cli = comprobante.nombre_firmante_cliente or 'Cliente'
    nombre_tec = comprobante.tecnico.nombre_interno if comprobante.tecnico_id else 'Técnico'

    firmas = Table(
        [
            [
                Paragraph(f'<b>Cliente</b><br/>{nombre_cli}', label_style),
                Paragraph(f'<b>Técnico</b><br/>{nombre_tec}', label_style),
            ],
            [firma_cli, firma_tec],
        ],
        colWidths=[8.5 * cm, 8.5 * cm],
    )
    firmas.setStyle(TableStyle([
        ('BOX', (0, 0), (0, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('BOX', (1, 0), (1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(firmas)
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(
        'Documento generado por la plataforma DelcoChile Inventario. '
        'Constituye respaldo digital de la intervención de cambio de medidor.',
        sub_style,
    ))

    doc.build(story)
    return buffer.getvalue()


def _pdf_escape(text: str) -> str:
    return (text or '').replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _generar_pdf_minimo(comprobante) -> bytes:
    """PDF de texto simple cuando reportlab no está disponible (p. ej. Python 3.14)."""
    cliente = comprobante.cliente
    fecha_txt = timezone.localtime(comprobante.fecha_cambio).strftime('%d/%m/%Y %H:%M')
    lineas = [
        'DelcoChile Telecomunicaciones',
        'Comprobante digital de cambio de medidor',
        f'OT #{comprobante.orden_id}',
        f'Cliente: {cliente.numero_cliente} — {cliente.customer_name or ""}',
        f'Direccion: {cliente.installation_address or cliente.direccion or ""}',
        f'Fecha cambio: {fecha_txt}',
        f'Medidor retirado: {comprobante.medidor_retirado_serie or "-"}',
        f'Medidor instalado: {comprobante.medidor_instalado_serie}',
        f'Tecnico: {comprobante.tecnico.nombre_interno if comprobante.tecnico_id else "-"}',
        f'Firmante cliente: {comprobante.nombre_firmante_cliente or "-"}',
        f'Observaciones: {comprobante.observaciones or "-"}',
        f'Firma cliente: {"SI" if comprobante.firma_cliente else "NO"}',
        f'Firma tecnico: {"SI" if comprobante.firma_tecnico else "NO"}',
    ]
    # Construir stream de texto PDF (coordenadas desde abajo)
    y = 750
    content_lines = ['BT', '/F1 11 Tf', '14 TL']
    for i, linea in enumerate(lineas):
        safe = _pdf_escape(linea[:110])
        if i == 0:
            content_lines.append(f'50 {y} Td ({safe}) Tj')
        else:
            content_lines.append(f'T* ({safe}) Tj')
    content_lines.append('ET')
    stream = '\n'.join(content_lines).encode('latin-1', errors='replace')

    objects = []
    objects.append(b'1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n')
    objects.append(b'2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n')
    objects.append(
        b'3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        b'/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n'
    )
    objects.append(
        f'4 0 obj<< /Length {len(stream)} >>stream\n'.encode('ascii')
        + stream
        + b'\nendstream\nendobj\n'
    )
    objects.append(b'5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n')

    out = BytesIO()
    out.write(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj)
    xref_pos = out.tell()
    out.write(f'xref\n0 {len(objects) + 1}\n'.encode('ascii'))
    out.write(b'0000000000 65535 f \n')
    for off in offsets[1:]:
        out.write(f'{off:010d} 00000 n \n'.encode('ascii'))
    out.write(
        f'trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
        f'startxref\n{xref_pos}\n%%EOF\n'.encode('ascii')
    )
    return out.getvalue()


def crear_comprobante_cambio(
    *,
    orden,
    usuario,
    medidor_instalado_serie: str,
    medidor_retirado_serie: str = '',
    medidor_instalado_marca: str = '',
    medidor_retirado_marca: str = '',
    fecha_cambio=None,
    nombre_firmante_cliente: str = '',
    observaciones: str = '',
    firma_cliente_data: str = '',
    firma_tecnico_data: str = '',
    pdf_subido=None,
):
    """Crea el comprobante, guarda firmas y genera (o adjunta) el PDF."""
    from ordenes_trabajo.models import ComprobanteCambioMedidor

    if not orden.cliente_id:
        raise ValueError('La orden no tiene cliente asociado.')

    serie_inst = (medidor_instalado_serie or '').strip()
    # Con PDF subido la serie es opcional (el documento ya trae el detalle)
    if not serie_inst and not pdf_subido:
        raise ValueError('Debe indicar la serie del medidor instalado.')

    if fecha_cambio is None:
        fecha_cambio = timezone.now()
    elif isinstance(fecha_cambio, str):
        fecha_cambio = datetime.fromisoformat(fecha_cambio)
        if timezone.is_naive(fecha_cambio):
            fecha_cambio = timezone.make_aware(fecha_cambio, timezone.get_current_timezone())

    comprobante = ComprobanteCambioMedidor(
        orden=orden,
        cliente=orden.cliente,
        medidor_retirado_serie=(medidor_retirado_serie or '').strip(),
        medidor_retirado_marca=(medidor_retirado_marca or '').strip(),
        medidor_instalado_serie=serie_inst,
        medidor_instalado_marca=(medidor_instalado_marca or '').strip(),
        fecha_cambio=fecha_cambio,
        nombre_firmante_cliente=(nombre_firmante_cliente or '').strip(),
        observaciones=(observaciones or '').strip(),
        tecnico=orden.tecnico_responsable,
        creado_por=usuario,
    )

    if firma_cliente_data:
        _guardar_firma(comprobante, 'firma_cliente', firma_cliente_data, 'firma_cliente')
    if firma_tecnico_data:
        _guardar_firma(comprobante, 'firma_tecnico', firma_tecnico_data, 'firma_tecnico')

    if pdf_subido:
        nombre = get_valid_filename(pdf_subido.name or f'comprobante_ot{orden.pk}.pdf')
        if not nombre.lower().endswith('.pdf'):
            nombre += '.pdf'
        comprobante.pdf.save(nombre, pdf_subido, save=False)
        comprobante.pdf_subido = True
        comprobante.save()
    else:
        comprobante.save()
        try:
            pdf_bytes = generar_pdf_comprobante(comprobante)
            nombre = get_valid_filename(
                f'comprobante_cambio_ot{orden.pk}_{timezone.now():%Y%m%d%H%M%S}.pdf'
            )
            comprobante.pdf.save(nombre, ContentFile(pdf_bytes), save=True)
        except Exception as exc:
            # Mantener el registro aunque falle el PDF (p. ej. reportlab ausente)
            register_audit_event(
                AuditEvent(
                    actor_id=getattr(usuario, 'id', None),
                    action='COMPROBANTE_CAMBIO_CREATE',
                    entity='ComprobanteCambioMedidor',
                    entity_id=str(comprobante.pk),
                    field_name='pdf',
                    old_value='',
                    new_value='ERROR',
                    reason=f'Comprobante OT #{orden.pk} sin PDF: {exc}',
                )
            )
            raise RuntimeError(
                f'Comprobante #{comprobante.pk} guardado, pero no se pudo generar el PDF: {exc}'
            ) from exc

    register_audit_event(
        AuditEvent(
            actor_id=getattr(usuario, 'id', None),
            action='COMPROBANTE_CAMBIO_CREATE',
            entity='ComprobanteCambioMedidor',
            entity_id=str(comprobante.pk),
            field_name='medidor_instalado_serie',
            old_value=comprobante.medidor_retirado_serie,
            new_value=comprobante.medidor_instalado_serie,
            reason=f'Comprobante de cambio de medidor en OT #{orden.pk}',
        )
    )
    return comprobante
