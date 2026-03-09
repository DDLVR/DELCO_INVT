from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Obtener un item de un diccionario en templates"""
    return dictionary.get(key, [])
