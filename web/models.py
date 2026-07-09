from django.conf import settings
from django.db import models


class AuditoriaRegistro(models.Model):
    """Registro persistente de cambios (PDF punto 12)."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auditorias_realizadas',
    )
    fecha_hora = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=100, db_index=True)
    entity = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=100, db_index=True)
    field_name = models.CharField(max_length=100, blank=True, null=True)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    reason = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['entity', 'entity_id']),
        ]

    def __str__(self):
        return f'{self.action} {self.entity}:{self.entity_id} ({self.fecha_hora:%Y-%m-%d %H:%M})'
