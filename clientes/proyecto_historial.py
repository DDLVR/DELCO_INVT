"""Servicios de historial de proyectos asociados a un cliente."""
from __future__ import annotations

from typing import Optional, Tuple, Union

from django.db import transaction
from django.utils import timezone

from clientes.models import Cliente, ClienteProyectoHistorial
from web.services.filtros_export import es_sin_proyecto

MOTIVO_REEMPLAZADO = 'Reemplazado por otro proyecto'


def _normalizar_proyecto(valor) -> str:
    texto = (str(valor).strip() if valor is not None else '')
    if es_sin_proyecto(texto):
        return ''
    return texto


def estado_proyecto_ui(item: ClienteProyectoHistorial) -> Tuple[str, str]:
    """Actual = proyecto vigente; Reemplazado = ya no es el actual."""
    if item.vigente:
        return 'actual', 'Actual'
    return 'reemplazado', 'Reemplazado'


def obtener_o_crear_proyecto(nombre: str, *, activo: bool = True):
    """Resuelve el catálogo Proyecto por nombre (case-insensitive)."""
    from catalogos.models import Proyecto

    texto = _normalizar_proyecto(nombre)
    if not texto:
        return None
    existente = Proyecto.objects.filter(nombre__iexact=texto).first()
    if existente:
        if not existente.activo and activo:
            existente.activo = True
            existente.save(update_fields=['activo', 'fecha_actualizacion'])
        return existente
    return Proyecto.objects.create(nombre=texto[:255], activo=activo)


def sincronizar_proyecto_asignado(cliente: Cliente, nombre_proyecto: str) -> None:
    """Actualiza Cliente.proyecto_asignado según el texto de proyecto."""
    from catalogos.models import Proyecto

    texto = _normalizar_proyecto(nombre_proyecto)
    if not texto:
        if cliente.proyecto_asignado_id:
            cliente.proyecto_asignado = None
            cliente.save(update_fields=['proyecto_asignado', 'fecha_actualizacion'])
        return
    proyecto = obtener_o_crear_proyecto(texto)
    if proyecto and cliente.proyecto_asignado_id != proyecto.pk:
        cliente.proyecto_asignado = proyecto
        cliente.save(update_fields=['proyecto_asignado', 'fecha_actualizacion'])


@transaction.atomic
def registrar_cambio_proyecto(
    cliente: Cliente,
    nuevo_proyecto: Union[str, None],
    *,
    usuario=None,
    motivo: str = '',
    actualizar_campo: bool = True,
) -> bool:
    """
    Registra un cambio de proyecto en el historial del cliente.

    - Cierra el período actual (si existe).
    - Abre un nuevo período con el proyecto nuevo (si no está vacío / sin proyecto).
    - Opcionalmente actualiza Cliente.proyecto (texto legado).
    - Sincroniza Cliente.proyecto_asignado (FK al catálogo).

    Retorna True si hubo cambio efectivo respecto al valor anterior.
    """
    # Bloqueo de fila para evitar dos períodos vigentes concurrentes
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)

    nuevo = _normalizar_proyecto(nuevo_proyecto)
    actual = _normalizar_proyecto(getattr(cliente, 'proyecto', None))
    vigentes = list(
        ClienteProyectoHistorial.objects.select_for_update()
        .filter(cliente=cliente, vigente=True)
        .order_by('-fecha_inicio', '-id')
    )
    vigente_existe = bool(vigentes)

    # Mismo proyecto: solo asegurar fila de historial si falta (datos legacy / alta)
    if nuevo == actual:
        if nuevo and not vigente_existe:
            ClienteProyectoHistorial.objects.create(
                cliente=cliente,
                proyecto=nuevo,
                fecha_inicio=getattr(cliente, 'fecha_creacion', None) or timezone.now(),
                vigente=True,
                cambiado_por=usuario if getattr(usuario, 'pk', None) else None,
                motivo=(motivo or 'Registro inicial').strip(),
            )
        sincronizar_proyecto_asignado(cliente, nuevo)
        return False

    ahora = timezone.now()
    for item in vigentes:
        item.vigente = False
        item.fecha_fin = ahora
        # Conservar motivo original; solo completar si estaba vacío
        if not (item.motivo or '').strip():
            item.motivo = (motivo or MOTIVO_REEMPLAZADO).strip() or MOTIVO_REEMPLAZADO
            item.save(update_fields=['vigente', 'fecha_fin', 'motivo'])
        else:
            item.save(update_fields=['vigente', 'fecha_fin'])

    if nuevo:
        ClienteProyectoHistorial.objects.create(
            cliente=cliente,
            proyecto=nuevo,
            fecha_inicio=ahora,
            vigente=True,
            cambiado_por=usuario if getattr(usuario, 'pk', None) else None,
            motivo=(motivo or '').strip(),
        )

    if actualizar_campo:
        # Mantener convención histórica: vacío -> None
        cliente.proyecto = nuevo or None
        cliente.save(update_fields=['proyecto', 'fecha_actualizacion'])

    sincronizar_proyecto_asignado(cliente, nuevo)
    return True


def asegurar_historial_inicial(cliente: Cliente, *, usuario=None) -> Optional[ClienteProyectoHistorial]:
    """
    Si el cliente tiene proyecto actual pero no hay filas de historial,
    crea la fila vigente inicial (útil para datos legacy).
    """
    if ClienteProyectoHistorial.objects.filter(cliente=cliente).exists():
        sincronizar_proyecto_asignado(cliente, getattr(cliente, 'proyecto', None) or '')
        return None
    proyecto = _normalizar_proyecto(getattr(cliente, 'proyecto', None))
    if not proyecto:
        return None
    fila = ClienteProyectoHistorial.objects.create(
        cliente=cliente,
        proyecto=proyecto,
        fecha_inicio=getattr(cliente, 'fecha_creacion', None) or timezone.now(),
        vigente=True,
        cambiado_por=usuario if getattr(usuario, 'pk', None) else None,
        motivo='Registro inicial (dato existente)',
    )
    sincronizar_proyecto_asignado(cliente, proyecto)
    return fila


def asignar_proyecto_al_crear_ot(cliente: Cliente, nombre_proyecto, *, usuario=None, motivo: str = '') -> bool:
    """
    Al crear una OT/carga: el cliente queda en ese proyecto.
    No hace nada si el nombre está vacío / «sin proyecto».
    """
    if not cliente or not getattr(cliente, 'pk', None):
        return False
    texto = _normalizar_proyecto(nombre_proyecto)
    if not texto:
        return False
    return registrar_cambio_proyecto(
        cliente,
        texto,
        usuario=usuario,
        motivo=motivo or 'Asignado al crear orden/carga administrativa',
        actualizar_campo=True,
    )
