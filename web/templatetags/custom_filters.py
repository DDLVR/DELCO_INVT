"""Filtros y tags de presentación Delco: badges, fechas, RUT y números."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from web.services.audit_labels import label_accion, label_campo, label_entidad, label_valor

register = template.Library()

ESTADOS_MOREAPP_OK = frozenset({'PROCESADO', 'EXITOSO'})

# ── OT estado → Bootstrap badge classes ──────────────────────────────────────
OT_BADGE_CLASS = {
    'CREADA': 'bg-secondary',
    'ASIGNADA': 'bg-warning text-dark',
    'EN_EJECUCION': 'bg-primary',
    'REASIGNADA': 'bg-info text-dark',
    'MANTENIMIENTO': 'bg-info text-dark',
    'REALIZADA': 'bg-success',
    'REALIZADA_PENDIENTE_COMPROBACION': 'bg-info text-dark',
    'PENDIENTE_VALIDACION': 'bg-warning text-dark',
    'VALIDADA': 'bg-success',
    'OBSERVADA': 'bg-danger',
    'FINALIZADA': 'bg-success',
    'CANCELADA': 'bg-danger',
}

OT_BADGE_LABEL = {
    'CREADA': 'Creada',
    'ASIGNADA': 'Asignada',
    'EN_EJECUCION': 'En ejecución',
    'REASIGNADA': 'Reasignada',
    'MANTENIMIENTO': 'Mantenimiento',
    'REALIZADA': 'Realizada',
    'REALIZADA_PENDIENTE_COMPROBACION': 'Realizada - Pendiente comprobación',
    'PENDIENTE_VALIDACION': 'Pendiente validación',
    'VALIDADA': 'Validada',
    'OBSERVADA': 'Observada',
    'FINALIZADA': 'Finalizada',
    'CANCELADA': 'Cancelada',
}

# ── MoreApp sync ─────────────────────────────────────────────────────────────
MOREAPP_SYNC_BADGE = {
    'PROCESADO': ('bg-success', 'Procesado'),
    'EXITOSO': ('bg-success', 'Procesado'),
    'ALERTA_REVISION': ('bg-warning text-dark', 'Alerta'),
    'DUPLICADO': ('delco-badge-muted', 'Duplicado'),
    'ERROR_JSON': ('bg-danger', 'Error JSON'),
    'ERROR_LECTURA': ('bg-danger', 'Error lectura'),
    'ERROR': ('bg-danger', 'Error'),
    'PENDIENTE': ('bg-info text-dark', 'Pendiente'),
}

# ── MoreApp revisión ─────────────────────────────────────────────────────────
MOREAPP_REVISION_BADGE = {
    'REVISADO': ('bg-success', 'Revisado'),
    'CON_ADVERTENCIA': ('bg-warning text-dark', 'Con advertencia'),
    'DESCARTADO': ('delco-badge-muted', 'Descartado'),
    'PENDIENTE': ('bg-primary', 'Pendiente'),
}

# ── SCi4 / STB (estado sistema externo) ──────────────────────────────────────
ESTADO_EXTERNO_BADGE = {
    'PENDIENTE': ('bg-warning text-dark', 'Pendiente'),
    'ACTUALIZADO': ('bg-success', 'Actualizado'),
    'SIN_REGISTRO': ('bg-secondary', 'Sin registro'),
}

# ── Prioridad (cargas / soporte) ─────────────────────────────────────────────
PRIORIDAD_BADGE = {
    'BAJA': ('bg-secondary', 'Baja'),
    'MEDIA': ('bg-info text-dark', 'Media'),
    'ALTA': ('bg-warning text-dark', 'Alta'),
    'CRITICA': ('bg-danger', 'Crítica'),
}

# ── Cargas administrativas ───────────────────────────────────────────────────
CARGA_ESTADO_BADGE = {
    'PENDIENTE': ('bg-warning text-dark', 'Pendiente'),
    'EN_PROGRESO': ('bg-info text-dark', 'En progreso'),
    'COMPLETADA': ('bg-success', 'Completada'),
    'CANCELADA': ('bg-dark', 'Cancelada'),
}

# ── Inventario (por nombre de catálogo, normalizado) ──────────────────────────
INVENTARIO_ESTADO_BADGE = {
    'instalado': 'bg-success',
    'en trayecto': 'bg-primary',
    'retirado': 'bg-warning text-dark',
    'devuelta': 'bg-warning text-dark',
    'devuelto': 'bg-warning text-dark',
    'en reparación': 'bg-info text-dark',
    'en reparacion': 'bg-info text-dark',
    'con problemas': 'bg-info text-dark',
    'sin conexión': 'bg-dark',
    'sin conexion': 'bg-dark',
    'dado de baja': 'bg-danger',
    'en peaje': 'bg-dark',
    'en bodega': 'bg-secondary',
    'disponible': 'bg-secondary',
}


def _badge_html(css_class, label, title=None):
    if title:
        return format_html(
            '<span class="badge {}" title="{}">{}</span>',
            css_class,
            title,
            label,
        )
    return format_html('<span class="badge {}">{}</span>', css_class, label)


# ── Filtros existentes ───────────────────────────────────────────────────────

@register.filter
def get_item(dictionary, key):
    """Obtener un item de un diccionario en templates"""
    return dictionary.get(key, [])


@register.filter
def moreapp_sync_ok(estado):
    """True si el registro MoreApp se sincronizó correctamente (legacy o actual)."""
    return estado in ESTADOS_MOREAPP_OK


@register.filter
def audit_action_label(codigo):
    """Acción de auditoría en texto legible."""
    return label_accion(codigo)


@register.filter
def audit_entity_label(codigo):
    """Entidad de auditoría en texto legible."""
    return label_entidad(codigo)


@register.filter
def audit_field_label(codigo):
    """Campo de auditoría en texto legible."""
    return label_campo(codigo)


@register.filter
def audit_value_label(codigo):
    """Valor anterior/nuevo de auditoría en texto legible."""
    return label_valor(codigo)


@register.filter
def es_sin_proyecto(valor):
    """True si el valor representa ausencia de proyecto."""
    from web.services.filtros_export import es_sin_proyecto as _es_sin_proyecto
    return _es_sin_proyecto(valor)


# ── Clases CSS (filtros) ─────────────────────────────────────────────────────

@register.filter
def badge_ot_class(estado):
    return OT_BADGE_CLASS.get(estado or '', 'bg-secondary')


@register.filter
def badge_moreapp_sync_class(estado):
    return MOREAPP_SYNC_BADGE.get(estado or '', ('delco-badge-muted', ''))[0]


@register.filter
def badge_moreapp_revision_class(estado):
    return MOREAPP_REVISION_BADGE.get(estado or '', ('bg-primary', 'Pendiente'))[0]


@register.filter
def badge_prioridad_class(prioridad):
    return PRIORIDAD_BADGE.get(prioridad or '', ('bg-secondary', ''))[0]


@register.filter
def badge_carga_estado_class(estado):
    return CARGA_ESTADO_BADGE.get(estado or '', ('bg-secondary', ''))[0]


@register.filter
def badge_estado_externo_class(estado):
    return ESTADO_EXTERNO_BADGE.get(estado or '', ('bg-secondary', 'Sin registro'))[0]


@register.filter
def badge_inventario_class(nombre):
    if not nombre:
        return 'bg-secondary'
    key = str(nombre).strip().lower()
    return INVENTARIO_ESTADO_BADGE.get(key, 'bg-secondary')


# ── Badges HTML (tags) ───────────────────────────────────────────────────────

@register.simple_tag
def badge_ot(estado, label=None):
    css = OT_BADGE_CLASS.get(estado or '', 'bg-secondary')
    text = label or OT_BADGE_LABEL.get(estado or '', estado or '—')
    return _badge_html(css, text)


@register.simple_tag
def badge_moreapp_sync(estado, label=None):
    css, default_label = MOREAPP_SYNC_BADGE.get(
        estado or '', ('delco-badge-muted', estado or '—')
    )
    return _badge_html(css, label or default_label)


@register.simple_tag
def badge_moreapp_revision(estado, label=None):
    css, default_label = MOREAPP_REVISION_BADGE.get(
        estado or '', ('bg-primary', 'Pendiente')
    )
    return _badge_html(css, label or default_label)


@register.simple_tag
def badge_estado_externo(estado, label=None, sistema='SCi4'):
    css, default_label = ESTADO_EXTERNO_BADGE.get(
        estado or '', ('bg-secondary', 'Sin registro')
    )
    text = label or default_label
    titles = {
        'PENDIENTE': 'Pendiente de actualización en {}'.format(sistema),
        'ACTUALIZADO': 'Actualizado en {}'.format(sistema),
        'SIN_REGISTRO': 'Sin registro en {}'.format(sistema),
    }
    return _badge_html(css, text, title=titles.get(estado or ''))


@register.simple_tag
def badge_prioridad(prioridad, label=None):
    css, default_label = PRIORIDAD_BADGE.get(
        prioridad or '', ('bg-secondary', prioridad or '—')
    )
    return _badge_html(css, label or default_label)


@register.simple_tag
def badge_carga_estado(estado, label=None):
    css, default_label = CARGA_ESTADO_BADGE.get(
        estado or '', ('bg-secondary', estado or '—')
    )
    return _badge_html(css, label or default_label)


@register.simple_tag
def badge_inventario(nombre, label=None):
    text = label or nombre or 'Sin estado'
    css = badge_inventario_class(nombre)
    return _badge_html(css, text)


# ── Formatos ─────────────────────────────────────────────────────────────────

@register.filter
def format_fecha(value, default='—'):
    """Fecha en formato dd/mm/YYYY. Vacío → em dash."""
    if value in (None, ''):
        return default
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    return default


@register.filter
def format_fecha_hora(value, default='—'):
    """Fecha-hora en formato dd/mm/YYYY HH:MM. Vacío → em dash."""
    if value in (None, ''):
        return default
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    return default


@register.filter
def format_fecha_corta(value, default='—'):
    """Fecha corta sin año: dd/mm HH:MM (útil en hubs)."""
    if value in (None, ''):
        return default
    if isinstance(value, datetime):
        return value.strftime('%d/%m %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m')
    return default


@register.filter
def format_rut(value, default='—'):
    """Muestra RUT con puntos y guión (12.345.678-K). Acepta con o sin formato."""
    if value in (None, ''):
        return default
    raw = str(value).strip().upper().replace('.', '').replace('-', '').replace(' ', '')
    if len(raw) < 2:
        return value
    cuerpo, dv = raw[:-1], raw[-1]
    if not cuerpo.isdigit():
        return value
    # Miles desde la derecha
    partes = []
    while cuerpo:
        partes.append(cuerpo[-3:])
        cuerpo = cuerpo[:-3]
    cuerpo_fmt = '.'.join(reversed(partes))
    return '{}-{}'.format(cuerpo_fmt, dv)


@register.filter
def format_numero(value, default='—'):
    """Entero con separador de miles estilo es-CL (1.234)."""
    if value in (None, ''):
        return default
    try:
        if isinstance(value, Decimal):
            n = int(value)
        else:
            n = int(value)
    except (TypeError, ValueError):
        return value
    negativo = n < 0
    s = str(abs(n))
    partes = []
    while s:
        partes.append(s[-3:])
        s = s[:-3]
    out = '.'.join(reversed(partes))
    return '-' + out if negativo else out


@register.filter
def vacio(value, default='—'):
    """Placeholder uniforme para valores vacíos."""
    if value in (None, '', []):
        return mark_safe(default) if default == '—' else default
    return value
