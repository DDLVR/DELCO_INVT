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
        help_text='Identificador comercial del cliente en el sistema'
    )
    
    direccion = models.CharField(max_length=255)
    
    comuna = models.CharField(max_length=100)
    
    referencia = models.TextField(
        blank=True,
        null=True,
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

    tipo_suministro = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Tipo de suministro asociado al cliente'
    )

    pod = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Punto de entrega (POD) del cliente'
    )

    sector = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Sector o área geográfica del cliente'
    )

    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Ciudad del cliente'
    )

    customer_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Nombre del cliente'
    )

    installation_address = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Dirección de instalación del cliente'
    )

    proyecto = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Proyecto asociado al cliente'
    )

    meter_manufacturer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Fabricante o identificador del medidor'
    )

    meter_serial_n_1 = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Número de serie del medidor'
    )

    client_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Tipo de cliente'
    )

    note = models.TextField(
        blank=True,
        null=True,
        help_text='Nota adicional para el cliente'
    )

    ultimo_acceso = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Último acceso registrado'
    )

    ultimo_perfil_carga = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Último perfil de carga'
    )

    ultimo_perfil_instrumentacion = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Último perfil de instrumentación'
    )

    ultimo_reset = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Último reset registrado'
    )

    ultimo_registro_facturacion = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Último registro de facturación'
    )

    # ═════════════════════════════════════════════════════════
    # CAMPOS ADICIONALES (AMARILLOS) - Para rellenar por administrativo
    # ═════════════════════════════════════════════════════════
    
    trabajo = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Descripción del trabajo realizado o a realizar'
    )
    
    ip = models.CharField(
        max_length=45,
        blank=True,
        null=True,
        help_text='Dirección IP asignada al cliente/modem'
    )
    
    puerto = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='Puerto o número de puerto de la conexión'
    )
    
    modem = models.CharField(
        max_length=255,
        blank=True,
        null=True,
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
