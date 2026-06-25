from django.db import models
from usuarios.models import Usuario
from config.storage import evidencias_storage, evidencia_upload_to


class EquipoTrabajo(models.Model):
    """
    Equipo/cuadrilla de técnicos que trabaja en conjunto (binomio/cuadrilla).
    """
    
    vehiculo = models.ForeignKey(
        'Vehiculo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipos'
    )
    
    responsable = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='equipos_responsable',
        limit_choices_to={'rol': 'TECNICO'}
    )
    
    miembros = models.ManyToManyField(
        Usuario,
        related_name='equipos_miembro',
        limit_choices_to={'rol': 'TECNICO'},
        help_text='Técnicos que forman parte del equipo (2 a 4 recomendado)'
    )
    
    activo = models.BooleanField(default=True)
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'Equipo: {self.responsable.nombre_interno}'
    
    class Meta:
        verbose_name_plural = 'Equipos de Trabajo'


class Vehiculo(models.Model):
    """Vehículos de transporte para técnicos"""
    
    patente = models.CharField(max_length=20, unique=True)
    modelo = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    
    ESTADO_CHOICES = [
        ('ACTIVO', 'Activo'),
        ('MANTENIMIENTO', 'En mantenimiento'),
        ('BAJA', 'Baja'),
    ]
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='ACTIVO')
    
    def __str__(self):
        return f'{self.patente} - {self.modelo}'
    
    class Meta:
        verbose_name_plural = 'Vehículos'


class Herramienta(models.Model):
    """Herramientas utilizadas en órdenes de trabajo"""
    
    codigo_interno = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    
    ESTADO_CHOICES = [
        ('DISPONIBLE', 'Disponible'),
        ('EN_USO', 'En uso'),
        ('REPARACION', 'En reparación'),
        ('BAJA', 'Baja'),
    ]
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='DISPONIBLE')
    observacion = models.TextField(blank=True)
    
    def __str__(self):
        return f'{self.codigo_interno} - {self.nombre}'
    
    class Meta:
        verbose_name_plural = 'Herramientas'


class OrdenHerramientaRequerida(models.Model):
    """Herramientas específicas necesarias para una OT"""
    
    orden = models.ForeignKey(
        'OrdenTrabajo',
        on_delete=models.CASCADE,
        related_name='herramientas_requeridas'
    )
    
    herramienta = models.ForeignKey(
        Herramienta,
        on_delete=models.PROTECT,
        related_name='ordenes_uso'
    )
    
    cantidad = models.PositiveIntegerField(default=1)
    obligatoria = models.BooleanField(default=True)
    
    def __str__(self):
        return f'{self.herramienta.nombre} x{self.cantidad}'
    
    class Meta:
        verbose_name_plural = 'Herramientas Requeridas'
        unique_together = ('orden', 'herramienta')


