from django.contrib import admin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = (
        'rut', 'nombre', 'apellido', 'nombre_interno', 'email', 'rol', 'is_active', 'is_staff', 'is_superuser'
    )
    search_fields = ('rut', 'nombre', 'apellido', 'email', 'nombre_interno')
    ordering = ('nombre_interno',)
    fieldsets = (
        (None, {'fields': ('rut', 'email', 'password')}),
        ('Información personal', {'fields': ('nombre', 'apellido', 'nombre_interno', 'rol')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('rut', 'email', 'password1', 'password2', 'nombre', 'apellido', 'nombre_interno', 'rol', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )

    # Filtro desplegable por rol
    def get_list_filter(self, request):
        from django.contrib.admin.filters import RelatedFieldListFilter
        return [
            ('rol', RelatedFieldListFilter),
            'is_active', 'is_staff', 'is_superuser'
        ]

    # Permitir borrar y editar usuarios
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff

    # Permitir cambiar contraseña desde el admin
    change_password_template = None  # Usar el template por defecto
