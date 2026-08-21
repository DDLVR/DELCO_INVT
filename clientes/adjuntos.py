"""Subida, papelera y auditoría de adjuntos asociados a la ficha del cliente."""

from __future__ import annotations

from django.utils import timezone
from django.utils.text import get_valid_filename

from web.services.audit import AuditEvent, register_audit_event

from .models import ClienteAdjunto

MAX_ADJUNTO_BYTES = 15 * 1024 * 1024
EXTENSIONES_IMAGEN = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
EXTENSIONES_PDF = ('.pdf',)
EXTENSIONES_PERMITIDAS = EXTENSIONES_IMAGEN + EXTENSIONES_PDF

ACCIONES_ADJUNTO = frozenset({
    'subir_adjunto',
    'reemplazar_adjunto',
    'papelera_adjunto',
    'recuperar_adjunto',
    'borrar_definitivo_adjunto',
})


def _inferir_tipo_adjunto(tipo_post, nombre):
    lower = (nombre or '').lower()
    es_img = lower.endswith(EXTENSIONES_IMAGEN)
    es_pdf = lower.endswith(EXTENSIONES_PDF)
    tipo = (tipo_post or '').strip().upper()

    if es_pdf:
        return 'PDF'
    if es_img:
        if tipo in ('FOTO', 'OTRO'):
            return tipo
        return 'FOTO'
    if tipo in dict(ClienteAdjunto.TIPO_CHOICES):
        return tipo
    return 'OTRO'


def validar_archivo_adjunto(request):
    """Valida archivo subido. Retorna (ok, mensaje_o_nombre, archivo, tipo)."""
    archivo = request.FILES.get('archivo')
    if not archivo:
        return False, 'Debes seleccionar un archivo.', None, None

    nombre = get_valid_filename(archivo.name or 'adjunto')
    lower = nombre.lower()
    if not lower.endswith(EXTENSIONES_PERMITIDAS):
        return False, 'Solo se permiten imágenes (jpg, png, webp, gif) o PDF.', None, None

    size = getattr(archivo, 'size', None) or 0
    if size <= 0:
        return False, 'El archivo está vacío.', None, None
    if size > MAX_ADJUNTO_BYTES:
        return False, 'El archivo supera el máximo de 15 MB.', None, None

    tipo = _inferir_tipo_adjunto(request.POST.get('tipo'), nombre)
    return True, nombre, archivo, tipo


def _audit_cliente_adjunto(*, actor_id, action, cliente_pk, field_name, old_value, new_value, reason):
    register_audit_event(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            entity='Cliente',
            entity_id=str(cliente_pk),
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
    )


def guardar_adjunto_cliente(cliente, request):
    """Valida y crea ClienteAdjunto. Retorna (ok, mensaje)."""
    ok, nombre_o_msg, archivo, tipo = validar_archivo_adjunto(request)
    if not ok:
        return False, nombre_o_msg

    adjunto = ClienteAdjunto(
        cliente=cliente,
        tipo=tipo,
        nombre_archivo=nombre_o_msg,
        subido_por=request.user,
    )
    adjunto.archivo.save(nombre_o_msg, archivo, save=True)

    _audit_cliente_adjunto(
        actor_id=request.user.id,
        action='CLIENT_ADJUNTO',
        cliente_pk=cliente.pk,
        field_name='archivo',
        old_value='',
        new_value=nombre_o_msg,
        reason=f'Adjunto {tipo} subido a la ficha',
    )
    return True, f'Adjunto «{nombre_o_msg}» subido.'