class OrdenTrabajo(models.Model):
    """Orden de trabajo con flujo operativo"""

    ESTADO_CHOICES = [
        ('CREADA', 'Creada'),
        ('ASIGNADA', 'Asignada'),
        ('EN_EJECUCION', 'En ejecución'),
        ('REASIGNADA', 'Reasignada'),
        ('MANTENIMIENTO', 'Mantenimiento'),
        ('REALIZADA', 'Realizada'),
        ('REALIZADA_PENDIENTE_COMPROBACION', 'Realizada - Pendiente comprobación'),
        ('PENDIENTE_VALIDACION', 'Pendiente validación'),
        ('VALIDADA', 'Validada'),
        ('OBSERVADA', 'Observada'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada'),
    ]

    ESTADOS_ABIERTOS = {
        'CREADA', 'ASIGNADA', 'EN_EJECUCION', 'REASIGNADA', 'MANTENIMIENTO',
    }

    TIPO_TRABAJO_CHOICES = [
        ('INSTALACION', 'Instalación'),
        ('CAMBIO', 'Cambio de equipo'),
        ('RETIRO', 'Retiro'),
        ('MANTENCION', 'Mantención'),
        ('REPARACION', 'Reparación'),
        ('INSPECCION', 'Inspección'),
        ('CONFIGURACION', 'Configuración'),
        ('OTRO', 'Otro'),
    ]

    # Información básica
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    tipo_trabajo = models.CharField(
        max_length=30,
        choices=TIPO_TRABAJO_CHOICES,
        default='INSTALACION',
        help_text='Tipo de trabajo a realizar'
    )
    
    # Referencia al cliente
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
        related_name='ordenes',
        null=True,
        blank=True
    )

    # Equipos utilizados en el trabajo
    medidor = models.ForeignKey(
        'inventario.Medidor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes',
        help_text='Medidor instalado/cambiado/retirado'
    )
    
    simcard = models.ForeignKey(
        'inventario.SimCard',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes',
        help_text='SIM Card utilizada en el trabajo'
    )
    
    modem = models.ForeignKey(
        'inventario.Modem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes',
        help_text='Módem instalado/cambiado/retirado'
    )

    # Observaciones del trabajo
    observaciones_tecnicas = models.TextField(
        blank=True,
        help_text='Observaciones del técnico durante la ejecución'
    )

    estado = models.CharField(
        max_length=40,
        choices=ESTADO_CHOICES,
        default='CREADA'
    )

    # Asignación de personal (opcional al crear/importar; se asigna después)
    tecnico_responsable = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='ordenes_responsable',
        limit_choices_to={'rol': 'TECNICO'},
        null=True,
        blank=True,
    )
    
    equipo_trabajo = models.ForeignKey(
        EquipoTrabajo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes'
    )

    tecnicos_equipo = models.ManyToManyField(
        Usuario,
        related_name='ordenes_equipo',
        limit_choices_to={'rol': 'TECNICO'},
        blank=True,
        help_text='Otros técnicos que participan (además del responsable)'
    )

    # Auditoría
    creada_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='ordenes_creadas'
    )
    
    validada_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes_validadas',
        limit_choices_to={'rol': 'SUPERVISOR'}
    )

    # Fechas
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_inicio_ejecucion = models.DateTimeField(
        null=True, 
        blank=True,
        help_text='Fecha y hora en que el técnico inició el trabajo'
    )
    fecha_fin_ejecucion = models.DateTimeField(
        null=True, 
        blank=True,
        help_text='Fecha y hora en que el técnico finalizó el trabajo'
    )
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    fecha_validacion = models.DateTimeField(null=True, blank=True)

    # Control
    tecnico_solicito_reasignacion = models.BooleanField(default=False)
    ediciones_tecnico = models.IntegerField(
        default=0,
        help_text='Número de veces que el técnico ha editado la orden (máximo 2)'
    )
    
    observacion_validacion = models.TextField(
        blank=True,
        help_text='Observaciones si la validación rechaza la OT'
    )

    alerta_duplicado = models.BooleanField(
        default=False,
        help_text='Posible trabajo duplicado para el mismo cliente en los últimos 14 días',
    )
    descripcion_alerta_duplicado = models.TextField(
        blank=True,
        help_text='Detalle de la alerta de posible duplicidad',
    )

    def __str__(self):
        return f'OT #{self.id} - {self.titulo}'
    
    def puede_cambiar_estado(self, usuario, nuevo_estado):
        """Valida si usuario puede cambiar a nuevo_estado"""

        # ADMIN y ADMINISTRATIVO pueden todo
        if usuario.rol in ['ADMIN', 'ADMINISTRATIVO']:
            return True

        # TECNICO responsable (permisos limitados)
        if usuario.rol == 'TECNICO' and usuario == self.tecnico_responsable:
            # Puede cambiar a EN_EJECUCION
            if nuevo_estado == 'EN_EJECUCION':
                return True
            # Puede marcar como realizada o finalizada
            if nuevo_estado in ['REALIZADA', 'FINALIZADA']:
                return True
            # Puede solicitar reasignación (una sola vez)
            if nuevo_estado in ['REASIGNADA', 'MANTENIMIENTO']:
                if not self.tecnico_solicito_reasignacion:
                    return True
        
        # SUPERVISOR puede validar
        if usuario.rol == 'SUPERVISOR' and nuevo_estado in ['VALIDADA', 'OBSERVADA']:
            return True

        return False

    def cambiar_estado(self, usuario, nuevo_estado, razon=''):
        """Cambia estado validando permisos"""
        if not self.puede_cambiar_estado(usuario, nuevo_estado):
            return {
                'success': False,
                'mensaje': f'No tienes permiso para cambiar a {nuevo_estado}'
            }

        self.estado = nuevo_estado

        from django.utils import timezone

        if nuevo_estado in ['REALIZADA', 'FINALIZADA']:
            if not self.fecha_fin_ejecucion:
                self.fecha_fin_ejecucion = timezone.now()
        if nuevo_estado == 'FINALIZADA':
            self.fecha_cierre = timezone.now()
        if nuevo_estado == 'ASIGNADA' and not self.fecha_asignacion:
            self.fecha_asignacion = timezone.now()

        if nuevo_estado in ['REASIGNADA', 'MANTENIMIENTO']:
            self.tecnico_solicito_reasignacion = True

        if nuevo_estado == 'VALIDADA':
            self.validada_por = usuario
            from django.utils import timezone
            self.fecha_validacion = timezone.now()

        self.save()

        return {
            'success': True,
            'mensaje': f'Estado actualizado a {nuevo_estado}'
        }

    def puede_editar_observaciones_tecnicas(self, usuario):
        """Admin/administrativo o técnico responsable pueden editar observaciones en cualquier estado."""
        if usuario.rol in ['ADMIN', 'ADMINISTRATIVO']:
            return True
        if usuario.rol == 'TECNICO' and usuario == self.tecnico_responsable:
            return True
        return False

    def puede_tecnico_editar(self, usuario):
        """Valida si un técnico puede editar la orden (máximo 2 veces)"""
        # Solo el técnico responsable puede editar
        if usuario.rol != 'TECNICO' or usuario != self.tecnico_responsable:
            return False, "No eres responsable de esta orden"
        
        # Máximo 2 ediciones
        if self.ediciones_tecnico >= 2:
            return False, "Has alcanzado el máximo de 2 ediciones permitidas"
        
        # Solo puede editar si está EN_EJECUCION
        if self.estado != 'EN_EJECUCION':
            return False, "Solo puedes editar órdenes en ejecución"
        
        return True, "Puedes editar esta orden"

    def incrementar_ediciones_tecnico(self):
        """Incrementa el contador de ediciones del técnico"""
        self.ediciones_tecnico += 1
        self.save()

    class Meta:
        verbose_name = 'Orden de Trabajo'
        verbose_name_plural = 'Órdenes de Trabajo'
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['estado']),
            models.Index(fields=['tecnico_responsable']),
            models.Index(fields=['cliente']),
            models.Index(fields=['-fecha_creacion']),
        ]


