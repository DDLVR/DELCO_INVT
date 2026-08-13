"""Utilidades de presentación para observaciones (HTML seguro, estilo documento)."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import List, Optional, Tuple


# Documento enriquecido: negrita, resaltado, tamaños, listas y tablas
_ALLOWED_TAGS = frozenset({
    'b', 'strong', 'mark', 'br', 'p', 'div',
    'span', 'font',
    'ul', 'ol', 'li',
    'h1', 'h2', 'h3',
    'u', 'i', 'em',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
})
_VOID_TAGS = frozenset({'br'})
_TABLE_TAGS = frozenset({'table', 'thead', 'tbody', 'tr', 'th', 'td'})
_TABLE_BORDER_CLASSES = frozenset({
    'delco-obs-table--medium',
    'delco-obs-table--thick',
})

_FONT_SIZE_MAP = {
    '1': '10px',
    '2': '12px',
    '3': '14px',
    '4': '16px',
    '5': '18px',
    '6': '22px',
    '7': '28px',
}


def _style_seguro(style: str, *, permitir_fondo: bool = True) -> str:
    """Filtra propiedades CSS peligrosas; deja font-size y fondo de resaltado."""
    if not style:
        return ''
    parts = []
    for chunk in style.split(';'):
        chunk = chunk.strip()
        if not chunk or ':' not in chunk:
            continue
        prop, val = chunk.split(':', 1)
        prop = prop.strip().lower()
        val = val.strip().lower()
        if prop == 'font-size':
            # Solo tamaños razonables (px o pt o keywords)
            if re.match(r'^\d{1,2}(\.\d+)?(px|pt)$', val) or val in (
                'x-small', 'small', 'medium', 'large', 'x-large', 'xx-large',
            ):
                parts.append(f'font-size: {val}')
        elif permitir_fondo and prop in ('background', 'background-color'):
            if any(x in val for x in ('fff59d', 'yellow', '255, 245, 157', '255,245,157', '#ff0')):
                parts.append('background-color: #fff59d')
        elif prop == 'font-weight' and val in ('bold', '700', '800', '900'):
            parts.append('font-weight: bold')
    return '; '.join(parts)


class _ObsSanitizer(HTMLParser):
    """Parser que conserva solo etiquetas/atributos seguros de documento."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []
        self._stack: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag = (tag or '').lower()
        attrs = attrs or []

        if tag == 'span':
            style = ''
            for name, value in attrs:
                if (name or '').lower() == 'style':
                    style = value or ''
                    break
            safe = _style_seguro(style)
            # Resaltado → <mark>
            if 'background-color: #fff59d' in safe and 'font-size' not in safe:
                self._stack.append('mark')
                self._parts.append('<mark>')
                return
            if safe:
                self._stack.append('span')
                self._parts.append(f'<span style="{html.escape(safe, quote=True)}">')
            else:
                # span vacío de estilo: no abrir etiqueta, pero trackear como noop
                self._stack.append('span-skip')
            return

        if tag == 'font':
            size = ''
            back = ''
            style = ''
            for name, value in attrs:
                n = (name or '').lower()
                v = value or ''
                if n == 'size':
                    size = v.strip()
                elif n in ('backcolor', 'bgcolor'):
                    back = v.lower()
                elif n == 'style':
                    style = v
            if 'yellow' in back or 'fff59d' in back:
                self._stack.append('mark')
                self._parts.append('<mark>')
                return
            font_size = _FONT_SIZE_MAP.get(size, '')
            safe = _style_seguro(style)
            if font_size and 'font-size' not in safe:
                safe = (safe + '; ' if safe else '') + f'font-size: {font_size}'
            if safe:
                self._stack.append('span')
                self._parts.append(f'<span style="{html.escape(safe, quote=True)}">')
            else:
                self._stack.append('span-skip')
            return

        if tag not in _ALLOWED_TAGS:
            return

        if tag in _VOID_TAGS:
            self._parts.append('<br>')
            return

        if tag == 'table':
            self._stack.append('table')
            classes = ['delco-obs-table']
            for name, value in attrs:
                if (name or '').lower() != 'class':
                    continue
                for token in (value or '').split():
                    token_l = token.lower()
                    if token_l in _TABLE_BORDER_CLASSES and token_l not in classes:
                        classes.append(token_l)
            self._parts.append(f'<table class="{" ".join(classes)}">')
            return

        if tag in ('th', 'td'):
            self._stack.append(tag)
            self._parts.append(f'<{tag}>')
            return

        self._stack.append(tag)
        self._parts.append(f'<{tag}>')

    def handle_endtag(self, tag):
        tag = (tag or '').lower()
        if tag == 'font':
            tag = 'span'  # se abrió como span/mark/span-skip
        if tag == 'span':
            # Cerrar mark / span / span-skip
            if self._stack and self._stack[-1] in ('mark', 'span', 'span-skip'):
                top = self._stack.pop()
                if top == 'mark':
                    self._parts.append('</mark>')
                elif top == 'span':
                    self._parts.append('</span>')
            return
        if tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        if tag in self._stack:
            while self._stack:
                top = self._stack.pop()
                if top == 'span-skip':
                    if top == tag or tag == 'span':
                        break
                    continue
                if top == 'mark':
                    self._parts.append('</mark>')
                else:
                    self._parts.append(f'</{top}>')
                if top == tag:
                    break

    def handle_data(self, data):
        if data:
            self._parts.append(html.escape(data))

    def handle_entityref(self, name):
        self._parts.append(f'&{name};')

    def handle_charref(self, name):
        self._parts.append(f'&#{name};')

    def get_html(self):
        while self._stack:
            top = self._stack.pop()
            if top == 'span-skip':
                continue
            if top == 'mark':
                self._parts.append('</mark>')
            else:
                self._parts.append(f'</{top}>')
        return ''.join(self._parts)


