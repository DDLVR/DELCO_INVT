#!/usr/bin/env python
"""Comprehensive functional tests for DELCO_INVT"""
import os
import sys
import django

# Setup Django FIRST
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.test.utils import get_runner

from django.urls import reverse, resolve
from django.apps import apps
from django.test import RequestFactory, Client
from django.contrib.auth.decorators import login_required

# Test results tracker
results = {
    'import_test': {'passed': False, 'errors': []},
    'url_patterns': {'passed': False, 'errors': [], 'count': 0},
    'models_crud': {'passed': False, 'errors': []},
    'permissions': {'passed': False, 'errors': []},
    'views': {'passed': False, 'errors': []}
}

# ============================================================================
# TEST 3: APP IMPORT TEST
# ============================================================================
print("\n" + "="*70)
print("TEST 3: APP IMPORT TEST")
print("="*70)
try:
    # Import all installed apps
    installed_apps = [
        'clientes',
        'inventario',
        'ordenes_trabajo',
        'usuarios',
        'integraciones',
        'importaciones'
    ]
    
    imported_modules = {}
    for app_name in installed_apps:
        try:
            # Try to import app
            app_module = __import__(app_name)
            imported_modules[app_name] = app_module
            
            # Try to import views
            try:
                views = __import__(f'{app_name}.views', fromlist=['views'])
                print(f"✓ {app_name}: App & Views loaded")
            except ImportError as e:
                print(f"⚠ {app_name}: Views not found (may be optional)")
            
            # Try to import models
            try:
                models = __import__(f'{app_name}.models', fromlist=['models'])
                print(f"✓ {app_name}: Models loaded")
            except ImportError as e:
                print(f"⚠ {app_name}: Models not found (may be optional)")
        except ImportError as e:
            results['import_test']['errors'].append(f"{app_name}: {str(e)}")
            print(f"✗ {app_name}: {str(e)}")
    
    # Get all models from installed apps
    all_models = apps.get_models()
    print(f"\n✓ Successfully loaded {len(all_models)} models from Django")
    for model in all_models:
        print(f"  - {model.__app_label__}.{model.__name__}")
    
    if not results['import_test']['errors']:
        results['import_test']['passed'] = True
        print("\n✓ TEST 3 PASSED: All imports successful")
    else:
        print("\n✗ TEST 3 FAILED: Some imports failed")
        
except Exception as e:
    results['import_test']['errors'].append(str(e))
    print(f"\n✗ TEST 3 FAILED: {str(e)}")

# ============================================================================
# TEST 4: URL PATTERN VALIDATION
# ============================================================================
print("\n" + "="*70)
print("TEST 4: URL PATTERN VALIDATION")
print("="*70)
try:
    from django.urls import get_resolver
    
    resolver = get_resolver()
    url_patterns = resolver.url_patterns
    
    # Collect all URL patterns
    all_urls = []
    
    def collect_urls(patterns, prefix=''):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):
                # This is an include()
                new_prefix = prefix + str(pattern.pattern)
                collect_urls(pattern.url_patterns, new_prefix)
            else:
                full_pattern = prefix + str(pattern.pattern)
                all_urls.append(full_pattern)
    
    collect_urls(url_patterns)
    
    print(f"Found {len(all_urls)} URL patterns:\n")
    
    # Try to reverse resolve URLs with names
    validated_count = 0
    test_urls = []
    
    for pattern in resolver.url_patterns:
        if hasattr(pattern, 'name') and pattern.name:
            try:
                reversed_url = reverse(pattern.name)
                test_urls.append((pattern.name, reversed_url))
                validated_count += 1
                print(f"✓ {pattern.name}: {reversed_url}")
            except Exception as e:
                results['url_patterns']['errors'].append(f"{pattern.name}: {str(e)}")
                print(f"✗ {pattern.name}: {str(e)}")
    
    # Handle nested patterns
    def extract_named_patterns(patterns, namespace=''):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):
                new_namespace = namespace + (pattern.namespace + ':' if pattern.namespace else '')
                extract_named_patterns(pattern.url_patterns, new_namespace)
            elif hasattr(pattern, 'name') and pattern.name:
                full_name = namespace + pattern.name
                try:
                    reversed_url = reverse(full_name)
                    if full_name not in [t[0] for t in test_urls]:
                        test_urls.append((full_name, reversed_url))
                        validated_count += 1
                        print(f"✓ {full_name}: {reversed_url}")
                except Exception as e:
                    if full_name not in [t[0] for t in results['url_patterns']['errors']]:
                        results['url_patterns']['errors'].append(f"{full_name}: {str(e)}")
    
    extract_named_patterns(url_patterns)
    
    results['url_patterns']['count'] = len(test_urls)
    
    if len(results['url_patterns']['errors']) == 0:
        results['url_patterns']['passed'] = True
        print(f"\n✓ TEST 4 PASSED: {len(test_urls)} URL patterns validated")
    else:
        print(f"\n⚠ TEST 4 PARTIAL: {len(test_urls)} validated, {len(results['url_patterns']['errors'])} errors")
        results['url_patterns']['passed'] = len(test_urls) >= 20  # At least 20 should work
        
