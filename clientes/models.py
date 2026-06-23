from django.db import models


class Cliente(models.Model):
    """
    Representa un cliente (domicilio/punto de instalación).
    
    Un cliente es el lugar donde se instalan medidores y se realizan trabajos.
    """
    
    # ═════════════════════════════════════════════════════════
    # CAMPOS PRINCIPALES (VERDES) - Datos de instalación
    # ═════════════════════════════════════════════════════════
    
    numero_cliente = models.CharField(
        max_length=50,
        unique=True,
        help_text='Identificador único del cliente en el sistema'
    )
    
    direccion = models.CharField(max_length=255)
    
    comuna = models.CharField(max_length=100)
    
    referencia = models.TextField(
        blank=True,
        help_text='Notas adicionales para ubicación (ej: "Puerta roja, cerca del almacén")'
    )
    
    medidor_actual = models.OneToOneField(
        'inventario.Medidor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cliente_actual',
        help_text='Medidor instalado actualmente en este cliente'
    )
    
    # ═════════════════════════════════════════════════════════
    # CAMPOS ADICIONALES (AMARILLOS) - Para rellenar por administrativo
    # ═════════════════════════════════════════════════════════
    
    trabajo = models.CharField(
        max_length=255,
        blank=True,
        help_text='Descripción del trabajo realizado o a realizar'
    )
    
    ip = models.CharField(
        max_length=45,
        blank=True,
        help_text='Dirección IP asignada al cliente/modem'
    )
    
    puerto = models.CharField(
        max_length=50,
        blank=True,
        help_text='Puerto o número de puerto de la conexión'
    )
    
    modem = models.CharField(
        max_length=255,
        blank=True,
        help_text='Modelo o información del módem instalado'
    )
    
    fecha_registro = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha de registro o instalación del cliente'
    )
    
    # ═════════════════════════════════════════════════════════
    # CAMPOS DE AUDITORÍA
    # ═════════════════════════════════════════════════════════
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return f'{self.numero_cliente} - {self.direccion}'
    
    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['numero_cliente']
        indexes = [
            models.Index(fields=['numero_cliente']),
            models.Index(fields=['activo']),
        ]
