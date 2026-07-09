from django.contrib import admin

from .models import CatalogoDiagnostico


@admin.register(CatalogoDiagnostico)
class CatalogoDiagnosticoAdmin(admin.ModelAdmin):
    list_display = ('categoria', 'origen', 'solucion_corta', 'activo', 'orden')
    list_filter = ('categoria', 'activo')
    search_fields = ('origen', 'solucion')
    ordering = ('categoria', 'orden', 'origen')

    @admin.display(description='Solución')
    def solucion_corta(self, obj):
        return obj.solucion[:80] + ('…' if len(obj.solucion) > 80 else '')
