# 🗂️ ESTRUCTURA DE BASE DE DATOS
# ======================================================
# Diagrama de relaciones y tablas

"""
════════════════════════════════════════════════════════════════════
ARQUITECTURA DE BD: MYSQL
════════════════════════════════════════════════════════════════════

NOMBRE BD: aplicacion_bonita
USUARIO: root (o similar)
HOST: localhost (o IP servidor)
PUERTO: 3306 (default MySQL)

════════════════════════════════════════════════════════════════════
TABLAS PRINCIPALES
════════════════════════════════════════════════════════════════════
"""

"""
┌─────────────────────────────────────────────────────────────────────┐
│                        TABLA: usuarios_usuario                       │
│                     (Usuarios y Autenticación)                       │
├─────────────────────────────────────────────────────────────────────┤
│ PK  id                    │ INT, AUTO_INCREMENT                      │
│     rut                   │ VARCHAR(12), UNIQUE, NOT NULL            │
│     email                 │ VARCHAR(254), UNIQUE, NOT NULL           │
│     password              │ VARCHAR(128), NOT NULL (encriptado)      │
│     nombre                │ VARCHAR(100), NOT NULL                   │
│     apellido              │ VARCHAR(100), NOT NULL                   │
│     nombre_interno        │ VARCHAR(100), NOT NULL                   │
│     rol                   │ VARCHAR(20), NOT NULL (ADMIN|TECNICO...) │
│     is_active             │ BOOLEAN, DEFAULT 1                       │
│     is_staff              │ BOOLEAN, DEFAULT 0                       │
│     is_superuser          │ BOOLEAN, DEFAULT 0                       │
│     fecha_creacion        │ DATETIME, AUTO_NOW_ADD                   │
│     last_login            │ DATETIME, NULL                           │
├─────────────────────────────────────────────────────────────────────┤
│ ÍNDICES:                                                             │
│   - rut (UNIQUE)                                                     │
│   - email (UNIQUE)                                                   │
│   - rol (NORMAL)                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ REGISTROS EJEMPLO:                                                   │
│   1 | 12345678-9 | juan@empresa.cl    | ...pbkdf2... | Juan | ... │
│   2 | 87654321-0 | maria@empresa.cl   | ...pbkdf2... | María| ... │
│   3 | 55555555-5 | admin@empresa.cl   | ...pbkdf2... | Admin| ... │
└─────────────────────────────────────────────────────────────────────┘
"""

"""
┌─────────────────────────────────────────────────────────────────────┐
│                 TABLA: ordenes_trabajo_ordentrabajo                  │
│                    (Órdenes de Trabajo)                              │
├─────────────────────────────────────────────────────────────────────┤
│ PK  id                           │ INT, AUTO_INCREMENT                │
│     titulo                       │ VARCHAR(200), NOT NULL             │
│     descripcion                  │ LONGTEXT, NULLABLE                 │
│     estado                       │ VARCHAR(20), NOT NULL              │
│                                  │ (CREADA|ASIGNADA|EN_EJECUCION...) │
│ FK  tecnico_responsable_id       │ INT, NOT NULL                      │
│                                  │ → usuarios_usuario.id              │
│ FK  creada_por_id               │ INT, NOT NULL                      │
│                                  │ → usuarios_usuario.id              │
│     fecha_creacion               │ DATETIME, AUTO_NOW_ADD             │
│     fecha_cierre                 │ DATETIME, NULLABLE                 │
│     tecnico_solicito_reasignacion│ BOOLEAN, DEFAULT 0                 │
├─────────────────────────────────────────────────────────────────────┤
│ ÍNDICES:                                                             │
│   - estado (NORMAL)                                                  │
│   - tecnico_responsable_id (FK)                                      │
│   - creada_por_id (FK)                                               │
│   - fecha_creacion (NORMAL)                                          │
├─────────────────────────────────────────────────────────────────────┤
│ REGISTROS EJEMPLO:                                                   │
│ ID │ Título                    │ Estado       │ Tecnico │ Creada_por│
│ 1  │ Instalar medidor site A   │ ASIGNADA     │ 2       │ 3         │
│ 2  │ Mantenimiento subestación │ EN_EJECUCION│ 2       │ 3         │
│ 3  │ Reparar transformador     │ FINALIZADA   │ 1       │ 3         │
└─────────────────────────────────────────────────────────────────────┘
"""

"""
┌─────────────────────────────────────────────────────────────────────┐
│        TABLA: ordenes_trabajo_ordentrabajo_tecnicos_equipo           │
│                    (Relación M2M)                                    │
├─────────────────────────────────────────────────────────────────────┤
│ PK  id                       │ INT, AUTO_INCREMENT                    │
│ FK  ordentrabajo_id          │ INT, NOT NULL                          │
│                              │ → ordenes_trabajo_ordentrabajo.id     │
│ FK  usuario_id               │ INT, NOT NULL                          │
│                              │ → usuarios_usuario.id                 │
├─────────────────────────────────────────────────────────────────────┤
│ UNIQUE(ordentrabajo_id, usuario_id)  [Evita duplicados]             │
├─────────────────────────────────────────────────────────────────────┤
│ REGISTROS EJEMPLO:                                                   │
│   1 | orden_id=1 | usuario_id=2 (técnico 2 en equipo orden 1)       │
│   2 | orden_id=1 | usuario_id=4 (técnico 4 en equipo orden 1)       │
│   3 | orden_id=2 | usuario_id=2 (técnico 2 en equipo orden 2)       │
└─────────────────────────────────────────────────────────────────────┘
"""

