from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename
from django.utils import timezone


@deconstructible
class EvidenciasStorage(FileSystemStorage):
    """Almacenamiento en DELCO_INVT/Registros/Evidencias."""

    def __init__(self):
        super().__init__(
            location=settings.EVIDENCIAS_ROOT,
            base_url=settings.EVIDENCIAS_URL,
        )


evidencias_storage = EvidenciasStorage()


def evidencia_upload_to(instance, filename):
    """Ruta relativa dentro de Registros/Evidencias."""
    safe_name = get_valid_filename(filename)
    class_name = instance.__class__.__name__
    if class_name == 'InformeCliente':
        subcarpeta = 'informes'
    elif class_name == 'ComprobanteCambioMedidor':
        subcarpeta = 'comprobantes'
    elif class_name == 'AdjuntoCarga':
        subcarpeta = 'adjuntos_cargas'
    elif class_name == 'ClienteAdjunto':
        subcarpeta = 'adjuntos_clientes'
    else:
        subcarpeta = 'adjuntos'
    return f'{subcarpeta}/{timezone.now():%Y/%m}/{safe_name}'
