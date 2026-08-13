from django.contrib import admin

from .models import CatalogoDiagnostico, Proyecto


@admin.register(CatalogoDiagnostico)
class CatalogoDiagnosticoAdmin(admin.ModelAdmin):
    list_display = ('categoria', 'origen', 'solucion_corta', 'activo', 'orden')
    list_filter = ('categoria', 'activo')
    search_fields = ('origen', 'solucion')
    ordering = ('categoria', 'orden', 'origen')

    @admin.display(description='Solución')
    def solucion_corta(self, obj):
        return obj.solucion[:80] + ('…' if len(obj.solucion) > 80 else '')


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'fecha_creacion', 'fecha_actualizacion')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    ordering = ('nombre',)
