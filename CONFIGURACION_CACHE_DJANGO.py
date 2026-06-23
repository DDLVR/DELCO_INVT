# ═════════════════════════════════════════════════════════════════
# DELCO INVT - Configuración de Cache para Django
# Agregar este código a: config/settings.py (al final del archivo)
# ═════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════
# 1. CONFIGURACIÓN DE CACHE
# ═════════════════════════════════════════════════════════════════

# Opciones: Desarrollo vs Producción
if DEBUG:
    # DESARROLLO: Cache local en memoria (LocMemCache)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'delco-inventario-cache',
            'OPTIONS': {
                'MAX_ENTRIES': 10000,
                'CULL_FREQUENCY': 3,
            },
            'KEY_PREFIX': 'delco',
            'VERSION': 1,
            'TIMEOUT': 600,  # 10 minutos por defecto
        }
    }
else:
    # PRODUCCIÓN: Redis (más eficiente)
    # Requiere: pip install django-redis
    try:
        CACHES = {
            'default': {
                'BACKEND': 'django_redis.cache.RedisCache',
                'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
                'OPTIONS': {
                    'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                    'CONNECTION_POOL_CLASS': 'redis.BlockingConnectionPool',
                    'CONNECTION_POOL_CLASS_KWARGS': {
                        'max_connections': 50,
                        'timeout': 20
                    },
                    'SOCKET_CONNECT_TIMEOUT': 5,
                    'SOCKET_TIMEOUT': 5,
                    'IGNORE_EXCEPTIONS': True,  # Fallar elegantemente si Redis cae
                }
            }
        }
    except:
        # Fallback: Cache local si Redis no está disponible
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'delco-fallback',
            }
        }

# ═════════════════════════════════════════════════════════════════
# 2. MIDDLEWARE DE CACHE
# ═════════════════════════════════════════════════════════════════

# Reemplazar tu MIDDLEWARE existente con este (orden es importante):
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    
    # ← GZIP MIDDLEWARE (comprimir respuestas)
    'django.middleware.gzip.GZipMiddleware',
    
    # ← CACHE MIDDLEWARE (parte 1)
    'django.middleware.cache.UpdateCacheMiddleware',
    
    # Middleware estándar
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    
    # ← CACHE MIDDLEWARE (parte 2 - va aquí!)
    'django.middleware.cache.FetchFromCacheMiddleware',
    
    # Middleware personalizado
    'web.middleware.AbsoluteSessionTimeoutMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ═════════════════════════════════════════════════════════════════
# 3. CONFIGURACIÓN DE TIEMPOS DE CACHE
# ═════════════════════════════════════════════════════════════════

# Cache de página completa (middleware)
CACHE_MIDDLEWARE_SECONDS = 600  # 10 minutos

# Cache para vistas específicas
CACHE_TIMEOUTS = {
    'default': 600,           # 10 minutos
    'short': 300,             # 5 minutos
    'medium': 1800,           # 30 minutos
    'long': 3600,             # 1 hora
    'very_long': 86400,       # 1 día
    'static_assets': 604800,  # 1 semana
}

# ═════════════════════════════════════════════════════════════════
# 4. GZIP COMPRESSION
# ═════════════════════════════════════════════════════════════════

# Tamaño mínimo para comprimir
GZIP_MIN_SIZE_BYTES = 860  # ~1KB

# Comprimir tipos MIME específicos
GZIP_SUPPORTED_TYPES = (
    'text/html',
    'text/plain',
    'text/css',
    'text/javascript',
    'application/javascript',
    'application/x-javascript',
    'application/json',
    'application/xml',
    'application/xhtml+xml',
)

# ═════════════════════════════════════════════════════════════════
# 5. SECURITY HEADERS (Producción)
# ═════════════════════════════════════════════════════════════════

if not DEBUG:
    # HTTPS y seguridad
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    
    # HSTS (HTTP Strict Transport Security)
    SECURE_HSTS_SECONDS = 31536000  # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Otros headers de seguridad
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
        'script-src': ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "code.jquery.com"),
        'style-src': ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net"),
        'img-src': ("'self'", "data:", "https:"),
        'font-src': ("'self'", "cdn.jsdelivr.net"),
    }

# ═════════════════════════════════════════════════════════════════
# 6. CONFIGURATION PARA STATICS CON VERSIONADO
# ═════════════════════════════════════════════════════════════════

# Habilitar almacenamiento de static files versionados
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# URLs de static files versionadas automáticamente
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'  # Para producción

# Media files (uploads de usuarios)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ═════════════════════════════════════════════════════════════════
# 7. HEADERS POR DEFECTO
# ═════════════════════════════════════════════════════════════════

# Headers personalizados para todas las respuestas
DEFAULT_RESPONSE_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
}

# ═════════════════════════════════════════════════════════════════
# 8. EXCLUSIONES DE CACHE (rutas que NO se cachean)
# ═════════════════════════════════════════════════════════════════

# URLs que NO se cachean (sensibles)
CACHE_EXCLUDE_PATTERNS = [
    '/api/auth/',
    '/admin/',
    '/login/',
    '/logout/',
    '/registro/',
    '/api/usuario/perfil/',
    '/api/dashboard/',
]

# ═════════════════════════════════════════════════════════════════
# 9. LOGGING DE CACHE (Debugging)
# ═════════════════════════════════════════════════════════════════

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'cache.log',
        },
    },
    'loggers': {
        'django_redis': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
    },
}

# ═════════════════════════════════════════════════════════════════
# NOTAS DE IMPLEMENTACIÓN
# ═════════════════════════════════════════════════════════════════

"""
PASOS PARA IMPLEMENTAR:

1. Editar config/settings.py y agregar toda esta configuración al final

2. Instalar dependencias (si es necesario):
   - pip install django-redis  # Para producción con Redis

3. Para desarrollo (sin Redis):
   - No requiere instalación adicional, usa LocMemCache

4. Para producción (con Redis):
   - Instalar Redis en el servidor
   - apt-get install redis-server
   - systemctl start redis-server

5. Reiniciar Django:
   - python manage.py runserver (desarrollo)
   - systemctl restart apache2 (producción con Passenger)

6. Verificar que funciona:
   - python manage.py shell
   - from django.core.cache import cache
   - cache.set('test', 'value')
   - cache.get('test')  # debe devolver 'value'

7. Monitorear:
   - Ver logs en logs/cache.log
   - Usar Django Debug Toolbar en desarrollo

ADVERTENCIAS:

⚠️ No cachear datos sensibles (passwords, tokens, etc)
⚠️ No cachear datos de usuarios autenticados sin cuidado
⚠️ En desarrollo, los cachés se pierden al reiniciar
⚠️ En producción con Redis, requiere monitoreo

BENEFICIOS:

✅ Reducción de 60-70% en tiempo de carga
✅ Menos solicitudes a la BD
✅ Menor uso de CPU
✅ Mejor escalabilidad
✅ Mejor experiencia de usuario
"""
