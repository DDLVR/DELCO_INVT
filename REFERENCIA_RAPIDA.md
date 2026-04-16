# REFERENCIA RAPIDA - OPERACION CLIENTE

Guia corta para operacion diaria del sistema DELCO_INVT.

## 1. URLs principales

- /login/
- /dashboard/
- /inventario/
- /movimientos/
- /reportes/moreapp/
- /operacional/pendientes/

## 2. Flujo diario recomendado

1. Ingresar a /reportes/moreapp/ y sincronizar.
2. Revisar /operacional/pendientes/.
3. Resolver casos:
   - REVISADO: caso validado.
   - CON_ADVERTENCIA: requiere seguimiento.
   - DESCARTADO: formulario no aplicable.
4. Revisar dashboard por pendientes envejecidos (> 7 dias).
5. Ejecutar control de calidad de datos.

## 3. Comandos clave

### Migraciones

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
```

### Verificaciones

```bash
python manage.py check
python manage.py verificar_calidad --solo-reporte
python manage.py verificar_calidad
```

### Estados estandar inventario

```bash
python manage.py inicializar_estados
```

## 4. Estados operativos MoreApp

### Estado de sincronizacion (tecnico)

- PENDIENTE
- PROCESANDO
- PROCESADO
- EXITOSO
- ERROR / ERROR_JSON / ERROR_LECTURA
- DUPLICADO
- ALERTA_REVISION

### Estado de revision (operativo)

- PENDIENTE
- CON_ADVERTENCIA
- REVISADO
- DESCARTADO

## 5. Inventario: trazabilidad

Cada movimiento registra:

- tipo (incluye AJUSTE, CORRECCION, MOREAPP)
- origen_sistema (MOREAPP, MANUAL, IMPORTACION, SISTEMA)
- origen y destino
- responsable
- observacion

## 6. Roles y alcance

- ADMIN: control total, elimina reportes MoreApp de prueba.
- ADMINISTRATIVO: operacion, revision y gestion diaria.
- SUPERVISOR: seguimiento y validacion operativa.
- TECNICO: ejecucion de terreno.
- GERENCIA / AUDITOR: monitoreo y control.

## 7. Checklist rapido ante incidencias

1. Confirmar si el submission existe en /reportes/moreapp/.
2. Revisar detalle del registro y pendientes de cruce.
3. Ver trazabilidad en /movimientos/ filtrando origen_sistema=MOREAPP.
4. Ajustar estado de revision en la cola operativa.
5. Registrar observacion y escalar si hay conflicto de instalacion.

## 📝 Template Context (Variables disponibles)

```html
<!-- En cualquier template -->
{{ request.user }}              <!-- Usuario actual -->
{{ request.user.nombre_interno }}<!-- Nombre del usuario -->
{{ request.user.rol }}           <!-- Rol: ADMIN, TECNICO, etc. -->
{{ request.user.email }}         <!-- Email del usuario -->

<!-- Si está autenticado -->
{% if user.is_authenticated %}
    <p>Bienvenido {{ user.nombre_interno }}</p>
{% else %}
    <p>Por favor inicia sesión</p>
{% endif %}

<!-- Por rol -->
{% if user.rol == 'ADMIN' %}
    <button>Crear usuario</button>
{% endif %}

<!-- Mensajes flash -->
{% if messages %}
    {% for message in messages %}
        <div class="alert alert-{{ message.tags }}">
            {{ message }}
        </div>
    {% endfor %}
{% endif %}
```

---

## 🐛 Debugging

### Ver detalles de solicitud

```python
from django.http import HttpRequest

def my_view(request):
    print(f"Usuario: {request.user}")
    print(f"Método: {request.method}")
    print(f"Datos POST: {request.POST}")
    print(f"Datos GET: {request.GET}")
    print(f"Headers: {request.META}")
    return render(request, 'template.html')
```

### Usar Django Shell

```bash
python manage.py shell

# Importar modelos
>>> from usuarios.models import Usuario
>>> from ordenes_trabajo.models import OrdenTrabajo

# Consultas
>>> Usuario.objects.all()
>>> OrdenTrabajo.objects.filter(estado='CREADA')

# Crear instancias
>>> usuario = Usuario(rut='123', email='test@test.com', rol='TECNICO')
>>> usuario.save()

# Actualizar
>>> usuario.nombre = 'Nuevo nombre'
>>> usuario.save()

# Eliminar
>>> usuario.delete()

# Salir
>>> exit()
```

---

## 📦 Dependencias (`requirements.txt`)

```
Django==5.2.7
djangorestframework==3.14.0
django-filter==23.5
mysqlclient==2.2.0
python-dotenv==1.0.0
```

Instalar:
```bash
pip install -r requirements.txt
```

---

## 🚀 Ejecutar Proyecto

### Setup Inicial (1 sola vez)

```bash
cd Backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

### Desarrollo Diario

```bash
# Terminal 1: Activar ambiente y ejecutar servidor
cd Backend
venv\Scripts\Activate.ps1
python manage.py runserver

# Terminal 2: Trabajar en código (editor)
# Django detecta cambios automáticamente
```

### Acceder

```
http://localhost:8000/login/     # Login
http://localhost:8000/admin/     # Admin
http://localhost:8000/dashboard/ # Dashboard
```

---

## 📋 Checklist antes de Commit

```bash
# 1. Verificar cambios
git status

# 2. Revisar código
# (buscar print(), TODO, debug code)

# 3. Ejecutar tests
python manage.py test

# 4. Hacer migraciones si cambió models.py
python manage.py makemigrations
python manage.py migrate

# 5. Agregar cambios
git add -A

# 6. Commit descriptivo
git commit -m "Feat: Agregar validación en cambio de estado"

# 7. Push
git push origin feature/nombre
```

---

## ⚠️ Problemas Comunes

### Error: "ModuleNotFoundError"
```bash
# Solución: instalar dependencias
pip install -r requirements.txt
```

### Error: "OperationalError: (2002) Can't connect to MySQL"
```
1. Verificar MySQL está corriendo
2. Verificar variables en .env
3. Crear BD: CREATE DATABASE aplicacion_bonita;
```

### Error: "No such table"
```bash
# Solución: ejecutar migraciones
python manage.py migrate
```

### Static files no cargan (CSS, JS)
```bash
# Solución en desarrollo: DEBUG = True (ya está en settings.py)
# En producción:
python manage.py collectstatic
```

---

## 📚 Recursos

- [Django Docs](https://docs.djangoproject.com/)
- [DRF Docs](https://www.django-rest-framework.org/)
- [MySQL Docs](https://dev.mysql.com/doc/)
- Este proyecto: Ver archivos .md en raíz

---

**Última actualización**: Enero 2026
**Para más información**: Leer DOCUMENTACION_PROYECTO.md
