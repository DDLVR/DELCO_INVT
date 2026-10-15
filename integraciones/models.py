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
