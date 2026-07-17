from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from web.decorators import admin_only
from web.services.audit import AuditEvent, register_audit_event

from .models import TicketSoporte


@login_required
@admin_only
def soporte_hub_view(request):
    """Hub llamativo de soporte — solo administradores."""
    tickets = TicketSoporte.objects.select_related('creado_por').order_by('-fecha_creacion')[:12]
    contadores = TicketSoporte.objects.aggregate(
        total=Count('id'),
        abiertos=Count('id', filter=Q(estado='ABIERTO')),
        en_revision=Count('id', filter=Q(estado='EN_REVISION')),
        criticos=Count('id', filter=Q(prioridad='CRITICA', estado__in=['ABIERTO', 'EN_REVISION'])),
    )
    return render(request, 'soporte/hub.html', {
        'tickets_recientes': tickets,
        'contadores': contadores,
    })


@login_required
@admin_only
def soporte_list_view(request):
    estado = request.GET.get('estado', '').strip()
    prioridad = request.GET.get('prioridad', '').strip()
    q = request.GET.get('q', '').strip()

    tickets = TicketSoporte.objects.select_related('creado_por', 'actualizado_por')
    if estado:
        tickets = tickets.filter(estado=estado)
    if prioridad:
        tickets = tickets.filter(prioridad=prioridad)
    if q:
        tickets = tickets.filter(
            Q(titulo__icontains=q) | Q(descripcion__icontains=q) | Q(pagina_url__icontains=q)
        )

    return render(request, 'soporte/list.html', {
        'tickets': tickets.order_by('-fecha_creacion')[:200],
        'estado_filtro': estado,
        'prioridad_filtro': prioridad,
        'q': q,
        'estados': TicketSoporte.ESTADO_CHOICES,
        'prioridades': TicketSoporte.PRIORIDAD_CHOICES,
    })


@login_required
@admin_only
@require_http_methods(['GET', 'POST'])
def soporte_crear_view(request):
    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        categoria = request.POST.get('categoria', 'BUG').strip()
        prioridad = request.POST.get('prioridad', 'MEDIA').strip()
        pagina_url = request.POST.get('pagina_url', '').strip()

        categorias = {c[0] for c in TicketSoporte.CATEGORIA_CHOICES}
        prioridades = {p[0] for p in TicketSoporte.PRIORIDAD_CHOICES}
        if categoria not in categorias:
            categoria = 'BUG'
        if prioridad not in prioridades:
            prioridad = 'MEDIA'

        if not titulo or not descripcion:
            messages.error(request, 'Título y descripción son obligatorios.')
            return redirect('soporte_crear')

        ticket = TicketSoporte.objects.create(
            titulo=titulo,
            descripcion=descripcion,
            categoria=categoria,
            prioridad=prioridad,
            pagina_url=pagina_url,
            creado_por=request.user,
            actualizado_por=request.user,
        )
        register_audit_event(
            AuditEvent(
                actor_id=request.user.id,
                action='SUPPORT_TICKET_CREATE',
                entity='TicketSoporte',
                entity_id=str(ticket.pk),
                field_name='titulo',
                old_value=None,
                new_value=titulo,
                reason=f'Ticket {categoria}/{prioridad}',
            )
        )
        messages.success(request, f'Ticket #{ticket.pk} creado correctamente.')
        return redirect('soporte_detalle', pk=ticket.pk)

    return render(request, 'soporte/crear.html', {
        'categorias': TicketSoporte.CATEGORIA_CHOICES,
        'prioridades': TicketSoporte.PRIORIDAD_CHOICES,
    })


@login_required
@admin_only
@require_http_methods(['GET', 'POST'])
def soporte_detalle_view(request, pk):
    ticket = get_object_or_404(TicketSoporte.objects.select_related('creado_por', 'actualizado_por'), pk=pk)

    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()
        if accion == 'actualizar_estado':
            nuevo_estado = request.POST.get('estado', '').strip()
            respuesta = request.POST.get('respuesta', '').strip()
            estados = {e[0] for e in TicketSoporte.ESTADO_CHOICES}
            if nuevo_estado not in estados:
                messages.error(request, 'Estado no válido.')
                return redirect('soporte_detalle', pk=pk)

            anterior = ticket.estado
            ticket.estado = nuevo_estado
            if respuesta:
                ticket.respuesta = respuesta
            ticket.actualizado_por = request.user
            ticket.save()
            register_audit_event(
                AuditEvent(
                    actor_id=request.user.id,
                    action='SUPPORT_TICKET_STATUS',
                    entity='TicketSoporte',
                    entity_id=str(ticket.pk),
                    field_name='estado',
                    old_value=anterior,
                    new_value=nuevo_estado,
                    reason=respuesta or 'Cambio de estado de ticket',
                )
            )
            messages.success(request, f'Ticket #{ticket.pk} actualizado.')
            return redirect('soporte_detalle', pk=pk)

    return render(request, 'soporte/detalle.html', {
        'ticket': ticket,
        'estados': TicketSoporte.ESTADO_CHOICES,
    })
