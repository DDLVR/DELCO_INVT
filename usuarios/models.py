from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager


class UsuarioManager(BaseUserManager):
    def create_user(self, rut, email, password=None, **extra_fields):
        if not rut:
            raise ValueError('El usuario debe tener un RUT')

        if not email:
            raise ValueError('El usuario debe tener un email')

        email = self.normalize_email(email)

        user = self.model(
            rut=rut,
            email=email,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, rut, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('rol', 'ADMIN')
        return self.create_user(rut, email, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    ROL_CHOICES = [
        ('ADMIN', 'Administrador'),
        ('GERENCIA', 'Gerencia'),
        ('ADMINISTRATIVO', 'Administrativo'),
        ('TECNICO', 'Técnico'),
        ('AUDITOR', 'Auditor'),
    ]

    rut = models.CharField(
        max_length=12,
        unique=True,
        help_text='RUT con guion, ejemplo: 12345678-9'
    )

    email = models.EmailField(unique=True)

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    nombre_interno = models.CharField(max_length=100)

    rol = models.CharField(
        max_length=20,
        choices=ROL_CHOICES
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'rut'
    REQUIRED_FIELDS = ['email']

    def __str__(self):
        return f'{self.rut} - {self.nombre_interno}'
