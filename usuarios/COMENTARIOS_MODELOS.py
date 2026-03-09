# 🔐 SISTEMA DE AUTENTICACIÓN - Usuarios y Roles
# ======================================================
# Modelo personalizado de Django que usa RUT como username
# Implementa RBAC (Role-Based Access Control) con 5 niveles

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager


# ============================================================
# GESTOR PERSONALIZADO DE USUARIOS
# ============================================================
class UsuarioManager(BaseUserManager):
    """
    Manager personalizado para crear usuarios con RUT como username.
    
    Casos de uso:
    - create_user(rut='12345678-9', email='user@mail.com', password='...')
    - create_superuser(rut='12345678-9', email='admin@mail.com', password='...')
    """
    
    def create_user(self, rut, email, password=None, **extra_fields):
        """
        Crea un usuario normal.
        
        Validaciones:
        - RUT es obligatorio (identificador único)
        - Email es obligatorio (contacto y recuperación)
        """
        if not rut:
            raise ValueError('El usuario debe tener un RUT')

        if not email:
            raise ValueError('El usuario debe tener un email')

        # Normaliza email (lowercase)
        email = self.normalize_email(email)

        # Crea instancia sin guardar aún
        user = self.model(
            rut=rut,
            email=email,
            **extra_fields
        )
        
        # Encripta la contraseña con pbkdf2
        user.set_password(password)
        
        # Guarda en BD
        user.save(using=self._db)
        return user

    def create_superuser(self, rut, email, password=None, **extra_fields):
        """
        Crea un superusuario (ADMIN con todos los permisos).
        
        Establece automáticamente:
        - is_staff = True (acceso al admin)
        - is_superuser = True (todos los permisos)
        - is_active = True (usuario habilitado)
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        return self.create_user(rut, email, password, **extra_fields)


# ============================================================
# MODELO USUARIO PERSONALIZADO
# ============================================================
class Usuario(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de Usuario personalizado basado en AbstractBaseUser.
    
    Reemplaza el User default de Django que usa 'username'.
    Aquí usamos 'rut' como USERNAME_FIELD.
    
    Hereda de:
    - AbstractBaseUser: Campos password, last_login
    - PermissionsMixin: Campos is_superuser, user_permissions, groups
    """
    
    # ========== DEFINICIÓN DE ROLES ==========
    ROL_CHOICES = [
        ('ADMIN', 'Administrador'),          # 👤 Control total del sistema
        ('GERENCIA', 'Gerencia'),            # 👔 Supervisión y reportes
        ('ADMINISTRATIVO', 'Administrativo'),# 📋 Gestión de órdenes
        ('TECNICO', 'Técnico'),              # 🔧 Ejecución de órdenes
        ('AUDITOR', 'Auditor'),              # 📊 Solo lectura
    ]

    # ========== CAMPOS DE IDENTIFICACIÓN ==========
    rut = models.CharField(
        max_length=12,
        unique=True,
        help_text='RUT con guion, ejemplo: 12345678-9'
    )
    # RUT único: Campo clave para login (no puede haber 2 usuarios con mismo RUT)

    email = models.EmailField(unique=True)
    # Email único: Para recuperación de contraseña y comunicaciones

    nombre = models.CharField(max_length=100)
    # Nombre del usuario (Ej: "Juan")

    apellido = models.CharField(max_length=100)
    # Apellido del usuario (Ej: "Pérez")

    nombre_interno = models.CharField(max_length=100)
    # Apodo interno usado en el sistema (Ej: "JPérez", "Juan P.")
    # Más corto para mostrar en interfaces

    # ========== CAMPOS DE AUTORIZACIÓN ==========
    rol = models.CharField(
        max_length=20,
        choices=ROL_CHOICES
    )
    # Define qué puede hacer el usuario (nivel de permisos)
    # Valores: ADMIN, GERENCIA, ADMINISTRATIVO, TECNICO, AUDITOR

    is_active = models.BooleanField(default=True)
    # Si False: usuario no puede loguearse
    # Uso: deshabilitar temporalmente sin eliminar

    is_staff = models.BooleanField(default=False)
    # Si True: usuario puede acceder a /admin/
    # Típicamente True solo para ADMIN

    # ========== CAMPOS DE AUDITORÍA ==========
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # Timestamp automático de creación (se establece 1 sola vez)

    # ========== CONFIGURACIÓN DEL MANAGER ==========
    objects = UsuarioManager()
    # Usa nuestro custom manager para create_user y create_superuser

    # ========== CONFIGURACIÓN DJANGO AUTH ==========
    USERNAME_FIELD = 'rut'
    # Campo usado para login en lugar de 'username' (default)
    # Django buscará: authenticate(username='rut_value', password='...')

    REQUIRED_FIELDS = ['email']
    # Campos requeridos al crear superuser interactivamente
    # (además de USERNAME_FIELD y password)

    # ========== MÉTODOS ==========
    def __str__(self):
        """Representación string del usuario (para admin y otros contextos)"""
        return f'{self.rut} - {self.nombre_interno}'

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['-fecha_creacion']
        # Muestra usuarios más recientes primero

    # ========== MÉTODOS DE NEGOCIO (A IMPLEMENTAR) ==========
    def puede_crear_orden(self):
        """¿Este usuario puede crear órdenes de trabajo?"""
        # Por implementar: ADMIN, GERENCIA, ADMINISTRATIVO
        return self.rol in ['ADMIN', 'GERENCIA', 'ADMINISTRATIVO']

    def puede_asignar_tecnico(self):
        """¿Este usuario puede asignar técnicos?"""
        # Por implementar: ADMIN, ADMINISTRATIVO
        return self.rol in ['ADMIN', 'ADMINISTRATIVO']

    def get_full_name(self):
        """Retorna nombre completo formateado"""
        return f'{self.nombre} {self.apellido}'

    def get_short_name(self):
        """Retorna nombre corto para UI"""
        return self.nombre_interno


# ============================================================
# CASOS DE USO DE EJEMPLO
# ============================================================
"""
# Crear usuario normal
usuario = Usuario.objects.create_user(
    rut='12345678-9',
    email='juan@empresa.cl',
    password='segura123',
    nombre='Juan',
    apellido='Pérez',
    nombre_interno='JPérez',
    rol='TECNICO'
)

# Crear administrador
admin = Usuario.objects.create_superuser(
    rut='87654321-0',
    email='admin@empresa.cl',
    password='admin123',
    nombre='Admin',
    apellido='User',
    nombre_interno='Admin'
)

# Verificar rol
if usuario.rol == 'TECNICO':
    print("Puede ejecutar órdenes")

# Buscar usuario para login
user = authenticate(username='12345678-9', password='segura123')
"""
