from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

from io import BytesIO

from usuarios.models import Usuario
from web.decorators import admin_or_administrativo
from web.services.audit import AuditEvent, register_audit_event

from .import_excel import exportar_cargas_excel, importar_cargas_excel, resumen_importacion
from .models import AdjuntoCarga, CargaAdministrativa
from .services import (
    asignar_carga,
    cancelar_carga,
    completar_carga,
    contadores_cargas,
    crear_carga,
    eliminar_carga,
    eliminar_cargas_masivo,
    generar_desde_pendientes,
)


PRIORIDAD_ORDER = Case(
    When(prioridad='ALTA', then=Value(3)),
    When(prioridad='MEDIA', then=Value(2)),
    When(prioridad='BAJA', then=Value(1)),
    default=Value(0),
    output_field=IntegerField(),
)

MAX_ADJUNTO_BYTES = 15 * 1024 * 1024
EXTENSIONES_IMAGEN = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
EXTENSIONES_PDF = ('.pdf',)
EXTENSIONES_PERMITIDAS = EXTENSIONES_IMAGEN + EXTENSIONES_PDF


def _administrativos_qs():
    return Usuario.objects.filter(
        rol__in=['ADMIN', 'ADMINISTRATIVO'],
        is_active=True,
    ).order_by('nombre_interno')


def _queryset_cargas_filtrado(request, *, aplicar_filtros: bool = True):
    """Base de cargas activas; opcionalmente aplica filtros del listado."""
    qs = (
        CargaAdministrativa.objects.filter(eliminado=False)
        .select_related(
            'asignado_a', 'creado_por', 'orden', 'cliente',
        )
        .annotate(
            _prio=PRIORIDAD_ORDER,
            adjuntos_activos=Count('adjuntos', filter=Q(adjuntos__eliminado=False)),
        )
        .order_by('-_prio', '-fecha_creacion')
    )
    if not aplicar_filtros:
        return qs

    estado = (request.GET.get('estado') or '').strip()
    tipo = (request.GET.get('tipo') or '').strip()
    asignado = (request.GET.get('asignado') or '').strip()
    q = (request.GET.get('q') or '').strip()
    vista = (request.GET.get('vista') or '').strip()
    proyecto = (request.GET.get('proyecto') or '').strip()

    if vista == 'mias':
        qs = qs.filter(asignado_a=request.user, estado__in=['PENDIENTE', 'EN_PROGRESO'])
    elif vista == 'sin_asignar':
        qs = qs.filter(asignado_a__isnull=True, estado__in=['PENDIENTE', 'EN_PROGRESO'])
    elif vista == 'abiertas':
        qs = qs.filter(estado__in=['PENDIENTE', 'EN_PROGRESO'])

    if estado:
        qs = qs.filter(estado=estado)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if asignado == '0':
        qs = qs.filter(asignado_a__isnull=True)
    elif asignado.isdigit():
        qs = qs.filter(asignado_a_id=int(asignado))
    if proyecto:
        qs = qs.filter(proyecto__iexact=proyecto)
    if q:
        qs = qs.filter(
            Q(titulo__icontains=q)
            | Q(descripcion__icontains=q)
            | Q(proyecto__icontains=q)
            | Q(cliente__numero_cliente__icontains=q)
            | Q(orden__titulo__icontains=q)
        )
    return qs


def _inferir_tipo_adjunto(tipo_post, nombre):
    """Alinea tipo con la extensión real del archivo (evita FOTO+PDF)."""
    lower = (nombre or '').lower()
    es_img = lower.endswith(EXTENSIONES_IMAGEN)
    es_pdf = lower.endswith(EXTENSIONES_PDF)
    tipo = (tipo_post or '').strip().upper()

    if es_pdf:
        if tipo == 'MOREAPP':
            return 'MOREAPP'
        return 'PDF'
    if es_img:
        if tipo == 'MOREAPP':
            # captura de pantalla marcada como MoreApp: guardar como FOTO
            return 'FOTO'
        if tipo in ('FOTO', 'OTRO'):
            return tipo
        return 'FOTO'
    if tipo in dict(AdjuntoCarga.TIPO_CHOICES):
        return tipo
    return 'OTRO'


