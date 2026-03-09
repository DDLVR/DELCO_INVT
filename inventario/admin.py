from django.contrib import admin
from .models import (
    EstadoInventario, Ubicacion, Medidor, SimCard, Modem,
    MovimientoInventario, MovimientoItem, VerificacionMedidor
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
        ('Información de Entrega', {
            'fields': ('fecha_entrega', 'entregado_a', 'cliente', 'estado_inventario')
        }),
        ('Trazabilidad', {
            'fields': ('en_custodia_de', 'ubicacion_actual', 'observaciones')
        }),
        ('Fechas', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SimCard)
class SimCardAdmin(admin.ModelAdmin):
    list_display = ('imei', 'operador', 'abonado', 'estado_inventario', 'cliente', 'medidor')
    list_filter = ('operador', 'estado_inventario', 'fecha_recepcion', 'fecha_entrega')
    search_fields = ('imei', 'abonado', 'operador', 'apn', 'direccion_ip')
    readonly_fields = ('fecha_creacion',)
    
    fieldsets = (
        ('Información desde Planilla (Amarillo)', {
            'fields': ('imei', 'operador', 'abonado', 'direccion_ip', 'apn', 'fecha_recepcion', 'entregado_a_nombre')
        }),
        ('Información Administrativa (Verde)', {
            'fields': ('fecha_entrega', 'estado_inventario', 'cliente', 'medidor')
        }),
        ('Campos Legacy', {
            'fields': ('msisdn', 'proveedor', 'serie_plastico', 'ip_fija', 'ubicacion_actual', 'en_custodia_de'),
            'classes': ('collapse',)
        }),
        ('Fechas', {
            'fields': ('fecha_creacion',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Modem)
class ModemAdmin(admin.ModelAdmin):
    list_display = ('serie', 'caja', 'marca', 'modulo', 'estado_inventario', 'entregado_a', 'cliente')
    list_filter = ('estado_inventario', 'marca', 'fecha_recepcion', 'fecha_entrega')
    search_fields = ('serie', 'caja', 'marca', 'modulo')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    fieldsets = (
        ('Información de Recepción', {
            'fields': ('fecha_recepcion', 'bodega', 'marca', 'caja', 'serie', 'modulo')
        }),
        ('Información de Entrega', {
            'fields': ('fecha_entrega', 'entregado_a', 'cliente', 'estado_inventario')
        }),
        ('Trazabilidad', {
            'fields': ('en_custodia_de', 'ubicacion_actual', 'observaciones')
        }),
        ('Fechas', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )


class MovimientoItemInline(admin.TabularInline):
    model = MovimientoItem
    extra = 1


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('get_tipo_display', 'origen', 'destino', 'responsable', 'fecha_hora')
    list_filter = ('tipo', 'fecha_hora', 'responsable')
    search_fields = ('observacion',)
    readonly_fields = ('fecha_hora',)
    inlines = [MovimientoItemInline]


@admin.register(MovimientoItem)
class MovimientoItemAdmin(admin.ModelAdmin):
    list_display = ('movimiento', 'get_tipo_equipo_display', 'cantidad')
    list_filter = ('tipo_equipo',)


@admin.register(VerificacionMedidor)
class VerificacionMedidorAdmin(admin.ModelAdmin):
    list_display = ('submission_id_corto', 'num_orden', 'num_cliente', 'comuna', 'resultado_visita', 'fecha_recepcion', 'procesado')
    list_filter = ('procesado', 'fecha_recepcion', 'comuna', 'resultado_visita')
    search_fields = ('num_cliente', 'num_orden', 'direccion', 'comuna', 'submission_id')
    readonly_fields = ('fecha_recepcion', 'submission_id', 'datos_completos')
    list_editable = ('procesado',)
    
    def submission_id_corto(self, obj):
        return obj.submission_id[:20] + "..." if len(obj.submission_id) > 20 else obj.submission_id
    submission_id_corto.short_description = "ID MoreApp"
    
    fieldsets = (
        ('Información del Formulario', {
            'fields': ('submission_id', 'fecha_recepcion', 'procesado')
        }),
        ('Datos de la Verificación', {
            'fields': ('num_cliente', 'num_orden', 'direccion', 'comuna', 'resultado_visita', 'estado_medidor')
        }),
        ('Evidencia', {
            'fields': ('foto_fachada_url',)
        }),
        ('Procesamiento', {
            'fields': ('notas',)
        }),
        ('Datos Completos (JSON)', {
            'fields': ('datos_completos',),
            'classes': ('collapse',)
        }),
    )
