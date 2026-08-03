from django.contrib import admin
from .models import (
    EstadoInventario, Ubicacion, Medidor, SimCard, Modem,
    MovimientoInventario, MovimientoItem,
)


@admin.register(EstadoInventario)
class EstadoInventarioAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'direccion')
    list_filter = ('tipo',)
    search_fields = ('nombre', 'direccion')


@admin.register(Medidor)
class MedidorAdmin(admin.ModelAdmin):
    list_display = ('serie', 'caja', 'marca', 'modulo', 'estado_inventario', 'entregado_a', 'cliente')
    list_filter = ('estado_inventario', 'marca', 'fecha_recepcion', 'fecha_entrega')
    search_fields = ('serie', 'caja', 'marca', 'modulo')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    fieldsets = (
        ('Información de Recepción', {
            'fields': ('fecha_recepcion', 'bodega', 'marca', 'caja', 'serie', 'modulo')
        }),
        ('Entrega y Estado', {
            'fields': ('fecha_entrega', 'entregado_a', 'entregado_a_otro', 'entregado_a_info', 'estado_inventario')
        }),
        ('Asignación', {
            'fields': ('cliente', 'cliente_otro', 'proyecto', 'tipo_medidor')
        }),
        ('Ubicación', {
            'fields': ('ubicacion_actual', 'en_custodia_de')
        }),
        ('Auditoría', {
            'fields': ('observaciones', 'fecha_creacion', 'fecha_actualizacion', 'eliminado'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SimCard)
class SimCardAdmin(admin.ModelAdmin):
    list_display = ('imei', 'operador', 'abonado', 'direccion_ip', 'estado_inventario', 'cliente')
    list_filter = ('estado_inventario', 'operador', 'fecha_recepcion')
    search_fields = ('imei', 'abonado', 'direccion_ip', 'operador', 'msisdn')
    fieldsets = (
        ('Datos de recepción', {
            'fields': ('imei', 'operador', 'abonado', 'direccion_ip', 'apn', 'fecha_recepcion', 'entregado_a_nombre')
        }),
        ('Asignación', {
            'fields': ('fecha_entrega', 'estado_inventario', 'cliente', 'cliente_otro', 'medidor', 'medidor_otro', 'proyecto')
        }),
        ('Ubicación / legacy', {
            'fields': ('msisdn', 'proveedor', 'serie_plastico', 'ip_fija', 'ubicacion_actual', 'en_custodia_de'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Modem)
class ModemAdmin(admin.ModelAdmin):
    list_display = ('serie', 'marca', 'modelo', 'imei', 'estado_inventario', 'cliente')
    list_filter = ('estado_inventario', 'marca', 'fecha_recepcion')
    search_fields = ('serie', 'imei', 'marca', 'modelo')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')


class MovimientoItemInline(admin.TabularInline):
    model = MovimientoItem
    extra = 0


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('get_tipo_display', 'origen_sistema', 'origen', 'destino', 'responsable', 'fecha_hora')
    list_filter = ('tipo', 'origen_sistema', 'fecha_hora', 'responsable')
    search_fields = ('observacion',)
    readonly_fields = ('fecha_hora',)
    inlines = [MovimientoItemInline]


@admin.register(MovimientoItem)
class MovimientoItemAdmin(admin.ModelAdmin):
    list_display = ('movimiento', 'get_tipo_equipo_display', 'cantidad')
    list_filter = ('tipo_equipo',)