def _validar_archivo_adjunto(request):
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


def _guardar_adjunto_carga(carga, request):
    """Valida y crea AdjuntoCarga. Retorna (ok, mensaje)."""
    # Admin/administrativo pueden corregir adjuntos también en cargas completadas
    ok, nombre_o_msg, archivo, tipo = _validar_archivo_adjunto(request)
    if not ok:
        return False, nombre_o_msg

    adjunto = AdjuntoCarga(
        carga=carga,
        tipo=tipo,
        nombre_archivo=nombre_o_msg,
        subido_por=request.user,
    )
    adjunto.archivo.save(nombre_o_msg, archivo, save=True)

    register_audit_event(
        AuditEvent(
            actor_id=request.user.id,
            action='CARGA_ADJUNTO',
            entity='AdjuntoCarga',
            entity_id=str(adjunto.pk),
            field_name='archivo',
            old_value='',
            new_value=nombre_o_msg,
            reason=f'Adjunto {tipo} en carga #{carga.pk}',
        )
    )
    return True, f'Adjunto «{nombre_o_msg}» subido.'


def _reemplazar_adjunto_carga(carga, request):
    """Reemplaza el archivo de un adjunto activo. Retorna (ok, mensaje)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        AdjuntoCarga.objects.filter(pk=int(adj_id), carga=carga, eliminado=False).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.'

    ok, nombre_o_msg, archivo, tipo = _validar_archivo_adjunto(request)
    if not ok:
        return False, nombre_o_msg

    anterior = adjunto.nombre_archivo
    if adjunto.archivo:
        adjunto.archivo.delete(save=False)
    adjunto.tipo = tipo
    adjunto.nombre_archivo = nombre_o_msg
    adjunto.subido_por = request.user
    adjunto.archivo.save(nombre_o_msg, archivo, save=True)

    register_audit_event(
        AuditEvent(
            actor_id=request.user.id,
            action='CARGA_ADJUNTO_REPLACE',
            entity='AdjuntoCarga',
            entity_id=str(adjunto.pk),
            field_name='archivo',
            old_value=anterior,
            new_value=nombre_o_msg,
            reason=f'Reemplazo en carga #{carga.pk}',
        )
    )
    return True, f'Adjunto reemplazado: «{anterior}» → «{nombre_o_msg}».'


def _papelera_adjunto(carga, request):
    """Soft-delete: mueve a papelera. Retorna (ok, mensaje)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        AdjuntoCarga.objects.filter(pk=int(adj_id), carga=carga, eliminado=False).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.'

    nombre = adjunto.nombre_archivo
    adjunto.eliminado = True
    adjunto.fecha_eliminacion = timezone.now()
    adjunto.eliminado_por = request.user
    adjunto.save(update_fields=['eliminado', 'fecha_eliminacion', 'eliminado_por'])

    register_audit_event(
        AuditEvent(
            actor_id=request.user.id,
            action='CARGA_ADJUNTO_TRASH',
            entity='AdjuntoCarga',
            entity_id=str(adjunto.pk),
            field_name='eliminado',
            old_value='False',
            new_value='True',
            reason=f'Papelera carga #{carga.pk}: {nombre}',
        )
    )
    return True, f'Adjunto «{nombre}» enviado a papelera. Puedes recuperarlo o borrarlo definitivo.'


def _recuperar_adjunto(carga, request):
    """Saca un adjunto de la papelera. Retorna (ok, mensaje)."""
    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        AdjuntoCarga.objects.filter(pk=int(adj_id), carga=carga, eliminado=True).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto en papelera no encontrado.'

    nombre = adjunto.nombre_archivo
    adjunto.eliminado = False
    adjunto.fecha_eliminacion = None
    adjunto.eliminado_por = None
    adjunto.save(update_fields=['eliminado', 'fecha_eliminacion', 'eliminado_por'])

    register_audit_event(
        AuditEvent(
            actor_id=request.user.id,
            action='CARGA_ADJUNTO_RESTORE',
            entity='AdjuntoCarga',
            entity_id=str(adjunto.pk),
            field_name='eliminado',
            old_value='True',
            new_value='False',
            reason=f'Recuperado en carga #{carga.pk}: {nombre}',
        )
    )
    return True, f'Adjunto «{nombre}» recuperado.'


