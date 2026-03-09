from django.db import models
from usuarios.models import Usuario


class IntegracionMoreAppLog(models.Model):
    """Log de integraciones con MoreApp (Webhook)"""
    
    STATUS_CHOICES = [
        ('RECIBIDO', 'Recibido'),
        ('PROCESADO', 'Procesado'),
        ('ERROR', 'Error'),
    ]
    
    fecha_hora = models.DateTimeField(auto_now_add=True)
    
    estado = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    payload_crudo = models.JSONField(help_text='Contenido completo recibido')
    
    mensaje_error = models.TextField(blank=True)
    
    orden_asociada = models.ForeignKey(
        'ordenes_trabajo.OrdenTrabajo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='integraciones_moreapp'
    )
    
    adjunto_creado = models.ForeignKey(
        'ordenes_trabajo.AdjuntoOrden',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='integracion_origen'
    )
    
    def __str__(self):
        return f'MoreApp {self.get_estado_display()} - {self.fecha_hora.strftime("%d/%m/%Y %H:%M")}'
    
    class Meta:
        verbose_name = 'Integración MoreApp'
        verbose_name_plural = 'Integraciones MoreApp'
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['estado']),
            models.Index(fields=['-fecha_hora']),
        ]
