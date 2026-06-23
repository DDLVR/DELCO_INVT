from django.contrib import admin
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('numero_cliente', 'direccion', 'comuna', 'modem', 'ip', 'activo')
    list_filter = ('activo', 'comuna', 'fecha_creacion')
    search_fields = ('numero_cliente', 'direccion', 'ip', 'modem')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    fieldsets = (
        ('Información Básica (VERDES)', {
            'fields': ('numero_cliente', 'direccion', 'comuna', 'referencia'),
            'description': 'Datos principales de identificación del cliente'
        }),
        ('Medidor', {
            'fields': ('medidor_actual',)
        }),
        ('Información Adicional (AMARILLOS) - Para completar por administrativo', {
            'fields': ('trabajo', 'ip', 'puerto', 'modem', 'fecha_registro'),
            'description': 'Campos adicionales para la configuración técnica',
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('activo', 'fecha_creacion', 'fecha_actualizacion')
        }),
    )
