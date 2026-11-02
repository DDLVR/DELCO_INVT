from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from web.decorators import role_required

from .models import CatalogoDiagnostico


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'AUDITOR', 'GERENCIA'])
def catalogo_diagnostico_list_view(request):
    categoria = (request.GET.get('categoria') or '').strip()
    q = (request.GET.get('q') or '').strip()
    qs = CatalogoDiagnostico.objects.filter(activo=True)
    if categoria:
        qs = qs.filter(categoria=categoria)
    if q:
        qs = qs.filter(Q(origen__icontains=q) | Q(solucion__icontains=q))

    return render(request, 'catalogos/list.html', {
        'items': qs.order_by('orden', 'categoria', 'origen'),
        'categorias': CatalogoDiagnostico.CATEGORIA_CHOICES,
        'categoria_actual': categoria,
        'q': q,
        'total': qs.count(),
    })
