"""Servicios para generar y gestionar cargas administrativas."""
from __future__ import annotations

from typing import Any, Dict, List

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from web.services.audit import AuditEvent, register_audit_event

from .models import CargaAdministrativa

ESTADOS_ABIERTOS = ('PENDIENTE', 'EN_PROGRESO')


def _audit(usuario, carga, action, field_name='', old_value='', new_value='', reason=''):
    register_audit_event(
        AuditEvent(
            actor_id=getattr(usuario, 'id', None),
            action=action,
            entity='CargaAdministrativa',
            entity_id=str(carga.pk),
            field_name=field_name or 'estado',
            old_value=old_value,
            new_value=new_value,
            reason=reason or f'Carga #{carga.pk}',
        )
    )


def url_listado_proyecto(proyecto: str) -> str:
    """URL del listado de OT filtrado por proyecto/carga administrativa."""
    from urllib.parse import urlencode

    proyecto = (proyecto or '').strip()
    if not proyecto:
        return ''
    return reverse('ordenes_list') + '?' + urlencode({'proyecto': proyecto})


def crear_carga(
    usuario,
    *,
    titulo: str,
    tipo: str = 'VERIFICACION',
    descripcion: str = '',
    prioridad: str = 'MEDIA',
    asignado_a=None,
    asignado_texto: str = '',
    orden=None,
    cliente=None,
    proyecto: str = '',
    url_referencia: str = '',
) -> CargaAdministrativa:
    tipos = {c[0] for c in CargaAdministrativa.TIPO_CHOICES}
    prioridades = {p[0] for p in CargaAdministrativa.PRIORIDAD_CHOICES}
    if tipo not in tipos:
        tipo = 'OTRO'
    if prioridad not in prioridades:
        prioridad = 'MEDIA'

    proyecto = (proyecto or '').strip()[:255]
    asignado_texto = (asignado_texto or '').strip()[:255]
    url = (url_referencia or '').strip()
    if not url and proyecto:
        url = url_listado_proyecto(proyecto)

    carga = CargaAdministrativa(
        titulo=titulo[:200],
        descripcion=descripcion,
        tipo=tipo,
        prioridad=prioridad,
        creado_por=usuario,
        asignado_a=asignado_a,
        asignado_texto=asignado_texto,
        orden=orden,
        cliente=cliente,
        proyecto=proyecto,
        url_referencia=url[:500],
    )
    if asignado_a or asignado_texto:
        carga.fecha_asignacion = timezone.now()
    carga.save()
    if cliente and proyecto:
        from clientes.proyecto_historial import asignar_proyecto_al_crear_ot
        asignar_proyecto_al_crear_ot(
            cliente,
            proyecto,
            usuario=usuario,
            motivo=f'Carga administrativa #{carga.pk}',
        )
    _audit(
        usuario,
        carga,
        'CARGA_CREATE',
        field_name='titulo',
        new_value=carga.titulo,
        reason=f'Tipo {tipo}' + (f' · Proyecto {proyecto}' if proyecto else ''),
    )
    return carga


def asignar_carga(carga: CargaAdministrativa, usuario_destino, actor) -> CargaAdministrativa:
    anterior = getattr(carga.asignado_a, 'id', '') or ''
    carga.asignado_a = usuario_destino
    carga.asignado_texto = (usuario_destino.nombre_interno or '')[:255]
    carga.fecha_asignacion = timezone.now()
    if carga.estado == 'PENDIENTE':
        carga.estado = 'EN_PROGRESO'
    carga.save(update_fields=[
        'asignado_a', 'asignado_texto', 'fecha_asignacion', 'estado', 'fecha_actualizacion',
    ])
    _audit(
        actor,
        carga,
        'CARGA_ASSIGN',
        field_name='asignado_a',
        old_value=str(anterior),
        new_value=str(usuario_destino.id),
        reason=f'Asignada a {usuario_destino.nombre_interno}',
    )
    return carga


def completar_carga(carga: CargaAdministrativa, actor, observaciones: str = '') -> CargaAdministrativa:
    anterior = carga.estado
    carga.estado = 'COMPLETADA'
    carga.fecha_completada = timezone.now()
    if observaciones:
        carga.observaciones = observaciones
    carga.save(update_fields=['estado', 'fecha_completada', 'observaciones', 'fecha_actualizacion'])
    _audit(
        actor,
        carga,
        'CARGA_COMPLETE',
        old_value=anterior,
        new_value='COMPLETADA',
        reason=observaciones[:200] if observaciones else 'Carga completada',
    )
    # Completar verificación SCi4 también marca el cliente como actualizado
    if carga.tipo == 'VERIFICACION_SCI4' and carga.cliente_id:
        from clientes.sci4 import marcar_sci4_actualizado

        marcar_sci4_actualizado(
            carga.cliente,
            actor_id=getattr(actor, 'id', None),
            reason=f'Carga administrativa #{carga.pk} completada',
        )
    return carga


