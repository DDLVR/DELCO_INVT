from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from usuarios.models import Usuario
from web.decorators import admin_or_administrativo
from web.services.audit import AuditEvent, register_audit_event

from .models import CargaAdministrativa
from .services import (
    asignar_carga,
    cancelar_carga,
    completar_carga,
    contadores_cargas,
    crear_carga,
    generar_desde_pendientes,
)


PRIORIDAD_ORDER = Case(
    When(prioridad='ALTA', then=Value(3)),
    When(prioridad='MEDIA', then=Value(2)),
    When(prioridad='BAJA', then=Value(1)),
    default=Value(0),
    output_field=IntegerField(),
)


def _administrativos_qs():
    return Usuario.objects.filter(
        rol__in=['ADMIN', 'ADMINISTRATIVO'],
        is_active=True,
    ).order_by('nombre_interno')


@login_required
@admin_or_administrativo
def cargas_hub_view(request):
    contadores = contadores_cargas(request.user)
    mias = (
        CargaAdministrativa.objects.filter(
            estado__in=['PENDIENTE', 'EN_PROGRESO'],
            asignado_a=request.user,
        )
        .select_related('asignado_a', 'orden', 'cliente')
        .annotate(_prio=PRIORIDAD_ORDER)
        .order_by('-_prio', '-fecha_creacion')[:10]
    )
    sin_asignar = (
        CargaAdministrativa.objects.filter(
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


@login_required
@admin_or_administrativo
def cargas_list_view(request):
    qs = (
        CargaAdministrativa.objects.select_related(
            'asignado_a', 'creado_por', 'orden', 'cliente',
        )
        .annotate(_prio=PRIORIDAD_ORDER)
        .order_by('-_prio', '-fecha_creacion')
    )

    estado = (request.GET.get('estado') or '').strip()
    tipo = (request.GET.get('tipo') or '').strip()
    asignado = (request.GET.get('asignado') or '').strip()
    q = (request.GET.get('q') or '').strip()
    vista = (request.GET.get('vista') or '').strip()

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
    if q:
        qs = qs.filter(
            Q(titulo__icontains=q)
            | Q(descripcion__icontains=q)
            | Q(cliente__numero_cliente__icontains=q)
            | Q(orden__titulo__icontains=q)
        )

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page') or 1)

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'cargas/list.html', {
        'page_obj': page,
        'cargas': page.object_list,
        'estados': CargaAdministrativa.ESTADO_CHOICES,
        'tipos': CargaAdministrativa.TIPO_CHOICES,
        'administrativos': _administrativos_qs(),
        'estado_filtro': estado,
        'tipo_filtro': tipo,
        'asignado_filtro': asignado,
        'vista': vista,
        'q': q,
        'query_string': params.urlencode(),
        'contadores': contadores_cargas(request.user),
    })


@login_required
@admin_or_administrativo
def cargas_crear_view(request):
    if request.method == 'POST':
        titulo = (request.POST.get('titulo') or '').strip()
        if not titulo:
            messages.error(request, 'El título es obligatorio.')
            return redirect('cargas_crear')

        asignado_id = (request.POST.get('asignado_a') or '').strip()
        asignado = None
        if asignado_id.isdigit():
            asignado = _administrativos_qs().filter(pk=int(asignado_id)).first()

        carga = crear_carga(
            request.user,
            titulo=titulo,
            tipo=(request.POST.get('tipo') or 'VERIFICACION').strip(),
            descripcion=(request.POST.get('descripcion') or '').strip(),
            prioridad=(request.POST.get('prioridad') or 'MEDIA').strip(),
            asignado_a=asignado,
            url_referencia=(request.POST.get('url_referencia') or '').strip(),
        )
        messages.success(request, f'Carga #{carga.pk} creada.')
        return redirect('cargas_detalle', pk=carga.pk)

    return render(request, 'cargas/crear.html', {
        'tipos': CargaAdministrativa.TIPO_CHOICES,
        'prioridades': CargaAdministrativa.PRIORIDAD_CHOICES,
        'administrativos': _administrativos_qs(),
    })


@login_required
@admin_or_administrativo
def cargas_detalle_view(request, pk):
    carga = get_object_or_404(
        CargaAdministrativa.objects.select_related(
            'asignado_a', 'creado_por', 'orden', 'cliente',
        ),
        pk=pk,
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
                completar_carga(
                    carga,
                    request.user,
                    observaciones=(request.POST.get('observaciones') or '').strip(),
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
            carga.observaciones = (request.POST.get('observaciones') or '').strip()
            carga.save(update_fields=['observaciones', 'fecha_actualizacion'])
            messages.success(request, 'Observaciones guardadas.')
        return redirect('cargas_detalle', pk=pk)

    return render(request, 'cargas/detalle.html', {
        'carga': carga,
        'administrativos': _administrativos_qs(),
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
