from django.contrib import admin
from .models import (
    OrdenTrabajo, EquipoTrabajo, Vehiculo, Herramienta,
    OrdenHerramientaRequerida, AdjuntoOrden, IntegracionMoreApp
)


class AdjuntoOrdenInline(admin.TabularInline):
    model = AdjuntoOrden
    extra = 0
    readonly_fields = ('fecha_hora', 'subido_por')


@admin.register(OrdenTrabajo)
class OrdenTrabajoAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'titulo',
        'tipo_trabajo',
        'estado',
        'tecnico_responsable',
        'cliente',
        'fecha_creacion',
    )
    list_filter = ('estado', 'tipo_trabajo', 'fecha_creacion', 'tecnico_responsable')
    search_fields = ('titulo', 'descripcion', 'cliente__numero_cliente')
    readonly_fields = ('fecha_creacion', 'fecha_asignacion', 'fecha_inicio_ejecucion', 'fecha_fin_ejecucion', 'fecha_cierre', 'fecha_validacion')
    inlines = [AdjuntoOrdenInline]
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('titulo', 'descripcion', 'tipo_trabajo', 'cliente')
        }),
        ('Equipos Utilizados', {
            'fields': ('medidor', 'simcard', 'modem'),
            'classes': ('collapse',)
        }),
        ('Asignación', {
            'fields': ('tecnico_responsable', 'equipo_trabajo', 'tecnicos_equipo')
        }),
        ('Observaciones', {
            'fields': ('observaciones_tecnicas', 'observacion_validacion')
        }),
        ('Estados', {
            'fields': ('estado', 'tecnico_solicito_reasignacion')
        }),
        ('Auditoría y Fechas', {
            'fields': (
                'creada_por', 
                'validada_por', 
                'fecha_creacion', 
                'fecha_asignacion',
                'fecha_inicio_ejecucion',
                'fecha_fin_ejecucion',
                'fecha_cierre', 
                'fecha_validacion'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(EquipoTrabajo)
class EquipoTrabajoAdmin(admin.ModelAdmin):
    list_display = ('responsable', 'vehiculo', 'activo', 'fecha_creacion')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('responsable__nombre_interno',)
    filter_horizontal = ('miembros',)


@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ('patente', 'modelo', 'estado')
    list_filter = ('estado',)
    search_fields = ('patente', 'modelo')


@admin.register(Herramienta)
class HerramientaAdmin(admin.ModelAdmin):
    list_display = ('codigo_interno', 'nombre', 'estado')
    list_filter = ('estado',)
    search_fields = ('codigo_interno', 'nombre')


class OrdenHerramientaRequeridalInline(admin.TabularInline):
    model = OrdenHerramientaRequerida
    extra = 0


@admin.register(AdjuntoOrden)
class AdjuntoOrdenAdmin(admin.ModelAdmin):
    list_display = ('nombre_archivo', 'orden', 'tipo', 'subido_por', 'fecha_hora')
    list_filter = ('tipo', 'fecha_hora')
    search_fields = ('nombre_archivo', 'orden__titulo')
    readonly_fields = ('fecha_hora', 'hash_archivo')


@admin.register(IntegracionMoreApp)
class IntegracionMoreAppAdmin(admin.ModelAdmin):
    list_display = (
        'moreapp_submission_id',
        'orden',
        'estado_sincronizacion',
        'fecha_recepcion',
        'actualizo_cliente',
        'actualizo_equipos',
        'creo_adjuntos'
    )
    list_filter = ('estado_sincronizacion', 'fecha_recepcion', 'actualizo_cliente', 'actualizo_equipos')
    search_fields = ('moreapp_submission_id', 'orden__titulo', 'mensaje_error')
    readonly_fields = ('fecha_recepcion', 'fecha_procesamiento')
    
    fieldsets = (
        ('Identificación', {
            'fields': ('moreapp_submission_id', 'orden')
        }),
        ('Estado', {
            'fields': ('estado_sincronizacion', 'mensaje_error')
        }),
        ('Datos', {
            'fields': ('datos_recibidos', 'datos_procesados'),
            'classes': ('collapse',)
        }),
        ('Actualizaciones', {
            'fields': ('actualizo_cliente', 'actualizo_equipos', 'creo_adjuntos')
        }),
        ('Auditoría', {
            'fields': ('procesado_por', 'fecha_recepcion', 'fecha_procesamiento'),
            'classes': ('collapse',)
        }),
    )
