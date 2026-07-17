from django import template

from web.services.audit_labels import label_accion, label_campo, label_entidad, label_valor

register = template.Library()

ESTADOS_MOREAPP_OK = frozenset({'PROCESADO', 'EXITOSO'})


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