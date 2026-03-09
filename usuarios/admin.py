from django.contrib import admin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = (
        'rut',
        'nombre_interno',
        'email',
        'rol',
        'is_active',
    )
    search_fields = ('rut', 'nombre', 'apellido', 'email')
    list_filter = ('rol', 'is_active')
