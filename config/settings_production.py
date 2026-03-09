"""
Configuración de Django para producción en Hostingplus
"""
from .settings import *
import os

# Configurar PyMySQL como reemplazo de MySQLdb
import pymysql
pymysql.install_as_MySQLdb()

# SEGURIDAD
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# IMPORTANTE: Cambiar esta clave por una segura y única
SECRET_KEY = os.environ.get('SECRET_KEY', 'CAMBIAR-POR-CLAVE-SEGURA-EN-PRODUCCION')

# Dominios permitidos - Configuración mínima para producción
ALLOWED_HOSTS = [
    'inventario.delcochile',
    'www.inventario.delcochile',  # opcional, si tienes subdominio
]

# Si existe variable de entorno, agregarla también
env_hosts = os.environ.get('ALLOWED_HOSTS', '')
if env_hosts:
    ALLOWED_HOSTS.extend([h.strip() for h in env_hosts.split(',') if h.strip()])

# Configuración para proxy reverso
USE_X_FORWARDED_HOST = True

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
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}

# Archivos estáticos
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Archivos multimedia
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'mediafiles')

# CORS - Configurar según tus necesidades
CORS_ALLOWED_ORIGINS = [
    "https://inventario.delcochile",
    "https://www.inventario.delcochile",  # opcional, si tienes subdominio
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
            'filename': os.path.join(BASE_DIR, 'logs', 'django_errors.log'),
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}

# Crear directorio de logs si no existe
os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)
