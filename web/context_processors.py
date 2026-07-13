from .moreapp_avisos import construir_aviso_moreapp


def moreapp_aviso(request):
    """Expone moreapp_aviso en todos los templates (badge sidebar / banners)."""
    return {'moreapp_aviso': construir_aviso_moreapp(request)}