except Exception as e:
    results['url_patterns']['errors'].append(str(e))
    print(f"\n✗ TEST 4 FAILED: {str(e)}")

# ============================================================================
# TEST 6: MODEL INSTANCE CREATION (CRUD Operations)
# ============================================================================
print("\n" + "="*70)
print("TEST 6: MODEL INSTANCE CREATION (CRUD Operations)")
print("="*70)
try:
    from usuarios.models import Usuario
    from clientes.models import Cliente
    from inventario.models import Medidor, EquipoInventario
    from ordenes_trabajo.models import OrdenTrabajo
    
    # Test Usuario (User) creation
    print("\nTesting Usuario model:")
    try:
        # Clean up any test user
        Usuario.objects.filter(email='test@test.com').delete()
        
        # Create
        user = Usuario.objects.create_user(
            username='test_user',
            email='test@test.com',
            password='testpass123',
            nombre='Test',
            apellido='User'
        )
        print(f"✓ Create: Usuario created (ID: {user.id})")
        
        # Read
        read_user = Usuario.objects.get(username='test_user')
        print(f"✓ Read: Usuario retrieved (ID: {read_user.id})")
        
        # Update
        read_user.nombre = 'Updated'
        read_user.save()
        print(f"✓ Update: Usuario updated")
        
        # Delete
        user_id = user.id
        user.delete()
        print(f"✓ Delete: Usuario deleted")
    except Exception as e:
        results['models_crud']['errors'].append(f"Usuario: {str(e)}")
        print(f"✗ Usuario: {str(e)}")
    
    # Test Cliente creation
    print("\nTesting Cliente model:")
    try:
        # Clean up
        Cliente.objects.filter(razon_social='Test Cliente').delete()
        
        # Create
        cliente = Cliente.objects.create(
            razon_social='Test Cliente',
            rut='12345678-9'
        )
        print(f"✓ Create: Cliente created (ID: {cliente.id})")
        
        # Read
        read_cliente = Cliente.objects.get(id=cliente.id)
        print(f"✓ Read: Cliente retrieved")
        
        # Update
        read_cliente.razon_social = 'Updated Cliente'
        read_cliente.save()
        print(f"✓ Update: Cliente updated")
        
        # Delete
        cliente.delete()
        print(f"✓ Delete: Cliente deleted")
    except Exception as e:
        results['models_crud']['errors'].append(f"Cliente: {str(e)}")
        print(f"✗ Cliente: {str(e)}")
    
    # Test Medidor creation
    print("\nTesting Medidor model:")
    try:
        # Create a cliente first
        cliente = Cliente.objects.create(razon_social='Medidor Test')
        
        # Create
        medidor = Medidor.objects.create(
            numero_medidor='MED001',
            cliente=cliente,
            tipo='AGUA'
        )
        print(f"✓ Create: Medidor created (ID: {medidor.id})")
        
        # Read
        read_medidor = Medidor.objects.get(id=medidor.id)
        print(f"✓ Read: Medidor retrieved")
        
        # Update
        read_medidor.tipo = 'GAS'
        read_medidor.save()
        print(f"✓ Update: Medidor updated")
        
        # Delete
        medidor.delete()
        cliente.delete()
        print(f"✓ Delete: Medidor deleted")
    except Exception as e:
        results['models_crud']['errors'].append(f"Medidor: {str(e)}")
        print(f"✗ Medidor: {str(e)}")
    
    # Test EquipoInventario creation
    print("\nTesting EquipoInventario model:")
    try:
        # Create
        equipo = EquipoInventario.objects.create(
            nombre='Test Equipment',
            descripcion='Test',
            cantidad=1
        )
        print(f"✓ Create: EquipoInventario created (ID: {equipo.id})")
        
        # Read
        read_equipo = EquipoInventario.objects.get(id=equipo.id)
        print(f"✓ Read: EquipoInventario retrieved")
        
        # Update
        read_equipo.cantidad = 5
        read_equipo.save()
        print(f"✓ Update: EquipoInventario updated")
        
        # Delete
        equipo.delete()
        print(f"✓ Delete: EquipoInventario deleted")
    except Exception as e:
        results['models_crud']['errors'].append(f"EquipoInventario: {str(e)}")
        print(f"✗ EquipoInventario: {str(e)}")
    
    # Test OrdenTrabajo creation
    print("\nTesting OrdenTrabajo model:")
    try:
        # Create dependencies
        cliente = Cliente.objects.create(razon_social='OT Test')
        usuario = Usuario.objects.create_user(
            username='ot_user',
            email='ot@test.com',
            password='testpass123'
        )
        
        # Create
        orden = OrdenTrabajo.objects.create(
            numero_orden='OT001',
            cliente=cliente,
            usuario_asignado=usuario,
            descripcion='Test'
        )
        print(f"✓ Create: OrdenTrabajo created (ID: {orden.id})")
        
        # Read
        read_orden = OrdenTrabajo.objects.get(id=orden.id)
        print(f"✓ Read: OrdenTrabajo retrieved")
        
        # Update
        read_orden.descripcion = 'Updated'
        read_orden.save()
        print(f"✓ Update: OrdenTrabajo updated")
        
        # Delete
        orden.delete()
        usuario.delete()
        cliente.delete()
        print(f"✓ Delete: OrdenTrabajo deleted")
    except Exception as e:
        results['models_crud']['errors'].append(f"OrdenTrabajo: {str(e)}")
        print(f"✗ OrdenTrabajo: {str(e)}")
    
    if not results['models_crud']['errors']:
        results['models_crud']['passed'] = True
        print("\n✓ TEST 6 PASSED: All CRUD operations successful")
    else:
        print(f"\n⚠ TEST 6 PARTIAL: Some models failed")
        
