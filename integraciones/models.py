# Preferencias de catálogo MoreApp API (por usuario).
# El registro operativo de MoreApp sigue en ordenes_trabajo.IntegracionMoreApp.

from django.conf import settings
from django.db import models


class MoreAppFormularioOculto(models.Model):
    """Formulario del catálogo API que un usuario oculta de su vista."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moreapp_formularios_ocultos",
    )
    form_id = models.CharField(max_length=80)
    form_name = models.CharField(max_length=255, blank=True)
    fecha_oculto = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("usuario", "form_id")
        verbose_name = "Formulario MoreApp oculto"
        verbose_name_plural = "Formularios MoreApp ocultos"

    def __str__(self):
        return "%s · %s" % (self.usuario_id, self.form_name or self.form_id)


class MoreAppFormularioAsignado(models.Model):
    """Formulario MoreApp que un administrador asigna a un usuario de la intranet."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moreapp_formularios_asignados",
    )
    form_id = models.CharField(max_length=80)
    form_name = models.CharField(max_length=255, blank=True)
    asignado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moreapp_formularios_asignados_por_mi",
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("usuario", "form_id")
        verbose_name = "Formulario MoreApp asignado"
        verbose_name_plural = "Formularios MoreApp asignados"
        ordering = ["form_name", "form_id"]

    def __str__(self):
        return "%s · %s" % (self.usuario_id, self.form_name or self.form_id)


class MoreAppFuenteInterna(models.Model):
    """Data source de MoreApp elegida para copiarse a la intranet. El resto no se guarda."""

    datasource_id = models.CharField(max_length=80, unique=True)
    nombre = models.CharField(max_length=255)
    columnas = models.JSONField(default=list, blank=True)
    filas_moreapp = models.PositiveIntegerField(null=True, blank=True)
    notas = models.CharField(max_length=255, blank=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moreapp_fuentes_internas",
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_importacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Fuente MoreApp interna"
        verbose_name_plural = "Fuentes MoreApp internas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre or self.datasource_id


class MoreAppFuenteFila(models.Model):
    """Fila local de una fuente MoreApp guardada en la intranet."""

    fuente = models.ForeignKey(
        MoreAppFuenteInterna,
        on_delete=models.CASCADE,
        related_name="filas",
    )
    entry_id = models.CharField(max_length=120)
    valores = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Fila de fuente MoreApp"
        verbose_name_plural = "Filas de fuentes MoreApp"
        unique_together = ("fuente", "entry_id")
        indexes = [
            models.Index(fields=["fuente", "entry_id"]),
        ]

    def __str__(self):
        return "%s · %s" % (self.fuente_id, self.entry_id)