def sanitizar_observaciones_html(texto: str) -> str:
    """
    Limpia HTML de observaciones permitiendo formato de documento:
    negrita, resaltado, tamaños, listas y tablas con cuadrícula.
    """
    if texto is None:
        return ''
    raw = str(texto).strip()
    if not raw:
        return ''

    if '<' not in raw:
        return html.escape(raw).replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>\n')

    parser = _ObsSanitizer()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return html.escape(raw).replace('\n', '<br>\n')

    cleaned = parser.get_html().strip()
    cleaned = re.sub(r'(?:<br>\s*){3,}', '<br><br>', cleaned)
    return cleaned


def observaciones_a_texto_plano(texto: str) -> str:
    """Quita etiquetas para Excel / búsquedas."""
    if not texto:
        return ''
    plain = re.sub(r'<br\s*/?>', '\n', str(texto), flags=re.I)
    plain = re.sub(r'</?[^>]+>', '', plain)
    plain = html.unescape(plain)
    return plain.strip()


def observaciones_a_reportlab(texto: str) -> str:
    """
    Convierte HTML permitido a markup de Paragraph de reportlab (sin tablas).
    Las tablas se manejan aparte en el generador de PDF.
    """
    if not texto:
        return ''
    safe = sanitizar_observaciones_html(texto)
    safe = re.sub(r'</?strong>', lambda m: '<b>' if m.group(0).startswith('<s') else '</b>', safe, flags=re.I)
    safe = re.sub(
        r'<mark>(.*?)</mark>',
        r'<font backColor="yellow">\1</font>',
        safe,
        flags=re.I | re.S,
    )
    # Tamaños → font size aprox
    safe = re.sub(
        r'<span style="[^"]*font-size:\s*(\d+)(?:px|pt)[^"]*">(.*?)</span>',
        lambda m: f'<font size="{max(8, min(18, int(m.group(1)) - 2))}">{m.group(2)}</font>',
        safe,
        flags=re.I | re.S,
    )
    safe = re.sub(r'</?span[^>]*>', '', safe, flags=re.I)
    safe = re.sub(r'</?div>', '', safe, flags=re.I)
    safe = re.sub(r'</?p>', '<br/>', safe, flags=re.I)
    safe = re.sub(r'</?u>', '', safe, flags=re.I)
    safe = re.sub(r'</?i>', '', safe, flags=re.I)
    safe = re.sub(r'</?em>', '', safe, flags=re.I)
    safe = re.sub(r'</?h[1-3]>', lambda m: '<br/><b>' if m.group(0).startswith('<h') else '</b><br/>', safe, flags=re.I)
    safe = re.sub(r'</?ul>|</?ol>|</?li>', '<br/>', safe, flags=re.I)
    # Quitar tablas del paragraph (se renderizan aparte)
    safe = re.sub(r'<table[\s\S]*?</table>', '', safe, flags=re.I)
    return safe