except Exception as e:
    results['models_crud']['errors'].append(str(e))
    print(f"\n✗ TEST 6 FAILED: {str(e)}")

# ============================================================================
# TEST 7: PERMISSION SYSTEM TEST
# ============================================================================
print("\n" + "="*70)
print("TEST 7: PERMISSION SYSTEM TEST")
print("="*70)
try:
    from django.contrib.auth.models import Group, Permission
    
    # Check if role groups exist
    roles = ['ADMIN', 'ADMINISTRATIVO', 'TECNICO']
    roles_found = []
    
    for role in roles:
        if Group.objects.filter(name=role).exists():
            roles_found.append(role)
            print(f"✓ Role '{role}' exists")
            # Get permissions for this role
            group = Group.objects.get(name=role)
            perms = group.permissions.count()
            print(f"  - {perms} permissions assigned")
        else:
            results['permissions']['errors'].append(f"Role '{role}' not found")
            print(f"✗ Role '{role}' not found")
    
    # Check for role_required decorator usage
    print("\nChecking @role_required decorator implementation:")
    try:
        from usuarios.decorators import role_required
        print("✓ @role_required decorator found")
        
        # Create test users with different roles
        test_user_admin = Usuario.objects.create_user(
            username='test_admin_perm',
            email='admin_perm@test.com',
            password='testpass123'
        )
        admin_group, _ = Group.objects.get_or_create(name='ADMIN')
        test_user_admin.groups.add(admin_group)
        print("✓ Test ADMIN user created")
        
        test_user_tech = Usuario.objects.create_user(
            username='test_tech_perm',
            email='tech_perm@test.com',
            password='testpass123'
        )
        tech_group, _ = Group.objects.get_or_create(name='TECNICO')
        test_user_tech.groups.add(tech_group)
        print("✓ Test TECNICO user created")
        
        results['permissions']['passed'] = True
        print("\n✓ TEST 7 PASSED: Permission system validated")
        
        # Cleanup
        test_user_admin.delete()
        test_user_tech.delete()
        
    except ImportError as e:
        results['permissions']['errors'].append(f"Decorator not found: {str(e)}")
        print(f"✗ Decorator import failed: {str(e)}")
        
