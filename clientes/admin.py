from django.contrib import admin
from .models import Cliente, ClienteAdjunto, ClienteProyectoHistorial


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('numero_cliente', 'customer_name', 'direccion', 'comuna', 'sector', 'city', 'proyecto', 'activo')
    list_filter = ('activo', 'comuna', 'sector', 'fecha_creacion')
    search_fields = ('numero_cliente', 'direccion', 'customer_name', 'ip', 'modem')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')

    fieldsets = (
        ('Información Básica (VERDES)', {
            'fields': ('numero_cliente', 'customer_name', 'tipo_suministro', 'sector', 'city', 'installation_address', 'proyecto', 'comuna', 'referencia'),
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


@admin.register(ClienteProyectoHistorial)
class ClienteProyectoHistorialAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'proyecto', 'fecha_inicio', 'fecha_fin', 'vigente', 'cambiado_por')
    list_filter = ('vigente',)
    search_fields = ('proyecto', 'cliente__numero_cliente', 'motivo')
    raw_id_fields = ('cliente', 'cambiado_por')


@admin.register(ClienteAdjunto)
class ClienteAdjuntoAdmin(admin.ModelAdmin):
    list_display = ('nombre_archivo', 'cliente', 'tipo', 'fecha_hora', 'eliminado', 'subido_por')
    list_filter = ('tipo', 'eliminado')
    search_fields = ('nombre_archivo', 'cliente__numero_cliente')
    raw_id_fields = ('cliente', 'subido_por', 'eliminado_por')
    readonly_fields = ('fecha_hora', 'fecha_eliminacion')