def _borrar_definitivo_adjunto(carga, request):
    """Borra el archivo del disco y el registro. Solo ADMIN. Retorna (ok, mensaje)."""
    if request.user.rol != 'ADMIN':
        return False, 'Solo un administrador puede borrar adjuntos de forma definitiva.'

    adj_id = (request.POST.get('adjunto_id') or '').strip()
    adjunto = (
        AdjuntoCarga.objects.filter(pk=int(adj_id), carga=carga).first()
        if adj_id.isdigit() else None
    )
    if not adjunto:
        return False, 'Adjunto no encontrado.'

    nombre = adjunto.nombre_archivo
    if adjunto.archivo:
        adjunto.archivo.delete(save=False)
    pk = adjunto.pk
    adjunto.delete()

    register_audit_event(
        AuditEvent(
            actor_id=request.user.id,
            action='CARGA_ADJUNTO_PURGE',
            entity='AdjuntoCarga',
            entity_id=str(pk),
            field_name='archivo',
            old_value=nombre,
            new_value='',
            reason=f'Borrado definitivo carga #{carga.pk}',
        )
    )
    return True, f'Adjunto «{nombre}» borrado definitivamente del sistema.'


@login_required
@admin_or_administrativo
def cargas_hub_view(request):
    contadores = contadores_cargas(request.user)
    mias = (
        CargaAdministrativa.objects.filter(
            eliminado=False,
            estado__in=['PENDIENTE', 'EN_PROGRESO'],
            asignado_a=request.user,
        )
        .select_related('asignado_a', 'orden', 'cliente')
        .annotate(_prio=PRIORIDAD_ORDER)
        .order_by('-_prio', '-fecha_creacion')[:10]
    )
    sin_asignar = (
        CargaAdministrativa.objects.filter(
            eliminado=False,
            estado__in=['PENDIENTE', 'EN_PROGRESO'],
            asignado_a__isnull=True,
        )
        .select_related('orden', 'cliente', 'creado_por')
        .annotate(_prio=PRIORIDAD_ORDER)
        .order_by('-_prio', '-fecha_creacion')[:10]
    )
    return render(request, 'cargas/hub.html', {
        'contadores': contadores,
        'mias': mias,
        'sin_asignar': sin_asignar,
        'colas_rapidas': [
            {
                'label': 'OT por validar',
                'url': reverse('ordenes_list') + '?cola=validar',
                'icon': 'bi-clipboard-check',
            },
            {
                'label': 'Pendientes SCi4',
                'url': reverse('clientes_list') + '?alarma=pendiente_sci4',
                'icon': 'bi-cloud-arrow-up',
            },
            {
                'label': 'Pendientes MoreApp',
                'url': reverse('pendientes_operativos'),
                'icon': 'bi-list-check',
            },
        ],
    })


def _proyectos_disponibles_cargas():
    """Nombres de proyecto usados en cargas (+ catálogo si existe)."""
    nombres = list(
        CargaAdministrativa.objects.filter(eliminado=False)
        .exclude(proyecto='')
        .values_list('proyecto', flat=True)
        .distinct()
        .order_by('proyecto')[:120]
    )
    try:
        from catalogos.models import Proyecto
        for n in Proyecto.objects.filter(activo=True).values_list('nombre', flat=True)[:80]:
            if n and n not in nombres:
                nombres.append(n)
    except Exception:
        pass
    return sorted({(n or '').strip() for n in nombres if (n or '').strip()}, key=lambda x: x.casefold())


