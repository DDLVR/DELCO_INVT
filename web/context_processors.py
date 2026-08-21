from django.urls import NoReverseMatch, reverse

from .moreapp_avisos import construir_aviso_moreapp

# Rutas fijas de respaldo: si el name no está en urls.py (deploy parcial),
# las plantillas siguen renderizando y el autocomplete apunta al path real.
_API_FALLBACKS = {
    'api_buscar_tecnicos': '/api/buscar-tecnicos/',
    'api_buscar_clientes': '/api/buscar-clientes/',
    'api_buscar_medidores': '/api/buscar-medidores/',
    'api_obtener_medidor': '/api/medidores/',
    'clientes_modificar_masivo': '/clientes/modificar-masivo/',
}


def _safe_reverse(name, fallback=None):
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback if fallback is not None else _API_FALLBACKS.get(name, '')


def moreapp_aviso(request):
    """Expone moreapp_aviso en todos los templates (badge sidebar / banners)."""
    return {'moreapp_aviso': construir_aviso_moreapp(request)}


def delco_api_urls(request):
    """
    URLs de API para autocomplete / acciones AJAX sin NoReverseMatch.
    Usar en templates: {{ delco_api.buscar_tecnicos }}
    """
    return {
        'delco_api': {
            'buscar_tecnicos': _safe_reverse('api_buscar_tecnicos'),
            'buscar_clientes': _safe_reverse('api_buscar_clientes'),
            'buscar_medidores': _safe_reverse('api_buscar_medidores'),
            'clientes_modificar_masivo': _safe_reverse('clientes_modificar_masivo'),
        }
    }


def _mtime_version(rel_path: str) -> str:
    """Versión corta basada en mtime para romper caché del navegador/CDN."""
    from django.conf import settings

    try:
        path = settings.BASE_DIR / 'static' / rel_path
        if path.is_file():
            return str(int(path.stat().st_mtime))
    except Exception:
        pass
    return '1'


def delco_static_version(request):
    """Expone delco_css_v para ?v= en app.css (producción no re-collectstatic)."""
    return {'delco_css_v': _mtime_version('css/app.css')}
