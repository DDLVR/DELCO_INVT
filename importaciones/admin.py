from django.contrib import admin
from .models import ImportacionExcel, ImportacionExcelError


class ImportacionExcelErrorInline(admin.TabularInline):
    model = ImportacionExcelError
    extra = 0
    readonly_fields = ('numero_fila', 'motivo', 'data_cruda', 'fecha_creacion')


@admin.register(ImportacionExcel)
class ImportacionExcelAdmin(admin.ModelAdmin):
    list_display = ('get_tipo_display', 'usuario', 'estado', 'total_filas', 'exitosas', 'fallidas', 'fecha_hora')
    list_filter = ('tipo', 'estado', 'fecha_hora', 'usuario')
    readonly_fields = ('fecha_hora', 'total_filas', 'exitosas', 'fallidas')
    inlines = [ImportacionExcelErrorInline]
    
    fieldsets = (
        ('Información de Importación', {
            'fields': ('tipo', 'archivo_original', 'usuario', 'fecha_hora')
        }),
        ('Resultados', {
            'fields': ('estado', 'total_filas', 'exitosas', 'fallidas')
        }),
        ('Observaciones', {
            'fields': ('observaciones',)
        }),
    )


@admin.register(ImportacionExcelError)
class ImportacionExcelErrorAdmin(admin.ModelAdmin):
    list_display = ('importacion', 'numero_fila', 'motivo')
    list_filter = ('importacion__tipo', 'importacion__fecha_hora')
    search_fields = ('motivo', 'data_cruda')
    readonly_fields = ('data_cruda', 'fecha_creacion')