class AdjuntoOrden(models.Model):
    """Evidencias, fotos, FPTs adjuntos a una orden"""
    
    TIPO_CHOICES = [
        ('FOTO', 'Fotografía'),
        ('FPT', 'FPT (MoreApp)'),
        ('PDF', 'PDF'),
        ('OTRO', 'Otro'),
    ]
    
    orden = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name='adjuntos'
    )
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    
    nombre_archivo = models.CharField(max_length=255)
    
    archivo = models.FileField(
        upload_to=evidencia_upload_to,
        storage=evidencias_storage,
        help_text='Archivo subido en Registros/Evidencias',
    )
    
    url_externa = models.URLField(
        blank=True,
        help_text='URL remota si viene de MoreApp u otro servicio'
    )
    
    subido_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        related_name='adjuntos_subidos'
    )
    
    fecha_hora = models.DateTimeField(auto_now_add=True)
    
    hash_archivo = models.CharField(
        max_length=64,
        blank=True,
        help_text='Hash SHA256 para evitar duplicados'
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Metadata adicional (de MoreApp u otra integración)'
    )
    
    def __str__(self):
        return f'{self.nombre_archivo} - OT #{self.orden.id}'
    
    class Meta:
        verbose_name_plural = 'Adjuntos de Órdenes'
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['orden']),
            models.Index(fields=['tipo']),
        ]


