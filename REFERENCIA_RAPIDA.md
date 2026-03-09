# 🔧 REFERENCIA RÁPIDA - BACKEND
# ======================================================
# Archivo de consulta rápida para desarrollo diario

## 📋 Archivo de Configuración (IMPORTANTE)

**Ubicación**: `Backend/.env` (NO commitear)

```
# Base de Datos MySQL
DB_NAME=aplicacion_bonita
DB_USER=root
DB_PASSWORD=tu_contraseña
DB_HOST=localhost
DB_PORT=3306

# Django (opcional)
SECRET_KEY=tu_secret_key_segura
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

## 🗂️ Estructura de Carpetas

```
Backend/
├── config/              # ⚙️ Configuración principal
│   ├── settings.py      # Base de datos, apps, middleware
│   ├── urls.py          # Enrutamiento principal
│   ├── asgi.py          # Configuración ASGI
│   ├── wsgi.py          # Configuración WSGI
│   └── __pycache__/
│
├── usuarios/            # 👥 Usuarios y autenticación
│   ├── models.py        # Usuario custom (RUT)
│   ├── admin.py         # Admin panel
│   ├── views.py         # (Vacío, usa web/views.py)
│   ├── serializers.py   # Para API REST
│   ├── urls.py          # (Vacío)
│   └── migrations/
│       └── 0001_initial.py
│
├── ordenes_trabajo/     # 📋 Órdenes de trabajo
│   ├── models.py        # OrdenTrabajo + máquina de estados
│   ├── admin.py         # Admin panel
│   ├── views.py         # Por implementar (API)
│   ├── serializers.py   # Para API REST
│   ├── urls.py          # Rutas API
│   └── migrations/
│       └── 0001_initial.py
│
├── web/                 # 🌐 Frontend HTML tradicional
│   ├── models.py        # (Vacío)
│   ├── views.py         # login, logout, dashboard
│   ├── urls.py          # Rutas HTML
│   ├── admin.py         # (Vacío)
│   └── migrations/
│
├── templates/           # 📄 Plantillas HTML
│   ├── base.html        # Plantilla base (herencia)
│   ├── dashboard.html   # Panel principal
│   ├── auth/
│   │   └── login.html   # Login
│   └── partials/
│       ├── navbar.html  # Barra superior
│       └── sidebar.html # Menú lateral
│
├── static/              # 📦 CSS, JS, imágenes
│   └── css/
│       └── app.css
│
├── db.sqlite3           # (Temporal, será MySQL)
├── manage.py            # 🛠️ CLI de Django
└── requirements.txt     # 📚 Dependencias Python
```

---

## 💾 Comandos Django (Más Comunes)

### Migraciones (Base de Datos)

```bash
# Detectar cambios en models.py y crear archivo de migración
python manage.py makemigrations

# Ver estado de migraciones
python manage.py showmigrations

# Aplicar migraciones a BD
python manage.py migrate

# Ver SQL generado (sin ejecutar)
python manage.py sqlmigrate usuarios 0001
```

### Usuario y Autenticación

```bash
# Crear superusuario interactivamente
python manage.py createsuperuser

# Cambiar contraseña de usuario
python manage.py changepassword nombre_usuario

# Crear usuario desde shell
python manage.py shell
# >>> from usuarios.models import Usuario
# >>> Usuario.objects.create_user(...)
```

### Servidor y Testing

```bash
# Ejecutar servidor de desarrollo
python manage.py runserver

# Abrir consola Python interactiva (shell)
python manage.py shell

# Ejecutar tests
python manage.py test

# Tests con verbosidad
python manage.py test --verbosity=2
```

### Datos (Importar/Exportar)

```bash
# Exportar datos a JSON (backup)
python manage.py dumpdata > datos_backup.json

# Cargar datos desde JSON
python manage.py loaddata datos_backup.json

# Vaciar tabla específica
python manage.py dumpdata usuarios > usuarios.json
```

---

## 📊 Modelos Principales

### Usuario (`usuarios/models.py`)

```python
from usuarios.models import Usuario

# Crear usuario
usuario = Usuario.objects.create_user(
    rut='12345678-9',
    email='juan@empresa.cl',
    password='segura123',
    nombre='Juan',
    apellido='Pérez',
    nombre_interno='JPérez',
    rol='TECNICO'  # ADMIN|GERENCIA|ADMINISTRATIVO|TECNICO|AUDITOR
)

# Buscar por RUT
usuario = Usuario.objects.get(rut='12345678-9')

# Listar técnicos
tecnicos = Usuario.objects.filter(rol='TECNICO')

# Contar usuarios por rol
admin_count = Usuario.objects.filter(rol='ADMIN').count()
```

### Orden de Trabajo (`ordenes_trabajo/models.py`)

```python
from ordenes_trabajo.models import OrdenTrabajo

# Crear orden
orden = OrdenTrabajo.objects.create(
    titulo='Instalar medidor tensión',
    descripcion='Detalles de la tarea...',
    estado='CREADA',  # CREADA|ASIGNADA|EN_EJECUCION|FINALIZADA|...
    tecnico_responsable=usuario_tecnico,
    creada_por=usuario_admin
)

# Buscar órdenes por estado
pendientes = OrdenTrabajo.objects.filter(estado='CREADA')

# Órdenes asignadas a técnico
mis_ordenes = OrdenTrabajo.objects.filter(tecnico_responsable=request.user)

# Cambiar estado (con validación de permisos)
resultado = orden.puede_cambiar_estado(usuario, 'FINALIZADA')
if resultado:
    orden.estado = 'FINALIZADA'
    orden.save()

# Asignar equipo
orden.tecnicos_equipo.add(tecnico_2, tecnico_3)

# Obtener equipo completo
equipo = orden.get_equipo_completo()
```

---

## 🛣️ URLs y Vistas

### Rutas (`config/urls.py`)

```python
urlpatterns = [
    path('admin/', admin.site.urls),                    # Admin
    path('', include('web.urls')),                      # HTML views
    path('ordenes/', include('ordenes_trabajo.urls')),  # API
]
```

### Vistas HTML (`web/urls.py`)

```
GET  /                  → home_view (redirección)
GET  /login/            → login_view (formulario)
POST /login/            → login_view (autenticación)
GET  /logout/           → logout_view (cierre sesión)
GET  /dashboard/        → dashboard_view (protegida)
```

---

## 🔒 Protección de Vistas

### Decoradores

```python
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin

# Verificar autenticación
@login_required
def my_view(request):
    user = request.user
    return render(request, 'template.html')

# Verificar permiso específico
@permission_required('ordenes_trabajo.add_ordentrabajo')
def create_orden(request):
    pass

# Verificar rol
@login_required
def admin_only(request):
    if request.user.rol != 'ADMIN':
        return redirect('dashboard')
    pass
```

---

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
