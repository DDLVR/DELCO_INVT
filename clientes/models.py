from django.db import models


# PDF punto 4 — disponible como constante de módulo (views/validators)
ESTADO_RESTRICCION_CHOICES = [
    ('', 'Sin restricción'),
    ('IP_BLOQUEADA', 'IP bloqueada'),
    ('IP_FUERA_SERVICIO', 'IP fuera de servicio'),
    ('IP_EN_REVISION', 'IP en revisión'),
    ('CERRADO', 'Cerrado'),
    ('DESHABITADO', 'Deshabitado'),
    ('NO_PERMITE', 'No permite acceso'),
]
ESTADOS_RESTRICCION_IP = {'IP_BLOQUEADA', 'IP_FUERA_SERVICIO', 'IP_EN_REVISION'}
ESTADOS_RESTRICCION_VISITA = {'CERRADO', 'DESHABITADO', 'NO_PERMITE'}


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

    empresa = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Empresa asociada al cliente, si corresponde'
    )

    ESTADO_TELEMETRIA_CHOICES = [
        ('OPERATIVO', 'Operativo'),
        ('SIN_COMUNICACION', 'Sin comunicación'),
        ('NO_COMUNICA', 'No comunica'),
        ('SIN_MEDIDOR', 'Sin medidor'),
        ('OTRO', 'Otro'),
    ]

    estado_telemetria = models.CharField(
        max_length=30,
        choices=ESTADO_TELEMETRIA_CHOICES,
        default='OPERATIVO',
        help_text='Estado actual de la telemetría del cliente'
    )

    ESTADO_SISTEMA_EXTERNO_CHOICES = [
        ('ACTUALIZADO', 'Actualizado'),
        ('PENDIENTE', 'Pendiente de actualización'),
        ('SIN_REGISTRO', 'Sin registro'),
    ]

    estado_stb = models.CharField(
        max_length=20,
        choices=ESTADO_SISTEMA_EXTERNO_CHOICES,
        default='SIN_REGISTRO',
        help_text='Estado de actualización en StarBeat (STB)'
    )

    estado_sci4 = models.CharField(
        max_length=20,
        choices=ESTADO_SISTEMA_EXTERNO_CHOICES,
        default='SIN_REGISTRO',
        help_text='Estado de actualización en SCi4'
    )

    sim_operador = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Operador de la SIM instalada'
    )

    sim_iccid = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='ICCID o identificador de la SIM'
    )

    sim_abonado = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='Número de abonado de la SIM'
    )

    ESTADO_SIM_CHOICES = [
        ('OPERATIVA', 'Operativa'),
        ('SIN_DATOS', 'Sin datos'),
        ('DANADA', 'Dañada'),
        ('SIN_COBERTURA', 'Sin cobertura'),
        ('SIN_IP', 'Sin IP'),
        ('OTRO', 'Otro'),
    ]

    sim_estado = models.CharField(
        max_length=20,
        choices=ESTADO_SIM_CHOICES,
        blank=True,
        null=True,
        help_text='Estado operativo de la SIM'
    )

    # PDF punto 4: IP bloqueada/fuera de servicio/en revisión y antecedentes de visita
    ESTADO_RESTRICCION_CHOICES = ESTADO_RESTRICCION_CHOICES
    ESTADOS_RESTRICCION_IP = ESTADOS_RESTRICCION_IP
    ESTADOS_RESTRICCION_VISITA = ESTADOS_RESTRICCION_VISITA

    estado_restriccion = models.CharField(
        max_length=30,
        choices=ESTADO_RESTRICCION_CHOICES,
        blank=True,
        default='',
        help_text='Restricción operativa del cliente/IP (PDF punto 4)',
    )
    justificacion_restriccion = models.TextField(
        blank=True,
        default='',
        help_text='Motivo obligatorio cuando hay restricción (bloqueada, fuera de servicio, deshabitado, etc.)',
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

    fecha_eliminacion = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Fecha de soft-delete (activo=False)',
    )
    eliminado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clientes_eliminados',
    )
    
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


class ClienteProyectoHistorial(models.Model):
    """
    Historial de proyectos asociados a un cliente.
    El proyecto actual queda en Cliente.proyecto; aquí se guarda la secuencia
    de cambios (cuándo entró y cuándo salió de cada proyecto).
    """

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='proyectos_historial',
    )
    proyecto = models.CharField(max_length=255)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Cuándo dejó de ser el proyecto actual (cambio a otro / cierre). Vacío = aún vigente o sin cierre registrado',
    )
    vigente = models.BooleanField(
        default=True,
        help_text='True = proyecto actual del cliente',
    )
    cambiado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cambios_proyecto_cliente',
    )
    motivo = models.CharField(max_length=255, blank=True, default='')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Historial de proyecto del cliente'
        verbose_name_plural = 'Historial de proyectos de clientes'
        ordering = ['-fecha_inicio', '-id']
        indexes = [
            # Nombres fijos (iguales a 0010) para evitar RenameIndex en hosting.
            models.Index(fields=['cliente', 'vigente'], name='clientes_cl_cliente_6a0f0f_idx'),
            models.Index(fields=['proyecto'], name='clientes_cl_proyect_7b1c2d_idx'),
        ]

    def __str__(self):
        estado = 'vigente' if self.vigente else 'cerrado'
        return f'{self.cliente_id} · {self.proyecto} ({estado})'
