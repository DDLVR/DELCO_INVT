from django.db import models

from usuarios.models import Usuario


class TicketSoporte(models.Model):
    """Ticket interno para reportar bugs y problemas (solo ADMIN)."""

    CATEGORIA_CHOICES = [
        ('BUG', 'Bug / Error'),
        ('PROBLEMA', 'Problema operativo'),
        ('MEJORA', 'Mejora / Idea'),
        ('ACCESO', 'Acceso / Permisos'),
        ('OTRO', 'Otro'),
    ]

    PRIORIDAD_CHOICES = [
        ('BAJA', 'Baja'),
        ('MEDIA', 'Media'),
        ('ALTA', 'Alta'),
        ('CRITICA', 'Crítica'),
    ]

    ESTADO_CHOICES = [
        ('ABIERTO', 'Abierto'),
        ('EN_REVISION', 'En revisión'),
        ('RESUELTO', 'Resuelto'),
        ('CERRADO', 'Cerrado'),
    ]

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='BUG')
    prioridad = models.CharField(max_length=20, choices=PRIORIDAD_CHOICES, default='MEDIA')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='ABIERTO', db_index=True)
    pagina_url = models.CharField(
        max_length=500,
        blank=True,
        help_text='URL o pantalla donde ocurrió el problema',
    )
    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='tickets_soporte_creados',
    )
    actualizado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_soporte_actualizados',
    )
    respuesta = models.TextField(blank=True, help_text='Notas internas de seguimiento')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = 'Ticket de soporte'
        verbose_name_plural = 'Tickets de soporte'
        indexes = [
            models.Index(fields=['estado', '-fecha_creacion']),
            models.Index(fields=['prioridad', '-fecha_creacion']),
        ]

    def __str__(self):
        return f'Ticket #{self.pk} — {self.titulo}'