def cancelar_carga(carga: CargaAdministrativa, actor, motivo: str = '') -> CargaAdministrativa:
    anterior = carga.estado
    carga.estado = 'CANCELADA'
    if motivo:
        carga.observaciones = (carga.observaciones + '\n' if carga.observaciones else '') + motivo
    carga.save(update_fields=['estado', 'observaciones', 'fecha_actualizacion'])
    _audit(
        actor,
        carga,
        'CARGA_CANCEL',
        old_value=anterior,
        new_value='CANCELADA',
        reason=motivo[:200] if motivo else 'Carga cancelada',
    )
    return carga


def eliminar_carga(carga: CargaAdministrativa, actor, motivo: str = '') -> bool:
    """
    Soft-delete de una carga administrativa.
    No borra adjuntos, vínculos ni archivos: solo oculta la carga del listado.
    Returns True si se eliminó ahora; False si ya estaba eliminada.
    """
    if getattr(carga, 'eliminado', False):
        return False

    carga.eliminado = True
    carga.fecha_eliminacion = timezone.now()
    carga.eliminado_por = actor
    update_fields = ['eliminado', 'fecha_eliminacion', 'eliminado_por', 'fecha_actualizacion']
    if motivo:
        nota = f'[Eliminada] {motivo.strip()}'
        carga.observaciones = (carga.observaciones + '\n' if carga.observaciones else '') + nota
        update_fields.append('observaciones')
    carga.save(update_fields=update_fields)

    adjuntos_activos = carga.adjuntos.filter(eliminado=False).count()
    reason = motivo[:200] if motivo else 'Eliminación lógica de carga administrativa'
    if adjuntos_activos:
        reason = f'{reason} (conserva {adjuntos_activos} adjunto(s))'

    _audit(
        actor,
        carga,
        'CARGA_DELETE',
        field_name='eliminado',
        old_value='False',
        new_value='True',
        reason=reason,
    )
    return True


def eliminar_cargas_masivo(ids, actor, motivo: str = '') -> Dict[str, Any]:
    """Elimina (soft) varias cargas. Ignora IDs inexistentes o ya eliminados."""
    eliminadas = 0
    omitidas = 0
    detalle: List[Dict[str, Any]] = []
    qs = CargaAdministrativa.objects.filter(pk__in=list(ids), eliminado=False)
    encontradas = {c.pk: c for c in qs}
    for pk in ids:
        carga = encontradas.get(int(pk)) if str(pk).isdigit() or isinstance(pk, int) else None
        if not carga:
            omitidas += 1
            detalle.append({'id': pk, 'ok': False, 'motivo': 'No encontrada o ya eliminada'})
            continue
        ok = eliminar_carga(carga, actor, motivo=motivo)
        if ok:
            eliminadas += 1
            detalle.append({'id': carga.pk, 'ok': True, 'titulo': carga.titulo})
        else:
            omitidas += 1
            detalle.append({'id': carga.pk, 'ok': False, 'motivo': 'Ya eliminada'})
    return {'eliminadas': eliminadas, 'omitidas': omitidas, 'detalle': detalle}


