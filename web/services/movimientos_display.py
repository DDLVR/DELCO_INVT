"""Helpers de presentación para movimientos de inventario."""
from __future__ import annotations


def _cliente_label_from_obj(cliente) -> str:
    if not cliente:
        return ''
    numero = (getattr(cliente, 'numero_cliente', None) or '').strip()
    nombre = (
        getattr(cliente, 'customer_name', None)
        or getattr(cliente, 'nombre', None)
        or ''
    )
    nombre = str(nombre).strip()
    direccion = (
        getattr(cliente, 'installation_address', None)
        or getattr(cliente, 'direccion', None)
        or ''
    )
    direccion = str(direccion).strip()
    extra = nombre or direccion
    if numero and extra:
        return f'{numero} · {extra}'
    return numero or extra or str(cliente.pk)


def cliente_desde_item_movimiento(item):
    """Obtiene el Cliente vinculado a un MovimientoItem (vía equipo)."""
    if not item:
        return None
    for attr in ('medidor', 'simcard', 'modem'):
        equipo = getattr(item, attr, None)
        if equipo is not None:
            return getattr(equipo, 'cliente', None)
    return None


def etiqueta_ubicacion_movimiento(ubicacion, items=None, rol: str = 'destino') -> str:
    """Etiqueta legible de origen/destino.

    Si la ubicación es tipo CLIENTE, intenta enriquecer con el Nº/nombre del
    cliente actual del equipo vinculado al movimiento.
    """
    if not ubicacion:
        return '—'
    base = getattr(ubicacion, 'nombre', None) or '—'
    tipo = getattr(ubicacion, 'tipo', '') or ''
    if tipo != 'CLIENTE':
        return base

    clientes = []
    vistos = set()
    for item in items or []:
        cliente = cliente_desde_item_movimiento(item)
        if not cliente or cliente.pk in vistos:
            continue
        vistos.add(cliente.pk)
        label = _cliente_label_from_obj(cliente)
        if label:
            clientes.append(label)

    if not clientes:
        return base
    if len(clientes) == 1:
        return clientes[0]
    return f'{clientes[0]} (+{len(clientes) - 1} más)'


def enriquecer_movimiento_ubicaciones(movimiento) -> None:
    """Adjunta origen_display / destino_display al objeto movimiento."""
    items = list(movimiento.items.all()) if hasattr(movimiento, 'items') else []
    movimiento.origen_display = etiqueta_ubicacion_movimiento(
        getattr(movimiento, 'origen', None), items, rol='origen'
    )
    movimiento.destino_display = etiqueta_ubicacion_movimiento(
        getattr(movimiento, 'destino', None), items, rol='destino'
    )
