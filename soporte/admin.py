from django.contrib import admin

from .models import TicketSoporte


@admin.register(TicketSoporte)
class TicketSoporteAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'categoria', 'prioridad', 'estado', 'creado_por', 'fecha_creacion')
    list_filter = ('estado', 'prioridad', 'categoria')
    search_fields = ('titulo', 'descripcion', 'pagina_url')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
