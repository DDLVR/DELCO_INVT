"""
Configuración de Django para producción en Hostingplus

Secretos: solo Passenger (Environment variables) o archivo .env en el servidor.
Nunca commitear .env — está en .gitignore.
"""
from .settings import *
import os

from django.core.exceptions import ImproperlyConfigured

# Configurar PyMySQL como reemplazo de MySQLdb
import pymysql
pymysql.install_as_MySQLdb()

from config.env_utils import require_env as _require_env


def _env_list(var_name, default_values=None):
    """Obtiene una lista separada por coma desde variables de entorno."""
    raw = os.environ.get(var_name, '')
    if raw:
        return [item.strip() for item in raw.split(',') if item.strip()]
    return list(default_values or [])


# SEGURIDAD
DEBUG = os.environ.get('DEBUG', 'False').strip().lower() == 'true'

SECRET_KEY = _require_env('SECRET_KEY')
_PLACEHOLDER_KEYS = {
    'CAMBIAR-POR-CLAVE-SEGURA-EN-PRODUCCION',
    'cambiar-por-clave-larga-y-unica',
    'delco-prod-compat-key-cambiar-en-passenger-o-dotenv',
}
if SECRET_KEY in _PLACEHOLDER_KEYS or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured(
        'SECRET_KEY inválida o de plantilla. '
        'Definir una clave única en Passenger o en el .env del servidor '
        '(ver .env.example y docs de hosting).'
    )

# Dominios permitidos
ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', [
    'inventario.delcochile.cl',
    'www.inventario.delcochile.cl',
])

CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS', [
    'https://inventario.delcochile.cl',
    'http://inventario.delcochile.cl',
])

# Proxy / cookies
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False').strip().lower() == 'true'
if SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = (
        os.environ.get('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True').strip().lower() == 'true'
    )
    SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'False').strip().lower() == 'true'
CSRF_COOKIE_AGE = 31449600

# MySQL — obligatorio por entorno / .env del servidor (sin contraseñas en el código)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': _require_env('DB_NAME'),
        'USER': _require_env('DB_USER'),
        'PASSWORD': _require_env('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'localhost') or 'localhost',
        'PORT': os.environ.get('DB_PORT', '3306') or '3306',
        'OPTIONS': {
            'init_command': "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci, sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}

# Webhook MoreApp — obligatorio
MOREAPP_WEBHOOK_SECRET = _require_env('MOREAPP_WEBHOOK_SECRET')

# Archivos estáticos
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(str(BASE_DIR), 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *[mw for mw in MIDDLEWARE if mw != 'django.middleware.security.SecurityMiddleware'],
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(str(BASE_DIR), 'mediafiles')

CORS_ALLOWED_ORIGINS = [
    "https://inventario.delcochile.cl",
    "https://www.inventario.delcochile.cl",
]
CORS_ALLOW_CREDENTIALS = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

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

os.makedirs(os.path.join(str(BASE_DIR), 'logs'), exist_ok=True)
os.makedirs(os.path.join(str(BASE_DIR), 'tmp'), exist_ok=True)

MOREAPP_WEB_SYNC_MAX_SEGUNDOS = int(os.environ.get('MOREAPP_WEB_SYNC_MAX_SEGUNDOS', '30'))
MOREAPP_WEB_SYNC_MAX_ARCHIVOS = int(os.environ.get('MOREAPP_WEB_SYNC_MAX_ARCHIVOS', '40'))
MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS = os.environ.get(
    'MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS', 'true'
).strip().lower() == 'true'
MOREAPP_FIRST_SCAN_TAIL = int(os.environ.get('MOREAPP_FIRST_SCAN_TAIL', '25'))
MOREAPP_INCREMENTAL_LOOKBACK = int(os.environ.get('MOREAPP_INCREMENTAL_LOOKBACK', '1'))
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
