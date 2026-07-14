"""
Configuración de Django para producción en Hostingplus
"""
from .settings import *
import os

# Configurar PyMySQL como reemplazo de MySQLdb
import pymysql
pymysql.install_as_MySQLdb()


def _env_list(var_name, default_values=None):
    """Obtiene una lista separada por coma desde variables de entorno."""
    raw = os.environ.get(var_name, '')
    if raw:
        return [item.strip() for item in raw.split(',') if item.strip()]
    return list(default_values or [])

# SEGURIDAD
DEBUG = os.environ.get('DEBUG', 'False').strip().lower() == 'true'

# IMPORTANTE: Cambiar esta clave por una segura y única
SECRET_KEY = os.environ.get('SECRET_KEY', 'CAMBIAR-POR-CLAVE-SEGURA-EN-PRODUCCION')

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
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False').strip().lower() == 'true'
CSRF_COOKIE_AGE = 31449600  # 1 año en segundos

# Base de datos MySQL (Hostingplus usa MySQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'delcochi_DelcoChile_Inventario'),
        'USER': os.environ.get('DB_USER', 'delcochi_DDLVR'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'Chomuske132$$'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci, sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}

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

# Seguridad adicional para HTTPS (desactivado temporalmente para pruebas iniciales)
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