class InformeCliente(models.Model):
    """Informes PDF de clientes vinculados a órdenes de trabajo."""

    ORIGEN_CHOICES = [
        ('MANUAL', 'Carga manual'),
        ('MOREAPP', 'MoreApp'),
        ('SISTEMA', 'Sistema'),
    ]

    orden = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name='informes',
        null=True,
        blank=True,
    )
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
        related_name='informes',
    )
    nombre_archivo = models.CharField(max_length=255)
    archivo = models.FileField(
        upload_to=evidencia_upload_to,
        storage=evidencias_storage,
        help_text='PDF del informe en Registros/Evidencias',
    )
    subido_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_subidos',
    )
    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default='MANUAL')
    registro_moreapp = models.ForeignKey(
        'IntegracionMoreApp',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_generados',
    )
    fecha_subida = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.nombre_archivo} — {self.cliente.numero_cliente}'

    class Meta:
        verbose_name = 'Informe de Cliente'
        verbose_name_plural = 'Informes de Clientes'
        ordering = ['-fecha_subida']


class IntegracionMoreApp(models.Model):
    """
    Registro de sincronizaciones con MoreApp para trazabilidad
    """
    
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PROCESANDO', 'Procesando'),
        ('PROCESADO', 'Procesado'),
        ('EXITOSO', 'Exitoso'),
        ('ERROR', 'Error'),
        ('ERROR_JSON', 'Error - JSON inválido'),
        ('ERROR_LECTURA', 'Error - Lectura'),
        ('DUPLICADO', 'Duplicado'),
        ('ALERTA_REVISION', 'Alerta - Revisión requerida'),
    ]
    
    orden = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sincronizaciones_moreapp'
    )
    
    moreapp_submission_id = models.CharField(
        max_length=255,
        unique=True,
        help_text='ID único del submission de MoreApp'
    )
    
    estado_sincronizacion = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE'
    )
    
    datos_recibidos = models.JSONField(
        default=dict,
        help_text='Payload completo recibido desde MoreApp'
    )
    
    datos_procesados = models.JSONField(
        default=dict,
        blank=True,
        help_text='Datos extraídos y procesados'
    )
    
    mensaje_error = models.TextField(
        blank=True,
        help_text='Mensaje de error si la sincronización falló'
    )
    
    fecha_recepcion = models.DateTimeField(auto_now_add=True)
    fecha_procesamiento = models.DateTimeField(null=True, blank=True)
    
    procesado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sincronizaciones_procesadas'
    )
    
    # Flags para actualización automática
    actualizo_cliente = models.BooleanField(default=False)
    actualizo_equipos = models.BooleanField(default=False)
    creo_adjuntos = models.BooleanField(default=False)

    # Campos para integración por lectura directa de carpetas
    ruta_carpeta = models.CharField(
        max_length=500,
        blank=True,
        help_text='Ruta local de la carpeta correlativa del registro'
    )
    numero_correlativo = models.IntegerField(
        null=True,
        blank=True,
        help_text='Número de carpeta correlativa MoreApp (1, 2, 3, ...)'
    )
    nombre_formulario = models.CharField(
        max_length=255,
        blank=True,
        help_text='Nombre del formulario (info.formName del JSON)'
    )
    alerta_doble_trabajo = models.BooleanField(
        default=False,
        help_text='True si se detectó posible trabajo duplicado al mismo cliente'
    )
    descripcion_alerta = models.TextField(
        blank=True,
        help_text='Descripción del motivo de la alerta de doble trabajo'
    )

    # --- Revisión operativa (Punto 8) ---
    ESTADO_REVISION_CHOICES = [
        ('PENDIENTE', 'Pendiente de revisión'),
        ('CON_ADVERTENCIA', 'Con advertencia'),
        ('REVISADO', 'Revisado OK'),
        ('DESCARTADO', 'Descartado'),
    ]
    estado_revision = models.CharField(
        max_length=20,
        choices=ESTADO_REVISION_CHOICES,
        default='PENDIENTE',
        db_index=True,
        help_text='Estado de revisión operativa del registro',
    )

    def __str__(self):
        return f'MoreApp {self.moreapp_submission_id} - {self.estado_sincronizacion}'

    class Meta:
        verbose_name = 'Integración MoreApp'
        verbose_name_plural = 'Integraciones MoreApp'
        ordering = ['-fecha_recepcion']
        indexes = [
            models.Index(fields=['moreapp_submission_id']),
            models.Index(fields=['estado_sincronizacion']),
            models.Index(fields=['-fecha_recepcion']),
            models.Index(fields=['alerta_doble_trabajo']),
            models.Index(fields=['estado_revision']),
        ]

