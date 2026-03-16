 #!/usr/bin/env python
"""
Script para crear superusuario en producción
"""
import os
import sys
import django

# Agregar el directorio raíz del proyecto al path
# Esto permite que funcione desde scripts/ o desde la raíz
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) if 'scripts' in current_dir else current_dir
sys.path.insert(0, project_root)

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_production')

# Configurar PyMySQL
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass

django.setup()

from usuarios.models import Usuario

# Datos del superusuario
rut = '20591586-9'  # Cambia este RUT si necesitas otro
email = 'die.delavega@delcochile.cl'
password = 'Chomuske132'
nombre = 'Diego'
apellido = 'De la Vega'
nombre_interno = 'Diego De la Vega'

# Verificar si ya existe por RUT o email
usuario_existente = Usuario.objects.filter(rut=rut).first() or Usuario.objects.filter(email=email).first()

if usuario_existente:
    print(f"⚠️  El usuario con RUT '{rut}' o email '{email}' ya existe.")
    # Actualizar datos por si acaso
    usuario_existente.rut = rut
    usuario_existente.email = email
    usuario_existente.set_password(password)
    usuario_existente.nombre = nombre
    usuario_existente.apellido = apellido
    usuario_existente.nombre_interno = nombre_interno
    usuario_existente.rol = 'ADMIN'
    usuario_existente.is_superuser = True
    usuario_existente.is_staff = True
    usuario_existente.is_active = True
    usuario_existente.save()
    print(f"✅ Usuario actualizado como superusuario.")
    print(f"   RUT: {rut}")
    print(f"   Email: {email}")
    print(f"   Rol: ADMIN")
else:
    # Crear superusuario
    usuario = Usuario.objects.create_superuser(
        rut=rut,
        email=email,
        password=password,
        nombre=nombre,
        apellido=apellido,
        nombre_interno=nombre_interno,
        rol='ADMIN'
    )
    print(f"✅ Superusuario creado exitosamente.")
    print(f"   RUT: {rut}")
    print(f"   Email: {email}")
    print(f"   Nombre: {nombre} {apellido}")
    print(f"   Rol: ADMIN")
