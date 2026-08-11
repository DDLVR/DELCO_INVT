from django.db import models
from usuarios.models import Usuario


class ImportacionExcel(models.Model):
    """Registro de importaciones masivas desde Excel"""
    
    TIPO_CHOICES = [
        ('EQUIPOS', 'Importar Equipos (Medidores/SIM/Módems)'),
        ('CLIENTES', 'Importar Clientes'),
        ('MOVIMIENTOS', 'Importar Movimientos de Inventario'),
        ('ORDENES_TRABAJO', 'Importar Órdenes de Trabajo'),
        ('CARGAS_ADMINISTRATIVAS', 'Importar Órdenes de Trabajo Administrativas'),
    ]
    
    STATUS_CHOICES = [
        ('PROCESANDO', 'Procesando...'),
        ('COMPLETADO', 'Completado'),
        ('ERROR', 'Error'),
    ]
    
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    
    archivo_original = models.CharField(max_length=255)
    
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='importaciones'
    )
    usuario_nombre = models.CharField(max_length=255, blank=True, help_text='Nombre del usuario que realizó la importación (histórico)')
    
    fecha_hora = models.DateTimeField(auto_now_add=True)
    
    estado = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROCESANDO')
    
    total_filas = models.PositiveIntegerField(default=0)
    
    exitosas = models.PositiveIntegerField(default=0)
    
    fallidas = models.PositiveIntegerField(default=0)
    
    observaciones = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        # Guardar el nombre del usuario antes de guardar el registro
        if self.usuario:
            self.usuario_nombre = str(self.usuario)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.fecha_hora.strftime("%d/%m/%Y %H:%M")}'
    
    class Meta:
        verbose_name_plural = 'Importaciones Excel'
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['tipo']),
            models.Index(fields=['estado']),
            models.Index(fields=['usuario']),
        ]


class ImportacionExcelError(models.Model):
    """Detalle de errores en cada fila de importación"""
    
    importacion = models.ForeignKey(
        ImportacionExcel,
        on_delete=models.CASCADE,
        related_name='errores'
    )
    
    numero_fila = models.PositiveIntegerField()
    
    motivo = models.TextField()
    
    data_cruda = models.TextField(help_text='Contenido de la fila que falló')
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'Fila {self.numero_fila} - {self.importacion.get_tipo_display()}'
    
    class Meta:
        verbose_name_plural = 'Errores de Importación'
        ordering = ['numero_fila']
