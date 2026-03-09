"""
WSGI config para Passenger (Hostingplus)
"""
import sys
import os

# IMPORTANTE: Configurar PyMySQL antes que Django (si está disponible)
# y habilitar logging para capturar errores tempranos.
import logging

# calcular el directorio actual inmediatamente, antes de usarlo
current_dir = os.path.dirname(os.path.abspath(__file__))

logfile = os.environ.get('WSGI_LOGFILE', os.path.join(current_dir, 'passenger_wsgi.log'))
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(logfile, encoding='utf-8'), logging.StreamHandler()]
)

try:
    import pymysql
    pymysql.install_as_MySQLdb()
    logging.info('PyMySQL cargado e instalado como MySQLdb')
except Exception as e:
    logging.warning('No se pudo cargar PyMySQL: %s', e)
    # Si PyMySQL no está instalado en el entorno del host, continuar
    # y dejar que Django muestre un error más descriptivo si falla al conectar
    pass

# Ruta al intérprete de Python del virtualenv (ajusta si tu hosting usa otra)
INTERP = os.path.expanduser("~/virtualenv/APPS_WEB/3.8/bin/python")

# Cambiar el intérprete sólo si la ruta existe; evita errores si la ruta no está
# disponible en el entorno del host (por ejemplo en local/Windows).
if os.path.exists(INTERP) and sys.executable != INTERP:
    try:
        os.execv(INTERP, [INTERP] + sys.argv)
    except Exception:
        # No forzar fallo del proceso; continuar con el intérprete actual
        pass

# Agregar el directorio del proyecto al path
sys.path.insert(0, current_dir)

# Usar configuración de producción (las variables de entorno se configuran en Setup Python App)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_production')

# Inicializar la aplicación Django
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
