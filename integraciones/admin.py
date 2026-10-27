from django.contrib import admin

from .models import (
    MoreAppCuentaTecnico,
    MoreAppFormularioAsignado,
    MoreAppFormularioOculto,
    MoreAppFuenteFila,
    MoreAppFuenteInterna,
    MoreAppGrupoAlias,
    MoreAppTareaAlerta,
    MoreAppTareaEnviada,
    MoreAppTareaEvento,
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


@admin.register(MoreAppCuentaTecnico)
class MoreAppCuentaTecnicoAdmin(admin.ModelAdmin):
    list_display = ("email", "tecnico_nombre", "tecnico_entry_id", "moreapp_nombre", "actualizado_por", "fecha_actualizacion")
    search_fields = ("email", "moreapp_nombre", "tecnico_nombre", "tecnico_entry_id")
    readonly_fields = ("fecha_actualizacion",)


@admin.register(MoreAppTareaEnviada)
class MoreAppTareaEnviadaAdmin(admin.ModelAdmin):
    list_display = (
        "form_name",
        "mensaje",
        "estado",
        "cuenta",
        "envio",
        "creado_por",
        "fecha_creacion",
        "fecha_completado",
        "task_id",
    )
    list_filter = ("estado", "envio")
    search_fields = ("form_id", "form_name", "mensaje", "task_id", "cuenta")
    readonly_fields = ("fecha_creacion", "fecha_asignacion", "fecha_completado", "ultima_sync")


@admin.register(MoreAppTareaEvento)
class MoreAppTareaEventoAdmin(admin.ModelAdmin):
    list_display = ("tarea", "tipo", "origen", "en")
    list_filter = ("tipo", "origen")
    readonly_fields = ("en",)


@admin.register(MoreAppTareaAlerta)
class MoreAppTareaAlertaAdmin(admin.ModelAdmin):
    list_display = ("tarea", "tipo", "usuario", "broadcast", "leida_en", "fecha_creacion")
    list_filter = ("tipo", "broadcast")
    readonly_fields = ("fecha_creacion",)
