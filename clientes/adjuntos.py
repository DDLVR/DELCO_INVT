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


def _validar_archivo(archivo, tipo_post):
    """Valida un UploadedFile. Retorna (ok, mensaje_o_nombre, archivo, tipo)."""
    if not archivo:
        return False, 'Debes seleccionar un archivo.', None, None

    nombre = get_valid_filename(archivo.name or 'adjunto')
    lower = nombre.lower()
    if not lower.endswith(EXTENSIONES_PERMITIDAS):
        return False, f'«{nombre}»: solo se permiten imágenes (jpg, png, webp, gif) o PDF.', None, None

    size = getattr(archivo, 'size', None) or 0
    if size <= 0:
        return False, f'«{nombre}»: el archivo está vacío.', None, None
    if size > MAX_ADJUNTO_BYTES:
        return False, f'«{nombre}»: supera el máximo de 15 MB.', None, None

    tipo = _inferir_tipo_adjunto(tipo_post, nombre)
    return True, nombre, archivo, tipo


def validar_archivo_adjunto(request):
    """Valida el primer archivo subido (compat). Retorna (ok, mensaje_o_nombre, archivo, tipo)."""
    archivo = request.FILES.get('archivo')
    if not archivo:
        archivos = request.FILES.getlist('archivos')
        archivo = archivos[0] if archivos else None
    return _validar_archivo(archivo, request.POST.get('tipo'))


def _listar_archivos_request(request):
    """Obtiene la lista de archivos desde `archivo` (single/multi) o `archivos`."""
    archivos = list(request.FILES.getlist('archivo'))
    if not archivos:
        archivos = list(request.FILES.getlist('archivos'))
    # Deduplicar por identidad de objeto por si el browser envía ambos nombres
    vistos = set()
    unicos = []
    for f in archivos:
        key = id(f)
        if key in vistos:
            continue
        vistos.add(key)
        unicos.append(f)
    return unicos


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


def _crear_adjunto_desde_archivo(cliente, request, archivo, tipo_post):
    """Crea un ClienteAdjunto. Retorna dict {ok, nombre, message, tipo}."""
    ok, nombre_o_msg, archivo_ok, tipo = _validar_archivo(archivo, tipo_post)
    if not ok:
        return {
            'ok': False,
            'nombre': getattr(archivo, 'name', '') or '',
            'message': nombre_o_msg,
            'tipo': '',
        }

    try:
        adjunto = ClienteAdjunto(
            cliente=cliente,
            tipo=tipo,
            nombre_archivo=nombre_o_msg,
            subido_por=request.user,
        )
        adjunto.archivo.save(nombre_o_msg, archivo_ok, save=True)
    except Exception as exc:  # noqa: BLE001 — devolver estado usable en popup
        return {
            'ok': False,
            'nombre': nombre_o_msg,
            'message': f'Error al guardar «{nombre_o_msg}»: {exc}',
            'tipo': tipo,
        }

    _audit_cliente_adjunto(
        actor_id=request.user.id,
        action='CLIENT_ADJUNTO',
        cliente_pk=cliente.pk,
        field_name='archivo',
        old_value='',
        new_value=nombre_o_msg,
        reason=f'Adjunto {tipo} subido a la ficha',
    )
    return {
        'ok': True,
        'nombre': nombre_o_msg,
        'message': f'Adjunto «{nombre_o_msg}» subido.',
        'tipo': tipo,
        'id': adjunto.pk,
    }


def guardar_adjunto_cliente(cliente, request):
    """Valida y crea uno o varios ClienteAdjunto. Retorna (ok, mensaje, resultados)."""
    archivos = _listar_archivos_request(request)
    if not archivos:
        return False, 'Debes seleccionar al menos un archivo.', []

    tipo_post = request.POST.get('tipo')
    resultados = [
        _crear_adjunto_desde_archivo(cliente, request, archivo, tipo_post)
        for archivo in archivos
    ]
    ok_count = sum(1 for r in resultados if r.get('ok'))
    fail_count = len(resultados) - ok_count

    if ok_count and not fail_count:
        if ok_count == 1:
            return True, resultados[0]['message'], resultados
        return True, f'{ok_count} archivos subidos correctamente.', resultados
    if ok_count and fail_count:
        return (
            True,
            f'{ok_count} subido(s), {fail_count} con error. Revisa el detalle.',
            resultados,
        )
    # Todos fallaron
    if len(resultados) == 1:
        return False, resultados[0]['message'], resultados
    return False, f'No se pudo subir ningún archivo ({fail_count} error(es)).', resultados


