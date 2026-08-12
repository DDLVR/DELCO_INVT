from django.db import models

from config.storage import evidencia_upload_to, evidencias_storage
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
        help_text='Administrativo responsable de la carga (usuario del sistema)',
    )
    asignado_texto = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Nombre libre del responsable (p. ej. desde Excel); no requiere usuario del sistema',
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
    proyecto = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_index=True,
        help_text='Proyecto / listado asociado a esta carga administrativa',
    )
    url_referencia = models.CharField(
        max_length=500,
        blank=True,
        help_text='Enlace directo a la pantalla de trabajo (p. ej. listado filtrado por proyecto)',
    )

    observaciones = models.TextField(
        blank=True,
        help_text='Notas de avance o resultado al completar',
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_completada = models.DateTimeField(null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    # Soft-delete: oculta la carga sin borrar adjuntos ni vínculos
    eliminado = models.BooleanField(default=False, db_index=True)
    fecha_eliminacion = models.DateTimeField(null=True, blank=True)
    eliminado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cargas_eliminadas',
    )

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
            models.Index(fields=['proyecto']),
            models.Index(fields=['eliminado', 'estado']),
        ]

    def __str__(self):
        return f'Carga #{self.pk} — {self.titulo}'

    @property
    def abierta(self) -> bool:
        return self.estado in ('PENDIENTE', 'EN_PROGRESO')

    @property
    def asignado_display(self) -> str:
        """Texto a mostrar como responsable (usuario del sistema o texto libre)."""
        if self.asignado_a_id:
            return self.asignado_a.nombre_interno or str(self.asignado_a)
        return (self.asignado_texto or '').strip()


class AdjuntoCarga(models.Model):
    """Fotos, PDF MoreApp u otros archivos adjuntos a una carga administrativa."""

    TIPO_CHOICES = [
        ('FOTO', 'Fotografía / captura de pantalla'),
        ('PDF', 'PDF'),
        ('MOREAPP', 'Archivo MoreApp'),
        ('OTRO', 'Otro'),
    ]

    carga = models.ForeignKey(
        CargaAdministrativa,
        on_delete=models.CASCADE,
        related_name='adjuntos',
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='FOTO')
    nombre_archivo = models.CharField(max_length=255)
    archivo = models.FileField(
        upload_to=evidencia_upload_to,
        storage=evidencias_storage,
        help_text='Archivo en Registros/Evidencias/adjuntos_cargas',
    )
    subido_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adjuntos_carga_subidos',
    )
    fecha_hora = models.DateTimeField(auto_now_add=True)
    hash_archivo = models.CharField(max_length=64, blank=True)

    # Papelera: soft-delete para poder recuperar o borrar definitivo
    eliminado = models.BooleanField(default=False, db_index=True)
    fecha_eliminacion = models.DateTimeField(null=True, blank=True)
    eliminado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adjuntos_carga_eliminados',
    )

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Adjunto de carga'
        verbose_name_plural = 'Adjuntos de cargas'
        indexes = [
            models.Index(fields=['carga']),
            models.Index(fields=['tipo']),
            models.Index(fields=['carga', 'eliminado']),
        ]

    def __str__(self):
        return f'{self.nombre_archivo} — Carga #{self.carga_id}'

    @property
    def es_imagen(self) -> bool:
        """True solo si el archivo es una imagen (por extensión)."""
        nombre = (self.nombre_archivo or '').lower()
        if self.archivo and getattr(self.archivo, 'name', None):
            nombre = self.archivo.name.lower()
        return nombre.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))

    @property
    def url_vista(self) -> str:
        if self.archivo:
            try:
                return self.archivo.url
            except ValueError:
                pass
        return ''
