"""
Script para crear usuarios de prueba para cada rol.
Ejecutar con: python manage.py shell < crear_usuarios.py
"""

from usuarios.models import Usuario

# Datos de usuarios a crear
usuarios_data = [
    {
        'rut': '111111113',
        'email': 'admin@delco.cl',
        'password': '123456789',
        'nombre': 'Admin',
        'apellido': 'Sistema',
        'nombre_interno': 'Administrador',
        'rol': 'ADMIN',
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'rut': '111111114',
        'email': 'administrativo@delco.cl',
        'password': '123456789',
        'nombre': 'Carlos',
        'apellido': 'Coordinador',
        'nombre_interno': 'Carlos Coordinador',
        'rol': 'ADMINISTRATIVO',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'rut': '111111115',
        'email': 'tecnico@delco.cl',
        'password': '123456789',
        'nombre': 'Juan',
        'apellido': 'Técnico',
        'nombre_interno': 'Juan Técnico',
        'rol': 'TECNICO',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'rut': '111111116',
        'email': 'supervisor@delco.cl',
        'password': '123456789',
        'nombre': 'Pedro',
        'apellido': 'Validador',
        'nombre_interno': 'Pedro Supervisor',
        'rol': 'SUPERVISOR',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'rut': '111111117',
        'email': 'gerencia@delco.cl',
        'password': '123456789',
        'nombre': 'Gerencia',
        'apellido': 'Delco',
        'nombre_interno': 'Jefe Gerencia',
        'rol': 'GERENCIA',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'rut': '111111119',
        'email': 'auditor@delco.cl',
        'password': '123456789',
        'nombre': 'Auditor',
        'apellido': 'Sistema',
        'nombre_interno': 'Auditor Delco',
        'rol': 'AUDITOR',
        'is_staff': False,
        'is_superuser': False,
    },
]

print("Creando usuarios de prueba...\n")

for user_data in usuarios_data:
    rut = user_data.pop('rut')
    email = user_data.pop('email')
    password = user_data.pop('password')
    
    # Verificar si ya existe
    if Usuario.objects.filter(rut=rut).exists():
        print(f"⚠️  Usuario {rut} ya existe, saltando...")
        continue
    
    # Crear usuario
    usuario = Usuario.objects.create_user(
        rut=rut,
        email=email,
        password=password,
        **user_data
    )
    
    print(f"✅ Creado: {usuario.nombre_interno} ({usuario.rol})")
    print(f"   RUT: {rut}")
    print(f"   Password: {password}\n")

print("\n✨ Usuarios de prueba creados exitosamente!")
print("\nPrueba logearte con:")
print("  RUT: 111111115 (Técnico)")
print("  RUT: 111111114 (Administrativo)")
print("  RUT: 111111116 (Supervisor)")
print("  etc...")
print("\nPassword para todos: 123456789")
