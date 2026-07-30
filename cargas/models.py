from django.db import models

from usuarios.models import Usuario


class CargaAdministrativa(models.Model):
    """
    Tarea administrativa asignable (verificaciones, validaciones, SCi4, etc.).
    Permite distribuir y seguir el trabajo de oficina aparte de las colas operativas.
    """

    TIPO_CHOICES = [
        ('VALIDACION_OT', 'Validación de OT'),
        ('VERIFICACION_SCI4', 'Actualización base comercial (SCi4)'),
        ('REVISION_MOREAPP', 'Revisión MoreApp'),
        ('COMUNICACION', 'Validación de comunicación'),
        ('VERIFICACION', 'Verificación administrativa'),
        ('OTRO', 'Otro'),
    ]

    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROGRESO', 'En progreso'),
        ('COMPLETADA', 'Completada'),
        ('CANCELADA', 'Cancelada'),
    ]

    PRIORIDAD_CHOICES = [
        ('BAJA', 'Baja'),
        ('MEDIA', 'Media'),
        ('ALTA', 'Alta'),
    ]

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default='VERIFICACION', db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE', db_index=True)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default='MEDIA')

    asignado_a = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cargas_asignadas',
        limit_choices_to={'rol__in': ['ADMIN', 'ADMINISTRATIVO'], 'is_active': True},
        help_text='Administrativo responsable de la carga',
    )
    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='cargas_creadas',
    )

    orden = models.ForeignKey(
        'ordenes_trabajo.OrdenTrabajo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cargas_admin',
    )
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cargas_admin',
    )
    url_referencia = models.CharField(
        max_length=500,
        blank=True,
        help_text='Enlace directo a la pantalla de trabajo',
    )

    observaciones = models.TextField(
        blank=True,
        help_text='Notas de avance o resultado al completar',
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_completada = models.DateTimeField(null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = 'Carga administrativa'
        verbose_name_plural = 'Cargas administrativas'
        indexes = [
            models.Index(fields=['estado', '-fecha_creacion']),
            models.Index(fields=['asignado_a', 'estado']),
            models.Index(fields=['tipo', 'estado']),
            models.Index(fields=['orden']),
            models.Index(fields=['cliente']),
        ]

    def __str__(self):
        return f'Carga #{self.pk} — {self.titulo}'

    @property
    def abierta(self) -> bool:
        return self.estado in ('PENDIENTE', 'EN_PROGRESO')
