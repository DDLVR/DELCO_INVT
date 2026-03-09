from django.contrib import admin
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('numero_cliente', 'direccion', 'comuna', 'medidor_actual', 'activo')
    list_filter = ('activo', 'comuna', 'fecha_creacion')
    search_fields = ('numero_cliente', 'direccion')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('numero_cliente', 'direccion', 'comuna')
        }),
        ('Medidor', {
            'fields': ('medidor_actual',)
        }),
        ('Notas', {
            'fields': ('referencia',)
        }),
        ('Estado', {
            'fields': ('activo', 'fecha_creacion', 'fecha_actualizacion')
        }),
    )
