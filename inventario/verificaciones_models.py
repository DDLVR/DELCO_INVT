"""
Modelos para Verificaciones de Medidores recibidas desde MoreApp
TEMPORAL - Los datos se guardarán aquí hasta definir estructura final
"""
from django.db import models
from django.utils import timezone


class VerificacionMedidor(models.Model):
    """
    Verificación de medidor recibida desde MoreApp
    Guarda temporalmente los datos del formulario
    """
    
    # Metadatos de MoreApp
    submission_id = models.CharField(max_length=255, unique=True, help_text="ID único del formulario en MoreApp")
    fecha_recepcion = models.DateTimeField(auto_now_add=True, help_text="Cuándo se recibió en el sistema")
    
    # Datos del formulario
    num_cliente = models.CharField(max_length=100, blank=True, null=True, verbose_name="Número de Cliente")
    num_orden = models.CharField(max_length=100, blank=True, null=True, verbose_name="Número de Orden")
    direccion = models.CharField(max_length=255, blank=True, null=True, verbose_name="Dirección")
    comuna = models.CharField(max_length=100, blank=True, null=True, verbose_name="Comuna")
    resultado_visita = models.CharField(max_length=255, blank=True, null=True, verbose_name="Resultado de Visita")
    estado_medidor = models.CharField(max_length=100, blank=True, null=True, verbose_name="Estado del Medidor")
    
    # Foto (URL de MoreApp o ruta local si se descarga)
    foto_fachada_url = models.URLField(max_length=500, blank=True, null=True, verbose_name="URL Foto Fachada")
    
    # JSON completo por si necesitamos datos adicionales
    datos_completos = models.JSONField(default=dict, blank=True, verbose_name="Datos completos JSON")
    
    # Estado de procesamiento
    procesado = models.BooleanField(default=False, help_text="Si ya se procesó y movió a su ubicación final")
    notas_procesamiento = models.TextField(blank=True, null=True, help_text="Notas sobre el procesamiento")
    
    class Meta:
        verbose_name = "Verificación de Medidor"
        verbose_name_plural = "Verificaciones de Medidores"
        ordering = ['-fecha_recepcion']
        
    def __str__(self):
        return f"Verificación {self.num_orden or self.submission_id[:8]} - {self.fecha_recepcion.strftime('%d/%m/%Y')}"
