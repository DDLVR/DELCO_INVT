"""Usuarios que pueden asignarse como responsable de una OT."""
from __future__ import annotations

from typing import Iterable, Optional

from usuarios.models import Usuario

# Técnico de campo y administrativo (oficina) pueden figurar como responsables.
ROLES_ASIGNABLES_OT = ('TECNICO', 'ADMINISTRATIVO')


def usuarios_asignables_ot(*, solo_activos: bool = True):
    """Queryset de usuarios elegibles para técnico_responsable de OT."""
    qs = Usuario.objects.filter(rol__in=ROLES_ASIGNABLES_OT)
    if solo_activos:
        qs = qs.filter(is_active=True)
    # Técnicos primero, luego administrativos; dentro de cada rol por nombre.
    return qs.order_by('rol', 'nombre_interno')


def get_usuario_asignable(pk) -> Usuario:
    """Obtiene un usuario activo asignable; lanza DoesNotExist si no aplica."""
    return Usuario.objects.get(pk=int(pk), rol__in=ROLES_ASIGNABLES_OT, is_active=True)


def etiqueta_asignable(usuario: Usuario) -> str:
    """Etiqueta para selects / autocomplete (incluye rol si no es técnico)."""
    nombre = (usuario.nombre_interno or '').strip() or str(usuario.pk)
    if usuario.rol == 'ADMINISTRATIVO':
        return f'{nombre} (Administrativo)'
    if usuario.rol != 'TECNICO':
        return f'{nombre} ({usuario.get_rol_display()})'
    return nombre


def es_usuario_asignable(usuario: Optional[Usuario]) -> bool:
    if not usuario or not getattr(usuario, 'is_active', False):
        return False
    return getattr(usuario, 'rol', None) in ROLES_ASIGNABLES_OT


def filtrar_ids_asignables(ids: Iterable[int]):
    return Usuario.objects.filter(
        pk__in=list(ids),
        rol__in=ROLES_ASIGNABLES_OT,
        is_active=True,
    )
