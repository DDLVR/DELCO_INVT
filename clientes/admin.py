from django.contrib import admin
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('numero_cliente', 'customer_name', 'direccion', 'comuna', 'sector', 'city', 'proyecto', 'activo')
    list_filter = ('activo', 'comuna', 'sector', 'fecha_creacion')
    search_fields = ('numero_cliente', 'direccion', 'customer_name', 'ip', 'modem')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    fieldsets = (
        ('Información Básica (VERDES)', {
            'fields': ('numero_cliente', 'customer_name', 'tipo_suministro', 'pod', 'sector', 'city', 'installation_address', 'proyecto', 'comuna', 'referencia'),
            'description': 'Datos principales de identificación del cliente'
        }),
        ('Medidor / Conexión', {
            'fields': ('meter_manufacturer_id', 'meter_serial_n_1', 'medidor_actual', 'client_type', 'ip', 'puerto'),
        }),
        ('Importación/Exportación', {
            'fields': ('ultimo_acceso', 'ultimo_perfil_carga', 'ultimo_perfil_instrumentacion', 'ultimo_reset', 'ultimo_registro_facturacion', 'note'),
            'description': 'Campos usados para importación y exportación de clientes',
            'classes': ('collapse',)
        }),
        ('Información Adicional (AMARILLOS) - Para completar por administrativo', {
            'fields': ('trabajo', 'modem', 'fecha_registro'),
            'description': 'Campos adicionales para la configuración técnica',
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('activo', 'fecha_creacion', 'fecha_actualizacion')
        }),
    )
