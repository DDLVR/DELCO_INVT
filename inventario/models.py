from django.db import models
from django.core.validators import MinValueValidator
from usuarios.models import Usuario


class EstadoInventario(models.Model):
    """Estados posibles de un equipo en inventario"""
    nombre = models.CharField(
        max_length=50,
        unique=True,
        help_text='BODEGA, INSTALADO, RETIRADO, REPARACION, BAJA, etc.'
    )
    descripcion = models.TextField(blank=True)
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name_plural = 'Estados de Inventario'


class Ubicacion(models.Model):
    """Lugares donde se almacenan/ubican equipos"""
    TIPO_CHOICES = [
        ('BODEGA_DELCO', 'Bodega Delco'),
        ('BODEGA_CONTRATISTA', 'Bodega Contratista'),
        ('TECNICO', 'Custodia Técnico'),
        ('CLIENTE', 'Instalado en Cliente'),
        ('PROVEEDOR', 'Proveedor/Reparación'),
    ]
    
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    nombre = models.CharField(max_length=255)
    direccion = models.CharField(max_length=255, blank=True)
    
    def __str__(self):
        return f'{self.nombre} ({self.get_tipo_display()})'
    
    class Meta:
        verbose_name_plural = 'Ubicaciones'


class Medidor(models.Model):
    """Medidores con trazabilidad completa - importados en bodega y entregados a técnicos"""
    
    # Campos de recepción en bodega (AMARILLOS - Se cargan en importación Excel)
    fecha_recepcion = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha de recepción en bodega (solo lectura)',
        editable=False
    )
    bodega = models.CharField(
        max_length=100,
        blank=True,
        help_text='Bodega de origen o referencia'
    )
    marca = models.CharField(max_length=100, blank=True, editable=False, help_text='Marca (solo lectura)')
    caja = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text='Número de caja de recepción (múltiples medidores por caja)'
    )
    serie = models.CharField(max_length=50, unique=True)
    modulo = models.BooleanField(
        null=True,
        blank=True,
        help_text='¿Tiene módulo? (Sí/No)'
    )
    
    # Campos que rellenará el administrativo (VERDES - Después de recibir)
    fecha_entrega = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha de entrega al técnico (editable)'
    )
    entregado_a = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medidores_entregados',
        help_text='Usuario a quien se entregó (editable)'
    )
    estado_inventario = models.ForeignKey(
        EstadoInventario,
        on_delete=models.PROTECT,
        related_name='medidores',
        null=True,
        blank=True,
        help_text='Estado del medidor (editable)'
    )
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medidores_asignados',
        help_text='Cliente (editable)'
    )
    
    # Campos de trazabilidad
    en_custodia_de = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medidores_en_custodia'
    )
    ubicacion_actual = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name='medidores',
        null=True,
        blank=True
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    observaciones = models.TextField(blank=True)
    
    def __str__(self):
        return f'Medidor {self.serie} - Caja {self.caja}'
    
    class Meta:
        verbose_name_plural = 'Medidores'
        indexes = [
            models.Index(fields=['serie']),
            models.Index(fields=['caja']),
            models.Index(fields=['estado_inventario']),
        ]