def reemplazar_adjunto_cliente(cliente, request):
    """Reemplaza el archivo de un adjunto activo. Retorna (ok, mensaje, resultados)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente, eliminado=False).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.', []

    ok, nombre_o_msg, archivo, tipo = validar_archivo_adjunto(request)
    if not ok:
        return False, nombre_o_msg, [{
            'ok': False,
            'nombre': '',
            'message': nombre_o_msg,
        }]

    anterior = adjunto.nombre_archivo
    try:
        if adjunto.archivo:
            adjunto.archivo.delete(save=False)
        adjunto.tipo = tipo
        adjunto.nombre_archivo = nombre_o_msg
        adjunto.subido_por = request.user
        adjunto.archivo.save(nombre_o_msg, archivo, save=True)
    except Exception as exc:  # noqa: BLE001
        msg = f'Error al reemplazar «{anterior}»: {exc}'
        return False, msg, [{'ok': False, 'nombre': anterior, 'message': msg}]

    _audit_cliente_adjunto(
        actor_id=request.user.id,
        action='CLIENT_ADJUNTO_REPLACE',
        cliente_pk=cliente.pk,
        field_name='archivo',
        old_value=anterior,
        new_value=nombre_o_msg,
        reason='Reemplazo de adjunto en la ficha',
    )
    msg = f'Adjunto reemplazado: «{anterior}» → «{nombre_o_msg}».'
    return True, msg, [{'ok': True, 'nombre': nombre_o_msg, 'message': msg, 'tipo': tipo}]


def papelera_adjunto_cliente(cliente, request):
    """Soft-delete: mueve a papelera. Retorna (ok, mensaje, resultados)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente, eliminado=False).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.', []

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
    msg = f'Adjunto «{nombre}» enviado a papelera. Puedes recuperarlo o borrarlo definitivo.'
    return True, msg, [{'ok': True, 'nombre': nombre, 'message': msg}]


def recuperar_adjunto_cliente(cliente, request):
    """Saca un adjunto de la papelera. Retorna (ok, mensaje, resultados)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente, eliminado=True).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto en papelera no encontrado.', []

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
    msg = f'Adjunto «{nombre}» recuperado.'
    return True, msg, [{'ok': True, 'nombre': nombre, 'message': msg}]


def borrar_definitivo_adjunto_cliente(cliente, request):
    """Borra el archivo del disco y el registro. Solo ADMIN. Retorna (ok, mensaje, resultados)."""
    if getattr(request.user, 'rol', None) != 'ADMIN':
        return False, 'Solo un administrador puede borrar adjuntos de forma definitiva.', []

    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        ClienteAdjunto.objects.filter(pk=int(adj_id), cliente=cliente).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.', []

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
    msg = f'Adjunto «{nombre}» borrado definitivamente del sistema.'
    return True, msg, [{'ok': True, 'nombre': nombre, 'message': msg}]


def procesar_accion_adjunto(cliente, request):
    """Despacha la acción POST de adjuntos. Retorna (handled, ok, mensaje, resultados)."""
    accion = (request.POST.get('accion') or '').strip()
    if accion not in ACCIONES_ADJUNTO:
        return False, False, '', []

    handlers = {
        'subir_adjunto': guardar_adjunto_cliente,
        'reemplazar_adjunto': reemplazar_adjunto_cliente,
        'papelera_adjunto': papelera_adjunto_cliente,
        'recuperar_adjunto': recuperar_adjunto_cliente,
        'borrar_definitivo_adjunto': borrar_definitivo_adjunto_cliente,
    }
    ok, mensaje, resultados = handlers[accion](cliente, request)
    return True, ok, mensaje, resultados