"""
┌─────────────────────────────────────────────────────────────────────┐
│              TABLA: auth_group                                        │
│          (Grupos de permisos - Django built-in)                      │
├─────────────────────────────────────────────────────────────────────┤
│ PK  id     │ INT, AUTO_INCREMENT                                    │
│     name   │ VARCHAR(150), UNIQUE                                   │
├─────────────────────────────────────────────────────────────────────┤
│ REGISTROS EJEMPLO:                                                   │
│   1 | "Técnicos"                                                     │
│   2 | "Administrativos"                                              │
│   3 | "Gerencia"                                                     │
└─────────────────────────────────────────────────────────────────────┘
"""

"""
════════════════════════════════════════════════════════════════════
RELACIONES ENTRE TABLAS
════════════════════════════════════════════════════════════════════

usuarios_usuario (1) ─────< (N) ordenes_trabajo_ordentrabajo
     ↑                              (tecnico_responsable_id)
     └─────────────────────────────

usuarios_usuario (1) ─────< (N) ordenes_trabajo_ordentrabajo
     ↑                              (creada_por_id)
     └─────────────────────────────

usuarios_usuario (N) ────── (N) ordenes_trabajo_ordentrabajo
         ↑                              ↑
         └───── (JOIN TABLE) ──────────┘
      ordenes_trabajo_ordentrabajo_tecnicos_equipo
"""

"""
════════════════════════════════════════════════════════════════════
MIGRACIONES DJANGO (Historial de cambios)
════════════════════════════════════════════════════════════════════

Archivo: Backend/usuarios/migrations/0001_initial.py
  → Crea tabla usuarios_usuario (1ª vez)

Archivo: Backend/ordenes_trabajo/migrations/0001_initial.py
  → Crea tabla ordenes_trabajo_ordentrabajo
  → Crea tabla ordenes_trabajo_ordentrabajo_tecnicos_equipo

Comandos:
  python manage.py makemigrations   # Detecta cambios en models.py
  python manage.py migrate          # Aplica migraciones a BD
  python manage.py showmigrations   # Muestra estado
"""

"""
════════════════════════════════════════════════════════════════════
TIPOS DE DATOS EN DJANGO → MYSQL
════════════════════════════════════════════════════════════════════

CharField(max_length=100)          → VARCHAR(100)
TextField()                        → LONGTEXT
IntegerField()                     → INT
BigAutoField()                     → BIGINT AUTO_INCREMENT
BooleanField(default=True)         → BOOLEAN (TINYINT)
DateTimeField(auto_now_add=True)   → DATETIME
ForeignKey(User, ...)              → INT + FOREIGN KEY
ManyToManyField(User, ...)         → Tabla intermedia
EmailField()                       → VARCHAR(254)
"""

"""
════════════════════════════════════════════════════════════════════
CONFIGURACIÓN .ENV (NO HACER COMMIT)
════════════════════════════════════════════════════════════════════

Archivo: Backend/.env

DB_NAME=aplicacion_bonita
DB_USER=root
DB_PASSWORD=tu_contraseña_segura
DB_HOST=localhost
DB_PORT=3306

Django carga estas variables en settings.py:
  os.getenv('DB_NAME')
  os.getenv('DB_USER')
  etc.
"""

"""
════════════════════════════════════════════════════════════════════
CICLO DE VIDA DE MIGRACIÓN
════════════════════════════════════════════════════════════════════

1. CAMBIAR models.py
   Ejemplo: Agregar campo nuevo a Usuario
   
   class Usuario(AbstractBaseUser, ...):
       # ... campos existentes ...
       telefono = models.CharField(max_length=20, null=True)  ← NUEVO

2. DETECTAR CAMBIOS
   $ python manage.py makemigrations
   
   Salida:
   Migrations for 'usuarios':
     usuarios/migrations/0002_usuario_telefono.py

3. REVISAR MIGRACIÓN
   $ cat usuarios/migrations/0002_usuario_telefono.py
   
   Contiene:
   - operations.AddField('usuario', 'telefono', models.CharField(...))

4. APLICAR A BD
   $ python manage.py migrate
   
   Ejecuta el SQL:
   ALTER TABLE usuarios_usuario ADD COLUMN telefono VARCHAR(20);

5. CONFIRMAR
   $ python manage.py showmigrations
   
   [X] usuarios.0001_initial
   [X] usuarios.0002_usuario_telefono
"""

"""
════════════════════════════════════════════════════════════════════
CONSULTAS ÚTILES DESDE DJANGO ORM
════════════════════════════════════════════════════════════════════

# Obtener usuario por RUT
usuario = Usuario.objects.get(rut='12345678-9')

# Listar técnicos
tecnicos = Usuario.objects.filter(rol='TECNICO')

# Órdenes asignadas a un técnico
ordenes = OrdenTrabajo.objects.filter(tecnico_responsable=usuario)

# Órdenes del último mes
from django.utils import timezone
from datetime import timedelta

hace_un_mes = timezone.now() - timedelta(days=30)
ordenes = OrdenTrabajo.objects.filter(fecha_creacion__gte=hace_un_mes)

# Estadísticas
total_ordenes = OrdenTrabajo.objects.count()
pendientes = OrdenTrabajo.objects.filter(estado='CREADA').count()
finalizadas = OrdenTrabajo.objects.filter(estado='FINALIZADA').count()

# SQL raw (último recurso)
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT * FROM usuarios_usuario WHERE rol=%s", ['TECNICO'])
    resultados = cursor.fetchall()
"""
