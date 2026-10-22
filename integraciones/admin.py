from django.contrib import admin

from .models import (
    MoreAppFormularioAsignado,
    MoreAppFormularioOculto,
    MoreAppFuenteFila,
    MoreAppFuenteInterna,
    MoreAppGrupoAlias,
    MoreAppTareaEnviada,
)


@admin.register(MoreAppFormularioOculto)
class MoreAppFormularioOcultoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "form_name", "form_id", "fecha_oculto")
    list_filter = ("usuario",)
    search_fields = ("form_id", "form_name")
    readonly_fields = ("fecha_oculto",)


@admin.register(MoreAppFormularioAsignado)
class MoreAppFormularioAsignadoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "form_name", "form_id", "asignado_por", "fecha_asignacion")
    list_filter = ("usuario",)
    search_fields = ("form_id", "form_name")
    readonly_fields = ("fecha_asignacion",)


@admin.register(MoreAppFuenteInterna)
class MoreAppFuenteInternaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "datasource_id", "fecha_importacion", "fecha_alta")
    search_fields = ("nombre", "datasource_id")
    readonly_fields = ("fecha_alta", "fecha_actualizacion", "fecha_importacion")


@admin.register(MoreAppFuenteFila)
class MoreAppFuenteFilaAdmin(admin.ModelAdmin):
    list_display = ("fuente", "entry_id")
    search_fields = ("entry_id", "fuente__nombre")
    list_filter = ("fuente",)


@admin.register(MoreAppGrupoAlias)
class MoreAppGrupoAliasAdmin(admin.ModelAdmin):
    list_display = ("nombre", "group_id", "actualizado_por", "fecha_actualizacion")
    search_fields = ("nombre", "group_id")
    readonly_fields = ("fecha_actualizacion",)


@admin.register(MoreAppTareaEnviada)
class MoreAppTareaEnviadaAdmin(admin.ModelAdmin):
    list_display = ("form_name", "mensaje", "envio", "creado_por", "fecha_creacion", "task_id")
    list_filter = ("envio",)
    search_fields = ("form_id", "form_name", "mensaje", "task_id")
    readonly_fields = ("fecha_creacion",)