@login_required
@admin_or_administrativo
def cargas_list_view(request):
    qs = _queryset_cargas_filtrado(request, aplicar_filtros=True)

    estado = (request.GET.get('estado') or '').strip()
    tipo = (request.GET.get('tipo') or '').strip()
    asignado = (request.GET.get('asignado') or '').strip()
    q = (request.GET.get('q') or '').strip()
    vista = (request.GET.get('vista') or '').strip()
    proyecto = (request.GET.get('proyecto') or '').strip()

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page') or 1)

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'cargas/list.html', {
        'page_obj': page,
        'cargas': page.object_list,
        'estados': CargaAdministrativa.ESTADO_CHOICES,
        'tipos': CargaAdministrativa.TIPO_CHOICES,
        'prioridades': CargaAdministrativa.PRIORIDAD_CHOICES,
        'administrativos': _administrativos_qs(),
        'proyectos_disponibles': _proyectos_disponibles_cargas(),
        'estado_filtro': estado,
        'tipo_filtro': tipo,
        'asignado_filtro': asignado,
        'proyecto_filtro': proyecto,
        'vista': vista,
        'q': q,
        'query_string': params.urlencode(),
        'contadores': contadores_cargas(request.user),
        'abrir_modal_nueva': (request.GET.get('nueva') or '') == '1',
    })


