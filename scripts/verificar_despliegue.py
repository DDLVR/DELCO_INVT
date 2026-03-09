#!/usr/bin/env python
"""
Script de verificación pre-despliegue
Ejecutar antes de subir a producción para verificar que todo esté listo
"""
import os
import sys
from pathlib import Path

def check_file(path, description):
    """Verificar si un archivo existe"""
    if Path(path).exists():
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"❌ {description}: {path} - NO ENCONTRADO")
        return False

def check_env_var(var_name, description):
    """Verificar si una variable de entorno está configurada"""
    if os.environ.get(var_name):
        print(f"✅ {description}: {var_name} configurada")
        return True
    else:
        print(f"⚠️  {description}: {var_name} - NO CONFIGURADA (requerida en producción)")
        return False

def main():
    print("=" * 60)
    print("CHECKLIST DE VERIFICACIÓN PRE-DESPLIEGUE")
    print("=" * 60)
    print()
    
    # BASE_DIR es Backend/ (un nivel arriba de scripts/)
    BASE_DIR = Path(__file__).resolve().parent.parent
    all_checks = []
    
    # 1. Archivos de configuración
    print("📁 ARCHIVOS DE CONFIGURACIÓN")
    print("-" * 60)
    all_checks.append(check_file(BASE_DIR / "passenger_wsgi.py", "Archivo WSGI"))
    all_checks.append(check_file(BASE_DIR / ".htaccess", "Archivo .htaccess"))
    all_checks.append(check_file(BASE_DIR / "config" / "settings_production.py", "Settings producción"))
    all_checks.append(check_file(BASE_DIR / "requirements.txt", "Requirements.txt"))
    print()
    
    # 2. Variables de entorno (advertencias)
    print("🔐 VARIABLES DE ENTORNO")
    print("-" * 60)
    print("⚠️  Las siguientes variables deben configurarse en el servidor:")
    print("   - SECRET_KEY")
    print("   - DB_NAME")
    print("   - DB_USER")
    print("   - DB_PASSWORD")
    print("   - DB_HOST")
    print()
    
    # 3. Estructura de directorios
    print("📂 ESTRUCTURA DE DIRECTORIOS")
    print("-" * 60)
    all_checks.append(check_file(BASE_DIR / "config", "Directorio config"))
    all_checks.append(check_file(BASE_DIR / "usuarios", "App usuarios"))
    all_checks.append(check_file(BASE_DIR / "inventario", "App inventario"))
    all_checks.append(check_file(BASE_DIR / "ordenes_trabajo", "App ordenes_trabajo"))
    all_checks.append(check_file(BASE_DIR / "manage.py", "manage.py"))
    print()
    
    # 4. Frontend compilado
    print("🎨 FRONTEND")
    print("-" * 60)
    frontend_path = BASE_DIR.parent / "Front" / "app-operaciones"
    if frontend_path.exists():
        print(f"✅ Directorio frontend encontrado: {frontend_path}")
        print("⚠️  Recuerda compilar con: cd Front/app-operaciones && npm run build")
    else:
        print(f"❌ Directorio frontend NO encontrado: {frontend_path}")
    print()
    
    # 5. Dependencias
    print("📦 DEPENDENCIAS")
    print("-" * 60)
    try:
        import django
        print(f"✅ Django instalado: {django.get_version()}")
        all_checks.append(True)
    except ImportError:
        print("❌ Django NO instalado")
        all_checks.append(False)
    
    try:
        import rest_framework
        print("✅ Django REST Framework instalado")
        all_checks.append(True)
    except ImportError:
        print("⚠️  Django REST Framework NO instalado")
        all_checks.append(False)
    print()
    
    # 6. Checklist manual
    print("📋 CHECKLIST MANUAL")
    print("-" * 60)
    print("Antes de subir a producción, asegúrate de:")
    print("   [ ] Cambiar SECRET_KEY en passenger_wsgi.py")
    print("   [ ] Configurar credenciales de base de datos MySQL")
    print("   [ ] Actualizar ALLOWED_HOSTS en settings_production.py")
    print("   [ ] Compilar el frontend: npm run build")
    print("   [ ] Generar requirements.txt: pip freeze > requirements.txt")
    print("   [ ] Probar localmente con DEBUG=False")
    print("   [ ] Actualizar rutas en .htaccess y passenger_wsgi.py")
    print("   [ ] Crear base de datos MySQL en cPanel")
    print("   [ ] Configurar dominio/subdominio en Hostingplus")
    print("   [ ] Subir archivos via FTP")
    print("   [ ] Instalar dependencias en el servidor")
    print("   [ ] Ejecutar migraciones: python manage.py migrate")
    print("   [ ] Crear superusuario: python manage.py createsuperuser")
    print("   [ ] Recopilar estáticos: python manage.py collectstatic")
    print("   [ ] Reiniciar aplicación")
    print()
    
    # Resumen
    print("=" * 60)
    passed = sum(all_checks)
    total = len(all_checks)
    print(f"RESULTADO: {passed}/{total} verificaciones pasadas")
    
    if passed == total:
        print("✅ ¡Todo listo para el despliegue!")
        return 0
    else:
        print("⚠️  Hay archivos faltantes. Revisa los errores arriba.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
