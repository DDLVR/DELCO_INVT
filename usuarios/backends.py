from django.contrib.auth.backends import ModelBackend
from usuarios.models import Usuario


class UsuarioBackend(ModelBackend):
    """Backend personalizado para autenticar usando RUT en lugar de username"""
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Intentar encontrar el usuario por RUT (con o sin formato)
            user = Usuario.objects.get(rut=username)
        except Usuario.DoesNotExist:
            # Si no encuentra con el RUT exacto, intentar sin puntos/guiones
            rut_limpio = username.replace('.', '').replace('-', '') if username else ''
            try:
                user = Usuario.objects.get(rut=rut_limpio)
            except Usuario.DoesNotExist:
                return None
        
        # Verificar la contraseña y si el usuario está activo
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None
    
    def get_user(self, user_id):
        try:
            return Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None
