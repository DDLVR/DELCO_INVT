"""
Configuración de Django para producción en Hostingplus
"""
from .settings import *
import logging
import os

# Configurar PyMySQL como reemplazo de MySQLdb
import pymysql
pymysql.install_as_MySQLdb()

from config.env_utils import env_or_default

logger = logging.getLogger(__name__)


def _env_list(var_name, default_values=None):
    """Obtiene una lista separada por coma desde variables de entorno."""
    raw = os.environ.get(var_name, '')
    if raw:
        return [item.strip() for item in raw.split(',') if item.strip()]
    return list(default_values or [])


# SEGURIDAD
DEBUG = os.environ.get('DEBUG', 'False').strip().lower() == 'true'

# Preferir SECRET_KEY en Passenger / .env. Fallback solo para no tumbar el sitio
# tras el endurecimiento de seguridad (rotar y definir env lo antes posible).
SECRET_KEY = env_or_default(
    'SECRET_KEY',
    'delco-prod-compat-key-cambiar-en-passenger-o-dotenv',
)

# Dominios permitidos - Configuración mínima para producción
ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', [
    'inventario.delcochile.cl',
    'www.inventario.delcochile.cl',
])

# Origenes confiables para CSRF (requieren esquema http/https).
CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS', [
    'https://inventario.delcochile.cl',
    'http://inventario.delcochile.cl',
])

# Configuración para proxy reverso
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = 'Lax'  # Permite cookies cross-site en POST desde mismo dominio
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True
# Activar en Passenger cuando el proxy envía X-Forwarded-Proto correctamente:
# SECURE_SSL_REDIRECT=True
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False').strip().lower() == 'true'
# HSTS solo si SSL redirect está activo (evita forzar HTTPS antes de tiempo)
if SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = (
        os.environ.get('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True').strip().lower() == 'true'
    )
    SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'False').strip().lower() == 'true'
CSRF_COOKIE_AGE = 31449600  # 1 año en segundos

# Base de datos MySQL (Hostingplus).
# Preferir DB_* en Passenger / .env. Fallbacks = valores con los que ya corría el sitio
# (compatibilidad de arranque). Mover a env y rotar DB_PASSWORD cuando se pueda.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env_or_default('DB_NAME', 'delcochi_DelcoChile_Inventario'),
        'USER': env_or_default('DB_USER', 'delcochi_DDLVR'),
        'PASSWORD': env_or_default('DB_PASSWORD', 'Chomuske132$$'),
        'HOST': os.environ.get('DB_HOST', 'localhost') or 'localhost',
        'PORT': os.environ.get('DB_PORT', '3306') or '3306',
        'OPTIONS': {
            'init_command': "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci, sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}

# Webhook: settings.py ya define MOREAPP_WEBHOOK_SECRET (env o fallback de compatibilidad)
if not (MOREAPP_WEBHOOK_SECRET or '').strip():
    logger.error(
        'MOREAPP_WEBHOOK_SECRET vacío: el webhook /api/moreapp-webhook/ rechazará con 403.'
    )

# Archivos estáticos
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(str(BASE_DIR), 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Servir archivos estaticos directamente desde Django en Passenger.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *[mw for mw in MIDDLEWARE if mw != 'django.middleware.security.SecurityMiddleware'],
]

# Archivos multimedia
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(str(BASE_DIR), 'mediafiles')

# CORS - Configurar según tus necesidades
CORS_ALLOWED_ORIGINS = [
    "https://inventario.delcochile.cl",
    "https://www.inventario.delcochile.cl",
]

CORS_ALLOW_CREDENTIALS = True

# Seguridad adicional para HTTPS
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(str(BASE_DIR), 'logs', 'django_errors.log'),
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# Crear directorio de logs si no existe
os.makedirs(os.path.join(str(BASE_DIR), 'logs'), exist_ok=True)

# Crear directorio tmp para Passenger restarts
os.makedirs(os.path.join(str(BASE_DIR), 'tmp'), exist_ok=True)

# Sync MoreApp por navegador: corto para no chocar con Connection Timeout del hosting
MOREAPP_WEB_SYNC_MAX_SEGUNDOS = int(os.environ.get('MOREAPP_WEB_SYNC_MAX_SEGUNDOS', '30'))
MOREAPP_WEB_SYNC_MAX_ARCHIVOS = int(os.environ.get('MOREAPP_WEB_SYNC_MAX_ARCHIVOS', '40'))
MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS = os.environ.get(
    'MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS', 'true'
).strip().lower() == 'true'
MOREAPP_FIRST_SCAN_TAIL = int(os.environ.get('MOREAPP_FIRST_SCAN_TAIL', '25'))
MOREAPP_INCREMENTAL_LOOKBACK = int(os.environ.get('MOREAPP_INCREMENTAL_LOOKBACK', '1'))
# No sincronizar MoreApp dentro de cada página: evita timeout con muchos registros.
MOREAPP_AUTO_SYNC_ENABLED = os.environ.get('MOREAPP_AUTO_SYNC_ENABLED', 'false').strip().lower() == 'true'
MOREAPP_AUTO_REFRESH_SECONDS = int(os.environ.get('MOREAPP_AUTO_REFRESH_SECONDS', '0') or 0)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'delcoplata-prod-locmem',
        'TIMEOUT': 120,
        'OPTIONS': {'MAX_ENTRIES': 4000},
    }
}
