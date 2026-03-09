from django.contrib import admin
from .models import IntegracionMoreAppLog


@admin.register(IntegracionMoreAppLog)
class IntegracionMoreAppLogAdmin(admin.ModelAdmin):
    list_display = ('estado', 'orden_asociada', 'adjunto_creado', 'fecha_hora')
    list_filter = ('estado', 'fecha_hora')
    search_fields = ('mensaje_error', 'payload_crudo')
    readonly_fields = ('fecha_hora', 'payload_crudo')
    
    fieldsets = (
        ('Información', {
            'fields': ('estado', 'fecha_hora')
        }),
        ('Asociaciones', {
            'fields': ('orden_asociada', 'adjunto_creado')
        }),
        ('Payload Recibido', {
            'fields': ('payload_crudo',)
        }),
        ('Errores', {
            'fields': ('mensaje_error',)
        }),
    )