def reemplazar_adjunto_cliente(cliente, request):
    """Reemplaza el archivo de un adjunto activo. Retorna (ok, mensaje)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente, eliminado=False).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.'

    ok, nombre_o_msg, archivo, tipo = validar_archivo_adjunto(request)
    if not ok:
        return False, nombre_o_msg

    anterior = adjunto.nombre_archivo
    if adjunto.archivo:
        adjunto.archivo.delete(save=False)
    adjunto.tipo = tipo
    adjunto.nombre_archivo = nombre_o_msg
    adjunto.subido_por = request.user
    adjunto.archivo.save(nombre_o_msg, archivo, save=True)

    _audit_cliente_adjunto(
        actor_id=request.user.id,
        action='CLIENT_ADJUNTO_REPLACE',
        cliente_pk=cliente.pk,
        field_name='archivo',
        old_value=anterior,
        new_value=nombre_o_msg,
        reason='Reemplazo de adjunto en la ficha',
    )
    return True, f'Adjunto reemplazado: «{anterior}» → «{nombre_o_msg}».'


def papelera_adjunto_cliente(cliente, request):
    """Soft-delete: mueve a papelera. Retorna (ok, mensaje)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente, eliminado=False).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.'

    nombre = adjunto.nombre_archivo
    adjunto.eliminado = True
    adjunto.fecha_eliminacion = timezone.now()
    adjunto.eliminado_por = request.user
    adjunto.save(update_fields=['eliminado', 'fecha_eliminacion', 'eliminado_por'])

    _audit_cliente_adjunto(
        actor_id=request.user.id,
        action='CLIENT_ADJUNTO_TRASH',
        cliente_pk=cliente.pk,
        field_name='archivo',
        old_value=nombre,
        new_value='',
        reason=f'Adjunto enviado a papelera: {nombre}',
    )
    return True, f'Adjunto «{nombre}» enviado a papelera. Puedes recuperarlo o borrarlo definitivo.'


def recuperar_adjunto_cliente(cliente, request):
    """Saca un adjunto de la papelera. Retorna (ok, mensaje)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente, eliminado=True).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto en papelera no encontrado.'

    nombre = adjunto.nombre_archivo
    adjunto.eliminado = False
    adjunto.fecha_eliminacion = None
    adjunto.eliminado_por = None
    adjunto.save(update_fields=['eliminado', 'fecha_eliminacion', 'eliminado_por'])

    _audit_cliente_adjunto(
        actor_id=request.user.id,
        action='CLIENT_ADJUNTO_RESTORE',
        cliente_pk=cliente.pk,
        field_name='archivo',
        old_value='',
        new_value=nombre,
        reason=f'Adjunto recuperado de papelera: {nombre}',
    )
    return True, f'Adjunto «{nombre}» recuperado.'


def borrar_definitivo_adjunto_cliente(cliente, request):
    """Borra el archivo del disco y el registro. Solo ADMIN. Retorna (ok, mensaje)."""
    if getattr(request.user, 'rol', None) != 'ADMIN':
        return False, 'Solo un administrador puede borrar adjuntos de forma definitiva.'

    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.'

    nombre = adjunto.nombre_archivo
    if adjunto.archivo:
        adjunto.archivo.delete(save=False)
    adjunto.delete()

    _audit_cliente_adjunto(
        actor_id=request.user.id,
        action='CLIENT_ADJUNTO_PURGE',
        cliente_pk=cliente.pk,
        field_name='archivo',
        old_value=nombre,
        new_value='',
        reason=f'Borrado definitivo de adjunto: {nombre}',
    )
    return True, f'Adjunto «{nombre}» borrado definitivamente del sistema.'


def procesar_accion_adjunto(cliente, request):
    """Despacha la acción POST de adjuntos. Retorna (handled, ok, mensaje)."""
    accion = (request.POST.get('accion') or '').strip()
    if accion not in ACCIONES_ADJUNTO:
        return False, False, ''

    handlers = {
        'subir_adjunto': guardar_adjunto_cliente,
        'reemplazar_adjunto': reemplazar_adjunto_cliente,
        'papelera_adjunto': papelera_adjunto_cliente,
        'recuperar_adjunto': recuperar_adjunto_cliente,
        'borrar_definitivo_adjunto': borrar_definitivo_adjunto_cliente,
    }
    ok, mensaje = handlers[accion](cliente, request)
    return True, ok, mensaje