class SimCard(models.Model):
    """
    SIM Cards para módems/telemetría con trazabilidad completa
    
    CAMPOS AMARILLOS (desde Excel - obligatorios):
    - IMEI, OPERADOR, ABONADO, DIRECCIÓN IP, APN, FECHA_RECEPCION, ENTREGADO_A
    
    CAMPOS VERDES (administrativo modifica después):
    - FECHA_ENTREGA, ESTADO, CLIENTE, MEDIDOR
    """
    
    # ===== CAMPOS AMARILLOS (desde Excel) =====
    imei = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text='IMEI del modem/equipo asociado'
    )
    
    operador = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Operador telefónico (ENTEL, CLARO, MOVISTAR, etc.)'
    )
    
    abonado = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Número de abonado o identificador del operador'
    )
    
    direccion_ip = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Dirección IP asignada'
    )
    
    apn = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Access Point Name (APN) configurado'
    )
    
    fecha_recepcion = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha de recepción en bodega'
    )
    
    entregado_a_nombre = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Nombre de quien recibe (del Excel)'
    )
    
    # ===== CAMPOS VERDES (administrativo modifica) =====
    fecha_entrega = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha de entrega al técnico o instalación'
    )
    
    estado_inventario = models.ForeignKey(
        EstadoInventario,
        on_delete=models.PROTECT,
        related_name='simcards',
        null=True,
        blank=True
    )
    
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simcards_asignadas',
        help_text='Cliente al que está asignada la SIM'
    )
    
    medidor = models.ForeignKey(
        'inventario.Medidor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simcards_asociadas',
        help_text='Medidor asociado a esta SIM'
    )
    
    # ===== CAMPOS LEGACY (mantener compatibilidad) =====
    msisdn = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='Número telefónico (legacy)'
    )
    
    ip_fija = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='IP fija (legacy - usar direccion_ip)'
    )
    
    serie_plastico = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='Número de serie del plástico (legacy)'
    )
    
    proveedor = models.CharField(
        max_length=100,
        blank=True,
        help_text='Proveedor (legacy - usar operador)'
    )
    
    ubicacion_actual = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name='simcards',
        null=True,
        blank=True
    )
    
    en_custodia_de = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simcards_en_custodia',
        limit_choices_to={'rol': 'TECNICO'}
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'SIM {self.imei} ({self.operador})'
    
    class Meta:
        verbose_name_plural = 'SIM Cards'


class Modem(models.Model):
    """
    Módems para telemetría con trazabilidad completa
    
    CAMPOS VERDES (desde Excel - solo lectura para administrativo):
    - marca, modelo, imei, serie, fecha_recepcion, fecha_entrega, caja, tecnico_responsable
    
    CAMPOS AMARILLOS (administrativo modifica):
    - cliente, medidor, observaciones
    
    CAMPOS NARANJAS (ocultos para administrativo - solo admin/auditor):
    - ip, puerto, marca_secundaria, retirado, serie_secundaria, irregularidad, proyecto
    """
    
    # ===== CAMPOS VERDES (desde Excel - solo lectura) =====
    marca = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Marca del módem'
    )
    
    modelo = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Modelo del módem'
    )
    
    imei = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text='IMEI del módem (identificador único)'
    )
    
    serie = models.CharField(
        max_length=50,
        unique=True,
        help_text='Número de serie del módem'
    )
    
    fecha_recepcion = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha de recepción en bodega'
    )
    
    fecha_entrega = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha de entrega al técnico'
    )
    
    caja = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text='Número de caja de recepción'
    )
    
    tecnico_responsable = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Nombre del técnico responsable (del Excel)'
    )
    
    # ===== CAMPOS AMARILLOS (administrativo modifica) =====
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modems_asignados',
        help_text='Cliente al que está asignado el módem'
    )
    
    medidor = models.ForeignKey(
        'inventario.Medidor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modems_asociados',
        help_text='Medidor asociado a este módem'
    )
    
    observaciones = models.TextField(
        blank=True,
        default='',
        help_text='Observaciones del administrativo'
    )
    
    # ===== CAMPOS NARANJAS (ocultos para administrativo - solo admin/auditor) =====
    ip = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Dirección IP del módem'
    )
    
    puerto = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='Puerto de conexión'
    )
    
    marca_secundaria = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Marca secundaria o adicional'
    )
    
    retirado = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Información de retiro'
    )
    
    serie_secundaria = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Serie secundaria'
    )
    
    irregularidad = models.TextField(
        blank=True,
        default='',
        help_text='Irregularidades detectadas'
    )
    
    proyecto = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Proyecto asociado'
    )
    
    # ===== CAMPOS LEGACY/SISTEMA =====
    bodega = models.CharField(
        max_length=100,
        blank=True,
        help_text='Bodega de origen'
    )
    
    modulo = models.CharField(
        max_length=100,
        blank=True,
        help_text='Módulo o tipo (legacy)'
    )
    
    entregado_a = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modems_entregados',
        help_text='Usuario a quien se entregó (legacy - usar tecnico_responsable)'
    )
    
    estado_inventario = models.ForeignKey(
        EstadoInventario,
        on_delete=models.PROTECT,
        related_name='modems',
        null=True,
        blank=True
    )
    
    en_custodia_de = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modems_en_custodia'
    )
    
    ubicacion_actual = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name='modems',
        null=True,
        blank=True
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'Modem {self.serie} - {self.marca} {self.modelo}'
    
    class Meta:
        verbose_name_plural = 'Módems'
        indexes = [
            models.Index(fields=['serie']),
            models.Index(fields=['caja']),
            models.Index(fields=['estado_inventario']),
        ]