@login_required
@admin_or_administrativo
def cargas_exportar_view(request):
    """Exporta cargas administrativas (filtradas por defecto; ?todas=1 sin filtros)."""
    filter_keys = ('estado', 'tipo', 'asignado', 'q', 'vista', 'proyecto')
    tiene_filtros = any((request.GET.get(k) or '').strip() for k in filter_keys)
    forzar_filtrar = request.GET.get('filtrar') == '1'
    exportar_todas = request.GET.get('todas') == '1'
    usar_filtros = (not exportar_todas) and (forzar_filtrar or tiene_filtros)

    qs = _queryset_cargas_filtrado(request, aplicar_filtros=usar_filtros)
    wb = exportar_cargas_excel(list(qs))

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    from web.services.export_filenames import nombre_exportacion_con_fecha
    filename = nombre_exportacion_con_fecha('cargas_administrativas.xlsx')
    response = HttpResponse(
        stream.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@admin_or_administrativo
def cargas_crear_view(request):
    """
    Crear OT administrativa.
    - GET: redirige al listado abriendo el popup (?nueva=1).
    - POST: título = número de cliente (obligatorio desde padrón); no inventa título libre.
    """
    from clientes.models import Cliente

    def _quiere_json():
        return (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in (request.headers.get('Accept') or '')
        )

    if request.method != 'POST':
        return redirect(reverse('cargas_list') + '?nueva=1')

    cliente_id = (request.POST.get('cliente_id') or '').strip()
    cliente = None
    if cliente_id.isdigit():
        cliente = Cliente.objects.filter(pk=int(cliente_id), activo=True).first()

    if not cliente:
        # Fallback: título enviado como nº cliente (compat)
        numero = (request.POST.get('titulo') or request.POST.get('numero_cliente') or '').strip()
        if numero:
            cliente = Cliente.objects.filter(numero_cliente__iexact=numero, activo=True).first()

    if not cliente:
        msg = 'Debes seleccionar un cliente existente de la base de datos. Si no aparece, créalo primero.'
        if _quiere_json():
            return JsonResponse({'success': False, 'message': msg}, status=400)
        messages.error(request, msg)
        return redirect(reverse('cargas_list') + '?nueva=1')

    titulo = (cliente.numero_cliente or '').strip()
    if not titulo:
        msg = 'El cliente seleccionado no tiene número de cliente válido.'
        if _quiere_json():
            return JsonResponse({'success': False, 'message': msg}, status=400)
        messages.error(request, msg)
        return redirect(reverse('cargas_list') + '?nueva=1')

    asignado_id = (request.POST.get('asignado_a') or '').strip()
    asignado = None
    if asignado_id.isdigit():
        asignado = _administrativos_qs().filter(pk=int(asignado_id)).first()

    carga = crear_carga(
        request.user,
        titulo=titulo[:200],
        tipo=(request.POST.get('tipo') or 'VERIFICACION').strip(),
        descripcion=(request.POST.get('descripcion') or '').strip(),
        prioridad=(request.POST.get('prioridad') or 'MEDIA').strip(),
        asignado_a=asignado,
        cliente=cliente,
        proyecto=(request.POST.get('proyecto') or '').strip(),
        url_referencia=(request.POST.get('url_referencia') or '').strip(),
    )
    ok_msg = f'ID {carga.pk} creada · cliente {titulo}.'
    if _quiere_json():
        return JsonResponse({
            'success': True,
            'message': ok_msg,
            'id': carga.pk,
            'redirect': reverse('cargas_detalle', kwargs={'pk': carga.pk}),
        })
    messages.success(request, ok_msg)
    return redirect('cargas_detalle', pk=carga.pk)


@login_required
@admin_or_administrativo
def cargas_detalle_view(request, pk):
    carga = get_object_or_404(
        CargaAdministrativa.objects.select_related(
            'asignado_a', 'creado_por', 'orden', 'cliente',
        ).prefetch_related('adjuntos'),
        pk=pk,
        eliminado=False,
    )

    if request.method == 'POST':
        accion = (request.POST.get('accion') or '').strip()
        if accion == 'asignar':
            dest_id = (request.POST.get('asignado_a') or '').strip()
            dest = _administrativos_qs().filter(pk=int(dest_id)).first() if dest_id.isdigit() else None
            if not dest:
                messages.error(request, 'Selecciona un administrativo válido.')
            else:
                asignar_carga(carga, dest, request.user)
                messages.success(request, f'Carga asignada a {dest.nombre_interno}.')
        elif accion == 'tomar':
            asignar_carga(carga, request.user, request.user)
            messages.success(request, 'Te asignaste esta carga.')
        elif accion == 'en_progreso':
            if carga.estado == 'PENDIENTE':
                carga.estado = 'EN_PROGRESO'
                if not carga.asignado_a_id:
                    carga.asignado_a = request.user
                    carga.fecha_asignacion = timezone.now()
                carga.save()
                register_audit_event(
                    AuditEvent(
                        actor_id=request.user.id,
                        action='CARGA_UPDATE',
                        entity='CargaAdministrativa',
                        entity_id=str(carga.pk),
                        field_name='estado',
                        old_value='PENDIENTE',
                        new_value='EN_PROGRESO',
                        reason='Marcada en progreso',
                    )
                )
                messages.success(request, 'Carga en progreso.')
        elif accion == 'completar':
            if not carga.abierta:
                messages.error(request, 'La carga ya no está abierta.')
            else:
                from ordenes_trabajo.observaciones_html import sanitizar_observaciones_html

                completar_carga(
                    carga,
                    request.user,
                    observaciones=sanitizar_observaciones_html(
                        request.POST.get('observaciones') or ''
                    ),
                )
                messages.success(request, 'Carga marcada como completada.')
        elif accion == 'cancelar':
            if not carga.abierta:
                messages.error(request, 'La carga ya no está abierta.')
            else:
                cancelar_carga(
                    carga,
                    request.user,
                    motivo=(request.POST.get('motivo') or '').strip(),
                )
                messages.warning(request, 'Carga cancelada.')
        elif accion == 'guardar_obs':
            from ordenes_trabajo.observaciones_html import sanitizar_observaciones_html

            # Se puede corregir observaciones también después de completar
            carga.observaciones = sanitizar_observaciones_html(
                request.POST.get('observaciones') or ''
            )
            carga.save(update_fields=['observaciones', 'fecha_actualizacion'])
            register_audit_event(
                AuditEvent(
                    actor_id=request.user.id,
                    action='CARGA_UPDATE',
                    entity='CargaAdministrativa',
                    entity_id=str(carga.pk),
                    field_name='observaciones',
                    old_value='',
                    new_value=carga.observaciones[:200],
                    reason=(
                        'Observaciones actualizadas'
                        + ('' if carga.abierta else ' (carga cerrada)')
                    ),
                )
            )
            messages.success(request, 'Observaciones guardadas.')
        elif accion == 'reabrir':
            if carga.estado not in ('COMPLETADA', 'CANCELADA'):
                messages.info(request, 'La carga ya está abierta.')
            else:
                anterior = carga.estado
                carga.estado = 'EN_PROGRESO'
                carga.fecha_completada = None
                if not carga.asignado_a_id:
                    carga.asignado_a = request.user
                    carga.fecha_asignacion = timezone.now()
                carga.save(update_fields=[
                    'estado', 'fecha_completada', 'asignado_a',
                    'fecha_asignacion', 'fecha_actualizacion',
                ])
                register_audit_event(
                    AuditEvent(
                        actor_id=request.user.id,
                        action='CARGA_UPDATE',
                        entity='CargaAdministrativa',
                        entity_id=str(carga.pk),
                        field_name='estado',
                        old_value=anterior,
                        new_value='EN_PROGRESO',
                        reason='Carga reabierta para corrección',
                    )
                )
                messages.success(request, 'Carga reabierta en progreso. Puedes seguir editando.')
        elif accion == 'subir_adjunto':
            ok, msg = _guardar_adjunto_carga(carga, request)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
        elif accion == 'reemplazar_adjunto':
            ok, msg = _reemplazar_adjunto_carga(carga, request)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
        elif accion == 'papelera_adjunto':
            ok, msg = _papelera_adjunto(carga, request)
            if ok:
                messages.warning(request, msg)
            else:
                messages.error(request, msg)
        elif accion == 'recuperar_adjunto':
            ok, msg = _recuperar_adjunto(carga, request)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
        elif accion == 'borrar_definitivo_adjunto':
            ok, msg = _borrar_definitivo_adjunto(carga, request)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
        elif accion == 'eliminar_adjunto':
            # Compatibilidad: mismo flujo que papelera
            ok, msg = _papelera_adjunto(carga, request)
            if ok:
                messages.warning(request, msg)
            else:
                messages.error(request, msg)
        return redirect('cargas_detalle', pk=pk)

    adjuntos = list(carga.adjuntos.filter(eliminado=False))
    adjuntos_papelera = list(
        carga.adjuntos.filter(eliminado=True).select_related('eliminado_por')
    )
    es_admin = request.user.rol == 'ADMIN'

    return render(request, 'cargas/detalle.html', {
        'carga': carga,
        'adjuntos': adjuntos,
        'adjuntos_papelera': adjuntos_papelera,
        'tipos_adjunto': AdjuntoCarga.TIPO_CHOICES,
        'administrativos': _administrativos_qs(),
        'puede_gestionar_adjuntos': True,
        'puede_editar_contenido': True,
        'puede_borrar_definitivo': es_admin,
    })


@login_required
@admin_or_administrativo
@require_POST
def cargas_generar_pendientes_view(request):
    result = generar_desde_pendientes(request.user)
    if result['creadas']:
        messages.success(
            request,
            f'Se generaron {result["creadas"]} cargas desde las colas pendientes'
            + (f' ({result["omitidas"]} ya existían).' if result['omitidas'] else '.'),
        )
    else:
        messages.info(
            request,
            'No hay pendientes nuevos para generar'
            + (f' ({result["omitidas"]} ya tenían carga abierta).' if result['omitidas'] else '.'),
        )
    return redirect('cargas_list')


@login_required
@admin_or_administrativo
@require_POST
def cargas_importar_view(request):
    """Importación masiva de órdenes de trabajo administrativas desde Excel."""
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'success': False, 'message': 'No se seleccionó ningún archivo'})

    try:
        importacion = importar_cargas_excel(archivo, request.user)
        conteos = resumen_importacion(importacion)
        errores_resumen = []
        if importacion.fallidas > 0:
            from collections import Counter
            errores = importacion.errores.all()[:100]
            for motivo, count in Counter(e.motivo for e in errores).most_common(8):
                errores_resumen.append({'motivo': motivo[:200], 'count': count})

        mensaje = importacion.observaciones or 'Importación finalizada.'
        # Quitar línea meta interna del mensaje al usuario
        mensaje = '\n'.join(
            line for line in mensaje.splitlines() if not line.startswith('[meta]')
        ).strip()

        return JsonResponse({
            'success': importacion.estado == 'COMPLETADO',
            'message': mensaje,
            'exitosas': importacion.exitosas,
            'fallidas': conteos['errores'],
            'duplicados': conteos['duplicados'],
            'total_filas': importacion.total_filas,
            'importacion_id': importacion.id,
            'errores_resumen': errores_resumen,
            'estado': importacion.estado,
            'errores_url': (
                reverse('importacion_errores', kwargs={'pk': importacion.id})
                if importacion.fallidas else ''
            ),
        })
    except Exception as exc:
        return JsonResponse({
            'success': False,
            'message': str(exc),
            'exitosas': 0,
            'fallidas': 0,
            'duplicados': 0,
        })


