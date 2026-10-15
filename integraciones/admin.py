from django.contrib import admin

from .models import MoreAppFormularioOculto


@admin.register(MoreAppFormularioOculto)
class MoreAppFormularioOcultoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "form_name", "form_id", "fecha_oculto")
    list_filter = ("usuario",)
    search_fields = ("form_id", "form_name")
    readonly_fields = ("fecha_oculto",)
