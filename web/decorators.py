"""
Decoradores para validación de permisos por rol de usuario.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponseForbidden


def role_required(allowed_roles):
    """
    Decorador que valida si el usuario tiene uno de los roles permitidos.
    
    Uso:
        @role_required(['ADMIN', 'ADMINISTRATIVO'])
        def mi_vista(request):
            ...
    
    Si el usuario no está autenticado → redirige a login
    Si está autenticado pero sin permiso → muestra error 403
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Si no está autenticado
            if not request.user.is_authenticated:
                messages.error(request, 'Debes iniciar sesión')
                return redirect('login')
            
            # Si su rol no está en la lista permitida
            if request.user.rol not in allowed_roles:
                messages.error(request, f'Tu rol ({request.user.rol}) no tiene acceso a esta sección')
                return HttpResponseForbidden('No tienes permisos suficientes')
            
            # Todo bien, ejecutar la vista
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_only(view_func):
    """Restricción exclusiva para ADMIN"""
    return role_required(['ADMIN'])(view_func)


def admin_or_administrativo(view_func):
    """Acceso para ADMIN o ADMINISTRATIVO"""
    return role_required(['ADMIN', 'ADMINISTRATIVO'])(view_func)


def admin_or_technical(view_func):
    """Acceso para ADMIN o TECNICO"""
    return role_required(['ADMIN', 'TECNICO'])(view_func)


def inventory_staff(view_func):
    """Acceso para ADMINISTRATIVO o ADMIN"""
    return role_required(['ADMIN', 'ADMINISTRATIVO'])(view_func)


def any_intranet_user(view_func):
    """Cualquier usuario interno autenticado con rol de la plataforma."""
    return role_required(['ADMIN', 'GERENCIA', 'ADMINISTRATIVO', 'TECNICO', 'AUDITOR'])(view_func)


def admin_or_formulario_asignado(view_func):
    """ADMIN ve todos los formularios; el resto solo los que tenga asignados."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Debes iniciar sesión')
            return redirect('login')
        if getattr(request.user, 'rol', '') == 'ADMIN':
            return view_func(request, *args, **kwargs)
        form_id = str(kwargs.get('form_id') or '')
        from integraciones.models import MoreAppFormularioAsignado
        if form_id and MoreAppFormularioAsignado.objects.filter(
            usuario=request.user, form_id=form_id
        ).exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes este formulario asignado')
        return HttpResponseForbidden('No tiene este formulario asignado')

    return wrapper


def admin_or_tiene_formulario_asignado(view_func):
    """ADMIN, o cualquier usuario con al menos un formulario MoreApp asignado."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Debes iniciar sesión')
            return redirect('login')
        if getattr(request.user, 'rol', '') == 'ADMIN':
            return view_func(request, *args, **kwargs)
        from integraciones.models import MoreAppFormularioAsignado
        if MoreAppFormularioAsignado.objects.filter(usuario=request.user).exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes formularios MoreApp asignados')
        return HttpResponseForbidden('No tiene formularios asignados')

    return wrapper