@login_required
@admin_or_administrativo
@require_POST
def cargas_eliminar_view(request, pk):
    """Soft-delete individual de una orden de trabajo administrativa."""
    carga = get_object_or_404(CargaAdministrativa, pk=pk, eliminado=False)
    carga_id = carga.pk
    titulo = carga.titulo
    n_adjuntos = carga.adjuntos.filter(eliminado=False).count()
    motivo = (request.POST.get('motivo') or '').strip()

    ok = eliminar_carga(carga, request.user, motivo=motivo)
    if ok:
        extra = (
            f' Se conservaron {n_adjuntos} adjunto(s) asociados.'
            if n_adjuntos else ''
        )
        messages.success(
            request,
            f'Orden de trabajo administrativa #{carga_id} («{titulo}») eliminada.{extra}',
        )
    else:
        messages.warning(request, f'La carga #{carga_id} ya estaba eliminada.')
    return redirect('cargas_list')


@login_required
@admin_or_administrativo
@require_POST
def cargas_eliminar_masivo_view(request):
    """Soft-delete masivo de órdenes de trabajo administrativas."""
    ids_raw = request.POST.getlist('ids') or request.POST.getlist('carga_ids')
    if not ids_raw and request.POST.get('ids'):
        ids_raw = [x.strip() for x in request.POST.get('ids').split(',') if x.strip()]

    ids = []
    for raw in ids_raw:
        if str(raw).isdigit():
            ids.append(int(raw))

    if not ids:
        messages.error(request, 'No se seleccionaron órdenes para eliminar.')
        return redirect('cargas_list')

    motivo = (request.POST.get('motivo') or '').strip()
    result = eliminar_cargas_masivo(ids, request.user, motivo=motivo)
    if result['eliminadas']:
        messages.success(
            request,
            f'Se eliminaron {result["eliminadas"]} orden(es) de trabajo administrativa(s)'
            + (f' ({result["omitidas"]} omitidas).' if result['omitidas'] else '.'),
        )
    else:
        messages.warning(
            request,
            'No se eliminó ninguna orden'
            + (f' ({result["omitidas"]} omitidas).' if result['omitidas'] else '.'),
        )
    return redirect('cargas_list')
    return redirect('cargas_list')


@login_required
@admin_or_administrativo
def cargas_pdf_view(request, pk):
    """Descarga PDF con datos e observaciones de la carga administrativa."""
    from .pdf_carga import generar_pdf_carga_administrativa, nombre_archivo_pdf_carga

    carga = get_object_or_404(
        CargaAdministrativa.objects.select_related(
            'asignado_a', 'creado_por', 'orden', 'cliente',
        ).prefetch_related('adjuntos'),
        pk=pk,
        eliminado=False,
    )
    pdf_bytes = generar_pdf_carga_administrativa(carga)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format(
        nombre_archivo_pdf_carga(carga)
    )
    return response