class MovimientoInventario(models.Model):
    """Registro de cambios de estado/custodia de equipos (trazabilidad)"""
    TIPO_CHOICES = [
        ('ENTREGA', 'Entrega a técnico'),
        ('RECEPCION', 'Recepción en bodega'),
        ('DEVOLUCION', 'Devolución'),
        ('INSTALACION', 'Instalación en cliente'),
        ('RETIRO', 'Retiro de cliente'),
    ]
    
    fecha_hora = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    
    origen = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name='movimientos_origen'
    )
    
    destino = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name='movimientos_destino'
    )
    
    responsable = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='movimientos_registrados'
    )
    
    observacion = models.TextField(blank=True)
    
    orden_trabajo = models.ForeignKey(
        'ordenes_trabajo.OrdenTrabajo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_inventario'
    )
    
    def __str__(self):
        return f'{self.get_tipo_display()} - {self.fecha_hora}'
    
    class Meta:
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['-fecha_hora']),
            models.Index(fields=['tipo']),
        ]


class MovimientoItem(models.Model):
    """Detalle de equipos en cada movimiento"""
    TIPO_EQUIPO_CHOICES = [
        ('MEDIDOR', 'Medidor'),
        ('SIM', 'SIM Card'),
        ('MODEM', 'Módem'),
    ]
    
    movimiento = models.ForeignKey(
        MovimientoInventario,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    tipo_equipo = models.CharField(max_length=20, choices=TIPO_EQUIPO_CHOICES)
    
    # Para vincular al equipo específico (flexibility: 3 FK opcionales)
    medidor = models.ForeignKey(Medidor, on_delete=models.SET_NULL, null=True, blank=True)
    simcard = models.ForeignKey(SimCard, on_delete=models.SET_NULL, null=True, blank=True)
    modem = models.ForeignKey(Modem, on_delete=models.SET_NULL, null=True, blank=True)
    
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    
    def __str__(self):
        return f'{self.get_tipo_equipo_display()} - {self.cantidad} unidad(es)'
    
    class Meta:
        verbose_name_plural = 'Ítems de Movimiento'


# =============================================================================
# VERIFICACIONES DE MEDIDORES (Temporal - desde MoreApp)
# =============================================================================

class VerificacionMedidor(models.Model):
    """
    Verificación de medidor recibida desde MoreApp
    Guarda temporalmente los datos del formulario hasta procesar
    """
    
    # Metadatos de MoreApp
    submission_id = models.CharField(max_length=255, unique=True, help_text="ID único del formulario en MoreApp")
    fecha_recepcion = models.DateTimeField(auto_now_add=True, help_text="Cuándo se recibió")
    
    # Datos del formulario
    num_cliente = models.CharField(max_length=100, blank=True, null=True, verbose_name="Número de Cliente")
    num_orden = models.CharField(max_length=100, blank=True, null=True, verbose_name="Número de Orden")
    direccion = models.CharField(max_length=255, blank=True, null=True, verbose_name="Dirección")
    comuna = models.CharField(max_length=100, blank=True, null=True, verbose_name="Comuna")
    resultado_visita = models.CharField(max_length=255, blank=True, null=True, verbose_name="Resultado de Visita")
    estado_medidor = models.CharField(max_length=100, blank=True, null=True, verbose_name="Estado del Medidor")
    
    # Foto (URL de MoreApp)
    foto_fachada_url = models.URLField(max_length=500, blank=True, null=True, verbose_name="URL Foto")
    
    # JSON completo
    datos_completos = models.JSONField(default=dict, blank=True, verbose_name="JSON completo")
    
    # Estado
    procesado = models.BooleanField(default=False, help_text="Si ya se procesó")
    notas = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Verificación de Medidor"
        verbose_name_plural = "Verificaciones de Medidores"
        ordering = ['-fecha_recepcion']
        
    def __str__(self):
        return f"Verificación {self.num_orden or self.submission_id[:8]} - {self.fecha_recepcion.strftime('%d/%m/%Y')}"
