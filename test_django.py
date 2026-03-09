#!/usr/bin/env python
"""Script de diagnóstico para verificar que Django funciona"""
import os
import sys

# Configurar PyMySQL
try:
    import pymysql
    pymysql.install_as_MySQLdb()
    print("✓ PyMySQL configurado")
except ImportError as e:
    print(f"✗ Error importando PyMySQL: {e}")

# Configurar Django
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_production')

try:
    import django
    print(f"✓ Django importado (versión {django.get_version()})")
    
    django.setup()
    print("✓ Django configurado correctamente")
    
    # Verificar base de datos
    from django.db import connection
    cursor = connection.cursor()
    print("✓ Conexión a base de datos exitosa")
    
    # Verificar modelos
    from usuarios.models import Usuario
    count = Usuario.objects.count()
    print(f"✓ Modelos cargados - {count} usuarios en BD")
    
    # Verificar URLs
    from django.urls import get_resolver
    resolver = get_resolver()
    print(f"✓ URLs configuradas")
    
    print("\n🎉 Django está funcionando correctamente!")
    print("\nVariables de entorno:")
    print(f"  DEBUG: {os.environ.get('DEBUG', 'no configurado')}")
    print(f"  SECRET_KEY: {'configurado' if os.environ.get('SECRET_KEY') else 'NO configurado'}")
    print(f"  DB_NAME: {os.environ.get('DB_NAME', 'no configurado')}")
    print(f"  ALLOWED_HOSTS: {os.environ.get('ALLOWED_HOSTS', 'no configurado')}")
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
