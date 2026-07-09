from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from web.decorators import role_required

from .models import CatalogoDiagnostico


@login_required
@role_required(['ADMIN', 'ADMINISTRATIVO', 'AUDITOR', 'GERENCIA'])
def catalogo_diagnostico_list_view(request):
    categoria = request.GET.get('categoria', '')
    qs = CatalogoDiagnostico.objects.filter(activo=True)
    if categoria:
        qs = qs.filter(categoria=categoria)

    return render(request, 'catalogos/list.html', {
        'items': qs.order_by('categoria', 'orden', 'origen'),
        'categorias': CatalogoDiagnostico.CATEGORIA_CHOICES,
        'categoria_actual': categoria,
    })