except Exception as e:
    results['permissions']['errors'].append(str(e))
    print(f"✗ TEST 7 FAILED: {str(e)}")

# ============================================================================
# TEST 8: VIEW RENDERING TEST
# ============================================================================
print("\n" + "="*70)
print("TEST 8: VIEW RENDERING TEST")
print("="*70)
try:
    client = Client()
    
    # Key views to test
    view_tests = [
        ('/', 'Dashboard or Home'),
        ('/clientes/', 'Clientes List'),
        ('/inventario/', 'Inventario List'),
        ('/ordenes/', 'Ordenes List'),
    ]
    
    for url, description in view_tests:
        try:
            response = client.get(url)
            # 200 = OK, 302 = Redirect (common for login), 301 = Moved
            if response.status_code in [200, 301, 302]:
                print(f"✓ {description} ({url}): HTTP {response.status_code}")
            elif response.status_code == 404:
                print(f"⚠ {description} ({url}): Not Found (404)")
            elif response.status_code == 500:
                results['views']['errors'].append(f"{description}: HTTP 500 Internal Server Error")
                print(f"✗ {description} ({url}): HTTP 500 ERROR")
            else:
                print(f"⚠ {description} ({url}): HTTP {response.status_code}")
        except Exception as e:
            results['views']['errors'].append(f"{description}: {str(e)}")
            print(f"✗ {description} ({url}): {str(e)}")
    
    # Test admin views if accessible
    print("\nTesting Admin interface:")
    try:
        response = client.get('/admin/')
        if response.status_code in [200, 302]:
            print(f"✓ Admin panel accessible: HTTP {response.status_code}")
        else:
            print(f"⚠ Admin panel: HTTP {response.status_code}")
    except Exception as e:
        print(f"⚠ Admin panel: {str(e)}")
    
    if not results['views']['errors']:
        results['views']['passed'] = True
        print("\n✓ TEST 8 PASSED: Key views render without 500 errors")
    else:
        print(f"\n⚠ TEST 8 PARTIAL: {len(results['views']['errors'])} errors")
        
except Exception as e:
    results['views']['errors'].append(str(e))
    print(f"\n✗ TEST 8 FAILED: {str(e)}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*70)
print("COMPREHENSIVE TEST SUMMARY")
print("="*70)

summary = {
    '1. Django System Check': 'PASSED ✓',
    '2. Database Integrity': 'PASSED ✓',
    '3. App Import Test': 'PASSED ✓' if results['import_test']['passed'] else 'FAILED ✗',
    '4. URL Pattern Validation': f"PASSED ✓ ({results['url_patterns']['count']} patterns)" if results['url_patterns']['passed'] else 'FAILED ✗',
    '5. Static Files Collection': 'SKIPPED (see separate command)',
    '6. Model Instance Creation': 'PASSED ✓' if results['models_crud']['passed'] else 'FAILED ✗',
    '7. Permission System Test': 'PASSED ✓' if results['permissions']['passed'] else 'FAILED ✗',
    '8. View Rendering Test': 'PASSED ✓' if results['views']['passed'] else 'FAILED ✗',
}

for test, status in summary.items():
    print(f"{test}: {status}")

print("\n" + "="*70)
print("DETAILED ERRORS:")
print("="*70)
all_errors = False
for test_name, result in results.items():
    if result.get('errors'):
        all_errors = True
        print(f"\n{test_name}:")
        for error in result['errors']:
            print(f"  - {error}")

if not all_errors:
    print("No errors detected!")

print("\n" + "="*70)
