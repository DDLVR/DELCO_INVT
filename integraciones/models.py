# Preferencias de catálogo MoreApp API (por usuario).
# El registro operativo de MoreApp sigue en ordenes_trabajo.IntegracionMoreApp.

from django.conf import settings
from django.db import models


class MoreAppFormularioOculto(models.Model):
    """Formulario del catálogo API que un usuario oculta de su vista."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moreapp_formularios_ocultos",
    )
    form_id = models.CharField(max_length=80)
    form_name = models.CharField(max_length=255, blank=True)
    fecha_oculto = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("usuario", "form_id")
        verbose_name = "Formulario MoreApp oculto"
        verbose_name_plural = "Formularios MoreApp ocultos"

    def __str__(self):
        return "%s · %s" % (self.usuario_id, self.form_name or self.form_id)


class MoreAppFormularioAsignado(models.Model):
    """Formulario MoreApp que un administrador asigna a un usuario de la intranet."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moreapp_formularios_asignados",
    )
    form_id = models.CharField(max_length=80)
    form_name = models.CharField(max_length=255, blank=True)
    asignado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moreapp_formularios_asignados_por_mi",
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("usuario", "form_id")
        verbose_name = "Formulario MoreApp asignado"
        verbose_name_plural = "Formularios MoreApp asignados"
        ordering = ["form_name", "form_id"]

    def __str__(self):
        return "%s · %s" % (self.usuario_id, self.form_name or self.form_id)


class MoreAppFuenteInterna(models.Model):
    """Data source de MoreApp elegida para copiarse a la intranet. El resto no se guarda."""

    datasource_id = models.CharField(max_length=80, unique=True)
    nombre = models.CharField(max_length=255)
    columnas = models.JSONField(default=list, blank=True)
    filas_moreapp = models.PositiveIntegerField(null=True, blank=True)
    notas = models.CharField(max_length=255, blank=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moreapp_fuentes_internas",
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_importacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Fuente MoreApp interna"
        verbose_name_plural = "Fuentes MoreApp internas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre or self.datasource_id


class MoreAppFuenteFila(models.Model):
    """Fila local de una fuente MoreApp guardada en la intranet."""

    fuente = models.ForeignKey(
        MoreAppFuenteInterna,
        on_delete=models.CASCADE,
        related_name="filas",
    )
    entry_id = models.CharField(max_length=120)
    valores = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Fila de fuente MoreApp"
        verbose_name_plural = "Filas de fuentes MoreApp"
        unique_together = ("fuente", "entry_id")
        indexes = [
            models.Index(fields=["fuente", "entry_id"]),
        ]

    def __str__(self):
        return "%s · %s" % (self.fuente_id, self.entry_id)


class MoreAppGrupoAlias(models.Model):
    """Nombre visible en la intranet para un grupo MoreApp (la API v1.0 no envía el nombre)."""

    group_id = models.CharField(max_length=80, unique=True)
    nombre = models.CharField(max_length=120)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moreapp_grupos_nombrados",
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Alias de grupo MoreApp"
        verbose_name_plural = "Alias de grupos MoreApp"

    def __str__(self):
        return "%s · %s" % (self.nombre, self.group_id)


class MoreAppCuentaTecnico(models.Model):
    """Cruce manual: un correo MoreApp queda asignado a un técnico de la data source Técnicos."""

    email = models.EmailField(unique=True)
    moreapp_user_id = models.CharField(max_length=80, blank=True)
    moreapp_nombre = models.CharField(max_length=255, blank=True)
    tecnico_entry_id = models.CharField(max_length=80, unique=True)
    tecnico_nombre = models.CharField(max_length=255)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moreapp_cuentas_enlazadas",
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cuenta MoreApp de técnico"
        verbose_name_plural = "Cuentas MoreApp de técnicos"
        ordering = ["email"]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.tecnico_entry_id = (self.tecnico_entry_id or "").strip()
        self.tecnico_nombre = (self.tecnico_nombre or "").strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return "%s · %s" % (self.email, self.tecnico_nombre or self.tecnico_entry_id)


class MoreAppTareaEnviada(models.Model):
    """Tarea creada en MoreApp desde la intranet (aviso en la app, no por correo)."""

    ESTADO_ERROR = "ERROR"
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_ASIGNADA = "ASIGNADA"
    ESTADO_COMPLETADA = "COMPLETADA"
    ESTADO_CHOICES = [
        (ESTADO_ERROR, "Error de envío"),
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_ASIGNADA, "Asignada"),
        (ESTADO_COMPLETADA, "Completada"),
    ]

    TIPO_TRABAJO_CHOICES = [
        ("INSTALACION", "Instalación"),
        ("CAMBIO", "Cambio de equipo"),
        ("RETIRO", "Retiro"),
        ("MANTENCION", "Mantención"),
        ("REPARACION", "Reparación"),
        ("INSPECCION", "Inspección"),
        ("CONFIGURACION", "Configuración"),
        ("OTRO", "Otro"),
    ]

    form_id = models.CharField(max_length=80)
    form_name = models.CharField(max_length=255, blank=True)
    task_id = models.CharField(max_length=80, blank=True)
    titulo = models.CharField(max_length=200, blank=True)
    tipo_trabajo = models.CharField(
        max_length=30,
        choices=TIPO_TRABAJO_CHOICES,
        blank=True,
        db_index=True,
    )
    cliente = models.ForeignKey(
        "clientes.Cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_moreapp",
    )
    proyecto_carga_administrativa = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
    )
    observaciones = models.TextField(blank=True)
    mensaje = models.CharField(max_length=500)
    destinatarios = models.JSONField(default=list, blank=True)
    grupos = models.JSONField(default=list, blank=True)
    envio = models.CharField(max_length=20, default="IMMEDIATE")
    programada_para = models.DateTimeField(null=True, blank=True)
    fecha_limite = models.DateTimeField(null=True, blank=True)
    ubicacion = models.CharField(max_length=255, blank=True)
    latitud = models.CharField(max_length=40, blank=True)
    longitud = models.CharField(max_length=40, blank=True)
    datos_precarga = models.JSONField(default=dict, blank=True)
    cuenta = models.CharField(max_length=80, blank=True, db_index=True)
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
        db_index=True,
    )
    fecha_asignacion = models.DateTimeField(null=True, blank=True)
    fecha_completado = models.DateTimeField(null=True, blank=True)
    ultima_sync = models.DateTimeField(null=True, blank=True)
    integracion = models.ForeignKey(
        "ordenes_trabajo.IntegracionMoreApp",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_moreapp",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moreapp_tareas_enviadas",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Tarea MoreApp enviada"
        verbose_name_plural = "Tareas MoreApp enviadas"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["estado", "-fecha_creacion"]),
            models.Index(fields=["form_id", "estado"]),
        ]

    def __str__(self):
        return "%s · %s" % (self.form_name or self.form_id, self.mensaje[:40])


