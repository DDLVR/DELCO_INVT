from django import template

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
