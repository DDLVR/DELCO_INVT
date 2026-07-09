from django.db import models


class CatalogoDiagnostico(models.Model):
    """Catálogo de causas y soluciones (PDF punto 10)."""

    CATEGORIA_CHOICES = [
        ('SISTEMA', 'Sistema'),
        ('SIMCARD', 'SIMCard'),
        ('MODEM', 'Módem'),
        ('MEDIDOR', 'Medidor'),
        ('ESTADO_CLIENTE', 'Estado cliente'),
        ('ESTADO_VISITA', 'Estado visita'),
        ('OTRO', 'Otro'),
    ]

    categoria = models.CharField(max_length=30, choices=CATEGORIA_CHOICES)
    origen = models.CharField(max_length=255, help_text='Causa u origen del diagnóstico')
    solucion = models.TextField(help_text='Acción o solución recomendada')
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Diagnóstico'
        verbose_name_plural = 'Catálogo de diagnósticos'
        ordering = ['categoria', 'orden', 'origen']
        indexes = [
            models.Index(fields=['categoria', 'activo']),
        ]

    def __str__(self):
        return f'{self.get_categoria_display()}: {self.origen}'