class MoreAppTareaEvento(models.Model):
    """Línea de tiempo append-only del ciclo de una tarea MoreApp."""

    TIPO_CREADA = "CREADA"
    TIPO_ASIGNADA = "ASIGNADA"
    TIPO_COMPLETADA = "COMPLETADA"
    TIPO_ERROR_ENVIO = "ERROR_ENVIO"
    TIPO_CHOICES = [
        (TIPO_CREADA, "Creada"),
        (TIPO_ASIGNADA, "Asignada"),
        (TIPO_COMPLETADA, "Completada"),
        (TIPO_ERROR_ENVIO, "Error de envío"),
    ]
    ORIGEN_INTRANET = "intranet"
    ORIGEN_API = "api"
    ORIGEN_INFORME = "informe"
    ORIGEN_CHOICES = [
        (ORIGEN_INTRANET, "Intranet"),
        (ORIGEN_API, "API MoreApp"),
        (ORIGEN_INFORME, "Informe MoreApp"),
    ]

    tarea = models.ForeignKey(
        MoreAppTareaEnviada,
        on_delete=models.CASCADE,
        related_name="eventos",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    en = models.DateTimeField(auto_now_add=True)
    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default=ORIGEN_INTRANET)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Evento de tarea MoreApp"
        verbose_name_plural = "Eventos de tareas MoreApp"
        ordering = ["en", "id"]
        indexes = [
            models.Index(fields=["tarea", "tipo"]),
        ]

    def __str__(self):
        return "%s · %s" % (self.tarea_id, self.tipo)


class MoreAppTareaAlerta(models.Model):
    """Alerta de creación o completado: personal al creador y broadcast al navbar."""

    TIPO_CREACION = "CREACION"
    TIPO_COMPLETADO = "COMPLETADO"
    TIPO_CHOICES = [
        (TIPO_CREACION, "Tarea creada"),
        (TIPO_COMPLETADO, "Tarea completada"),
    ]

    tarea = models.ForeignKey(
        MoreAppTareaEnviada,
        on_delete=models.CASCADE,
        related_name="alertas",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moreapp_tareas_alertas",
    )
    broadcast = models.BooleanField(default=False, db_index=True)
    leida_en = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alerta de tarea MoreApp"
        verbose_name_plural = "Alertas de tareas MoreApp"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["broadcast", "leida_en"]),
            models.Index(fields=["usuario", "leida_en"]),
        ]

    def __str__(self):
        return "%s · %s" % (self.tipo, self.tarea_id)
