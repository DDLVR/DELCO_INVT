"""Utilidades de presentación para observaciones técnicas (HTML seguro)."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser


# Etiquetas permitidas para negrita y resaltado (más saltos de línea)
_ALLOWED_TAGS = frozenset({'b', 'strong', 'mark', 'br', 'p', 'div'})
_BLOCK_TAGS = frozenset({'p', 'div'})


class _ObsSanitizer(HTMLParser):
    """Parser que conserva solo etiquetas permitidas y escapa el resto."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts = []
        self._stack = []

    def handle_starttag(self, tag, attrs):
        tag = (tag or '').lower()
        if tag == 'span':
            # Convertir resaltado del navegador (hiliteColor) a <mark>
            style = ''
            for name, value in attrs or []:
                if (name or '').lower() == 'style':
                    style = (value or '').lower()
                    break
            if 'background' in style and (
                'fff59d' in style or 'yellow' in style or '255, 245, 157' in style
                or '255,245,157' in style
            ):
                self._stack.append('mark')
                self._parts.append('<mark>')
            return
        if tag == 'font':
            # Algunos editores usan font color/backcolor
            back = ''
            for name, value in attrs or []:
                if (name or '').lower() in ('style', 'backcolor', 'bgcolor'):
                    back = (value or '').lower()
            if 'yellow' in back or 'fff59d' in back:
                self._stack.append('mark')
                self._parts.append('<mark>')
            return
        if tag not in _ALLOWED_TAGS:
            return
        if tag == 'br':
            self._parts.append('<br>')
            return
        self._stack.append(tag)
        self._parts.append('<{}>'.format(tag))

    def handle_endtag(self, tag):
        tag = (tag or '').lower()
        if tag in ('span', 'font'):
            # Cerrar mark si el span/font se abrió como mark
            if self._stack and self._stack[-1] == 'mark':
                self._stack.pop()
                self._parts.append('</mark>')
            return
        if tag not in _ALLOWED_TAGS or tag == 'br':
            return
        if tag in self._stack:
            while self._stack:
                top = self._stack.pop()
                self._parts.append('</{}>'.format(top))
                if top == tag:
                    break

    def handle_data(self, data):
        if data:
            self._parts.append(html.escape(data))

    def handle_entityref(self, name):
        self._parts.append('&{};'.format(name))

    def handle_charref(self, name):
        self._parts.append('&#{};'.format(name))

    def get_html(self):
        while self._stack:
            top = self._stack.pop()
            self._parts.append('</{}>'.format(top))
        return ''.join(self._parts)


def sanitizar_observaciones_html(texto: str) -> str:
    """
    Limpia HTML de observaciones permitiendo solo negrita (<b>/<strong>)
    y resaltado (<mark>), más <br>/<p>.
    Texto plano se conserva escapado; saltos de línea se convierten a <br>.
    """
    if texto is None:
        return ''
    raw = str(texto).strip()
    if not raw:
        return ''

    # Si no parece HTML, tratar como texto plano con saltos de línea
    if '<' not in raw:
        return html.escape(raw).replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>\n')

    parser = _ObsSanitizer()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return html.escape(raw).replace('\n', '<br>\n')

    cleaned = parser.get_html().strip()
    # Colapsar espacios excesivos entre bloques
    cleaned = re.sub(r'(?:<br>\s*){3,}', '<br><br>', cleaned)
    return cleaned


def observaciones_a_texto_plano(texto: str) -> str:
    """Quita etiquetas para Excel / búsquedas."""
    if not texto:
        return ''
    plain = re.sub(r'<br\s*/?>', '\n', str(texto), flags=re.I)
    plain = re.sub(r'</?(?:b|strong|mark|p|div)\s*>', '', plain, flags=re.I)
    plain = html.unescape(plain)
    return plain.strip()


def observaciones_a_reportlab(texto: str) -> str:
    """
    Convierte HTML permitido a markup de Paragraph de reportlab.
    <b>/<strong> → <b>, <mark> → fondo amarillo con <font backColor="yellow">.
    """
    if not texto:
        return ''
    safe = sanitizar_observaciones_html(texto)
    # reportlab Paragraph usa un subconjunto distinto
    safe = re.sub(r'</?strong>', lambda m: '<b>' if m.group(0).startswith('<s') else '</b>', safe, flags=re.I)
    safe = re.sub(
        r'<mark>(.*?)</mark>',
        r'<font backColor="yellow">\1</font>',
        safe,
        flags=re.I | re.S,
    )
    safe = re.sub(r'</?p>', '', safe, flags=re.I)
    safe = re.sub(r'</?div>', '', safe, flags=re.I)
    # Escapar & que no sean entidades (sanitizer ya escapó texto)
    return safe