def generar_desde_pendientes(usuario) -> Dict[str, Any]:
    """
    Crea cargas abiertas a partir de colas operativas existentes,
    sin duplicar si ya hay una carga abierta para la misma OT/cliente+tipo.
    """
    from clientes.models import Cliente
    from ordenes_trabajo.models import OrdenTrabajo, ValidacionComunicacionOT

    creadas: List[CargaAdministrativa] = []
    omitidas = 0

    # OT pendientes de validación administrativa
    ots = (
        OrdenTrabajo.objects.filter(
            eliminado=False,
            estado__in=['PENDIENTE_VALIDACION', 'REALIZADA_PENDIENTE_COMPROBACION'],
        )
        .select_related('cliente', 'tecnico_responsable')
        .order_by('-fecha_creacion')[:200]
    )
    ot_ids_con_carga = set(
        CargaAdministrativa.objects.filter(
            eliminado=False,
            tipo='VALIDACION_OT',
            estado__in=ESTADOS_ABIERTOS,
            orden_id__isnull=False,
        ).values_list('orden_id', flat=True)
    )
    for ot in ots:
        if ot.id in ot_ids_con_carga:
            omitidas += 1
            continue
        cliente_txt = ot.cliente.numero_cliente if ot.cliente_id else 'sin cliente'
        carga = crear_carga(
            usuario,
            titulo=f'Validar OT #{ot.pk} — {ot.titulo[:80]}',
            tipo='VALIDACION_OT',
            descripcion=(
                f'Orden pendiente de validación administrativa.\n'
                f'Cliente: {cliente_txt}\n'
                f'Estado: {ot.get_estado_display()}\n'
                f'Técnico: {ot.tecnico_responsable.nombre_interno if ot.tecnico_responsable_id else "—"}'
            ),
            prioridad='ALTA',
            orden=ot,
            cliente=ot.cliente,
            url_referencia=reverse('orden_detalle', kwargs={'pk': ot.pk}),
        )
        creadas.append(carga)

    # Clientes pendientes SCi4 (base comercial)
    clientes_sci4 = Cliente.objects.filter(activo=True, estado_sci4='PENDIENTE').order_by('-fecha_actualizacion')[:200]
    cli_ids_con_carga = set(
        CargaAdministrativa.objects.filter(
            eliminado=False,
            tipo='VERIFICACION_SCI4',
            estado__in=ESTADOS_ABIERTOS,
            cliente_id__isnull=False,
        ).values_list('cliente_id', flat=True)
    )
    for cli in clientes_sci4:
        if cli.id in cli_ids_con_carga:
            omitidas += 1
            continue
        carga = crear_carga(
            usuario,
            titulo=f'Actualizar SCi4 — cliente {cli.numero_cliente}',
            tipo='VERIFICACION_SCI4',
            descripcion=(
                f'Cliente con cambios pendientes de sincronizar en la base comercial (SCi4).\n'
                f'Nombre: {cli.customer_name or "—"}\n'
                f'Medidor: {cli.meter_serial_n_1 or "—"}\n'
                f'Módem: {cli.modem or "—"}\n'
                f'IP: {cli.ip or "—"}'
            ),
            prioridad='ALTA',
            cliente=cli,
            url_referencia=reverse('cliente_historial', kwargs={'pk': cli.pk}),
        )
        creadas.append(carga)

    # Validaciones de comunicación solicitadas
    sols = (
        ValidacionComunicacionOT.objects.filter(estado='SOLICITADA')
        .select_related('orden', 'orden__cliente', 'solicitado_por')
        .order_by('-fecha_solicitud')[:100]
    )
    ot_com_con_carga = set(
        CargaAdministrativa.objects.filter(
            eliminado=False,
            tipo='COMUNICACION',
            estado__in=ESTADOS_ABIERTOS,
            orden_id__isnull=False,
        ).values_list('orden_id', flat=True)
    )
    for sol in sols:
        if sol.orden_id in ot_com_con_carga:
            omitidas += 1
            continue
        carga = crear_carga(
            usuario,
            titulo=f'Prueba de comunicación — OT #{sol.orden_id}',
            tipo='COMUNICACION',
            descripcion=(
                f'Solicitada por {sol.solicitado_por.nombre_interno if sol.solicitado_por_id else "—"}\n'
                f'{sol.observaciones_solicitud or ""}'
            ),
            prioridad='MEDIA',
            orden=sol.orden,
            cliente=sol.orden.cliente if sol.orden_id else None,
            url_referencia=reverse('orden_detalle', kwargs={'pk': sol.orden_id}) + '#validacion-comunicacion',
        )
        creadas.append(carga)

    return {
        'creadas': len(creadas),
        'omitidas': omitidas,
        'ids': [c.pk for c in creadas],
    }


def contadores_cargas(usuario=None) -> Dict[str, int]:
    qs = CargaAdministrativa.objects.filter(eliminado=False)
    data = {
        'pendientes': qs.filter(estado='PENDIENTE').count(),
        'en_progreso': qs.filter(estado='EN_PROGRESO').count(),
        'sin_asignar': qs.filter(estado__in=ESTADOS_ABIERTOS, asignado_a__isnull=True).count(),
        'completadas': qs.filter(estado='COMPLETADA').count(),
        'abiertas': qs.filter(estado__in=ESTADOS_ABIERTOS).count(),
    }
    if usuario is not None:
        data['mias'] = qs.filter(estado__in=ESTADOS_ABIERTOS, asignado_a=usuario).count()
    return data