def _extraer_tablas_y_bloques(html_safe: str) -> List[Tuple[str, object]]:
    """
    Separa el HTML en bloques ('html', fragmento) y ('table', dict con rows/border).
    """
    blocks: List[Tuple[str, object]] = []
    pos = 0
    for match in re.finditer(r'<table[\s\S]*?</table>', html_safe, flags=re.I):
        before = html_safe[pos:match.start()].strip()
        if before:
            blocks.append(('html', before))
        table_html = match.group(0)
        border = 'normal'
        class_m = re.search(r'<table[^>]*\bclass=["\']([^"\']*)["\']', table_html, flags=re.I)
        if class_m:
            tokens = class_m.group(1).lower().split()
            if 'delco-obs-table--thick' in tokens:
                border = 'thick'
            elif 'delco-obs-table--medium' in tokens:
                border = 'medium'
        rows = []
        for tr in re.finditer(r'<tr[\s\S]*?</tr>', table_html, flags=re.I):
            cells = re.findall(r'<t[hd][^>]*>([\s\S]*?)</t[hd]>', tr.group(0), flags=re.I)
            row = []
            for cell in cells:
                cell_plain = observaciones_a_texto_plano(cell)
                row.append(cell_plain)
            if row:
                rows.append(row)
        if rows:
            blocks.append(('table', {'rows': rows, 'border': border}))
        pos = match.end()
    after = html_safe[pos:].strip()
    if after:
        blocks.append(('html', after))
    if not blocks and html_safe.strip():
        blocks.append(('html', html_safe))
    return blocks


def observaciones_a_flowables(texto: str, styles) -> list:
    """Convierte observaciones HTML a flowables de reportlab (párrafos + tablas)."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    safe = sanitizar_observaciones_html(texto or '')
    if not safe:
        return []

    body = ParagraphStyle(
        'CargaObsBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        spaceAfter=6,
    )
    border_widths = {
        'normal': 0.6,
        'medium': 1.25,
        'thick': 2.2,
    }
    flowables = []
    for kind, payload in _extraer_tablas_y_bloques(safe):
        if kind == 'html':
            markup = observaciones_a_reportlab(payload)
            if markup.strip():
                # reportlab prefiere <br/> 
                markup = re.sub(r'<br\s*/?>', '<br/>', markup, flags=re.I)
                try:
                    flowables.append(Paragraph(markup, body))
                except Exception:
                    flowables.append(Paragraph(html.escape(observaciones_a_texto_plano(payload)), body))
        elif kind == 'table' and payload:
            rows = payload.get('rows') if isinstance(payload, dict) else payload
            border = payload.get('border', 'normal') if isinstance(payload, dict) else 'normal'
            if not rows:
                continue
            # Normalizar columnas
            max_cols = max(len(r) for r in rows)
            data = [r + [''] * (max_cols - len(r)) for r in rows]
            # Celdas como Paragraphs para wrap
            data_p = [[Paragraph(html.escape(c or '—'), body) for c in row] for row in data]
            grid_w = border_widths.get(border, 0.6)
            tbl = Table(data_p, hAlign='LEFT', colWidths=None)
            tbl.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), grid_w, colors.HexColor('#222222')),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            flowables.append(tbl)
            flowables.append(Spacer(1, 8))
    return flowables
