# 🚀 GUÍA COMPLETA: Primera subida a cPanel

**Proyecto**: DelcoChile Inventario  
**Dominio**: delcochile.inventario  
**Host**: Hostingplus (cPanel)  
**Fecha**: 5 de marzo de 2026

---

## ⏱️ PASO 0: Preparación previa (LOCAL en tu máquina)

### 0.1 Verifica que el proyecto esté listo
```bash
cd c:\Users\DelcoChile TI\Desktop\APPS PROG\aplicacion-bonita\Backend
python manage.py check --settings=config.settings_production
```
**Esperado**: `System check identified no issues (0 silenced).`

### 0.2 Genera estáticos
```bash
python manage.py collectstatic --noinput --settings=config.settings_production
```
**Esperado**: `162 static files copied to '...staticfiles'.`

### 0.3 Archivos a excluir
Crea un `.gitignore` (o excluye manualmente) los siguientes:
```
db.sqlite3
.env
__pycache__/
*.pyc
*.log
.DS_Store
*.egg-info/
dist/
build/
```

### 0.4 Empaqueta el proyecto
Comprime todo excepto lo anterior en un ZIP:
- Desde `Backend/`, ZIP todo DENTRO (no la carpeta Backend misma).
- Nombre sugerido: `backend_delcochile_v1.zip`

---

## 🔑 PASO 1: Acceso y preparación en cPanel

### 1.1 Accede a tu cPanel
1. Ve a `https://tuhost.com:2083` (o la URL que te haya dado Hostingplus)
2. Usuario: `delcochi` (o el que uses)
3. Contraseña: (la que tengas)

### 1.2 Crea un directorio para la aplicación
1. ve a **Administrador de archivos**
2. Navega a `/home50/delcochi/` (o `/home/tu_usuario/`)
3. Crea una carpeta nueva llamada `delcochile_inventario`
4. Dentro de esa carpeta, crea: `virtualenv` (o deja que cPanel lo haga en el siguiente paso)

---

## 🐍 PASO 2: Crear la aplicación Python en cPanel

### 2.1 Dirígete a "Python App" (o "Application Manager")
Busca en el panel de cPanel:
- Opción 1: Sección **Software** → **Python Application Manager**
- Opción 2: Búsqueda directa: "python"

### 2.2 Crea una nueva aplicación


Haz clic en **"+ Create Application"** (o **"Create App"**):

| Campo | Valor |
|-------|-------|
| **Python version** | `3.8` o `3.9` (lo que recomiende Hostingplus) |
| **Application root** | `/home50/delcochi/delcochile_inventario` |
| **Application URL** | `delcochile.inventario` |
| **Application startup file** | `passenger_wsgi.py` |
| **Application entry point** | `application` |
| **Passenger log file** | `/home50/delcochi/delcochile_inventario/passenger.log` |

Haz clic en **CREATE**.

cPanel creará automáticamente:
- Un virtualenv en `/home50/delcochi/virtualenv/delcochile_inventario/3.8/` (o similar)
- Un enlace simbólico a `/home50/delcochi/delcochile_inventario/`

---

## 📁 PASO 3: Sube los archivos del proyecto

### 3.1 Acceso por SFTP/FTP o Administrador de archivos
1. En cPanel → **Administrador de archivos**
2. Navega a `/home50/delcochi/delcochile_inventario/`
3. Haz clic en **Subir** (o usa FTP si prefieres)
4. Sube el archivo `backend_delcochile_v1.zip`

### 3.2 Descomprime el ZIP
1. Clic derecho en `backend_delcochile_v1.zip`
2. Opción **"Extract"** (o "Descomprimir")
3. Asegúrate de que los archivos queden directamente dentro de `/home50/delcochi/delcochile_inventario/`  
   (es decir: `delcochile_inventario/manage.py`, `delcochile_inventario/config/`, etc., **no** `delcochile_inventario/Backend/manage.py`)

### 3.3 Verifica estructura
Debería verse así:
```
/home50/delcochi/delcochile_inventario/
├── manage.py
├── passenger_wsgi.py
├── requirements.txt
├── config/
│   ├── settings.py
│   ├── settings_production.py
│   ├── urls.py
│   └── ...
├── clientes/
├── inventario/
├── usuarios/
├── static/
└── templates/
```

---

## ⚙️ PASO 4: Configura variables de entorno

### 4.1 Accede a la aplicación Python en cPanel
En **Python Application Manager**, busca tu aplicación `delcochile.inventario` y haz clic en **"Edit"** o el icono de configuración.

### 4.2 Añade variables de entorno
En la sección **"Environment Variables"**, añade estas líneas de una en una (o pégalas si permite):

```
DB_NAME=delcochi_DelcoChile_Inventario
DB_USER=delcochi_DDLVR
DB_PASSWORD=Chomuske132$$
DB_HOST=localhost
DB_PORT=3306
SECRET_KEY=aBcD1234eFgH5678iJkL9012MnOpQrStUvWxYz@#$%^&*()_+-=[]{}|;:'",.<>?/
DEBUG=False
ALLOWED_HOSTS=delcochile.inventario,www.delcochile.inventario
DJANGO_SETTINGS_MODULE=config.settings_production
```

**Importante**: 
- `SECRET_KEY` debe ser una cadena larga y aleatoria. Puedes generarla con:
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
  (ejecuta esto en tu máquina local primero)
- `DEBUG=False` es OBLIGATORIO en producción.

Guarda los cambios.

---

## 📦 PASO 5: Instala dependencias

### 5.1 Accede al shell interactivo de Python App
En **Python Application Manager**, busca tu app y haz clic en **"Enter Shell"** (o accede por SSH a la terminal).

### 5.2 Activa el virtualenv
```bash
cd /home50/delcochi/delcochile_inventario
source /home50/delcochi/virtualenv/delcochile_inventario/3.8/bin/activate
```
(o la ruta que te haya mostrado cPanel)

### 5.3 Instala dependencias
```bash
pip install -r requirements.txt
```

**Esperado**: Se instalan todos los paquetes sin error.

---

## 🗄️ PASO 6: Ejecuta migraciones

### 6.1 Desde el shell activado, ejecuta:
```bash
python manage.py migrate --settings=config.settings_production
```

**Esperado**: 
```
Operations to perform:
  Apply all migrations: admin, auth, clientes, contenttypes, importaciones, ...
Running migrations:
  Applying ... OK
  ...
```

Si hay errores de **"Access denied"**, es que el servidor MySQL está rechazando
las credenciales antes de ejecutar las migraciones. Haz lo siguiente:

1. **Comprueba las variables de entorno** en el panel de la aplicación:
   `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT` deben coincidir
   exactamente con los nombres generados por cPanel (incluyendo el prefijo del
   usuario). No debe haber espacios ni caracteres extraños.
2. **Prueba la conexión manual** en el mismo shell donde corres los comandos:
   ```bash
   mysql -u delcochi_DDLVR -p -h localhost -P 3306 delcochi_DelcoChile_Inventario
   ```
   Si también obtienes "Access denied" aquí, entonces la contraseña o el usuario
   son incorrectos o no tienen permisos.
3. En cPanel → **MySQL® Databases**:
   * Crea o modifica el usuario `delcochi_DDLVR` con la contraseña que usas en
     `DB_PASSWORD`.
   * Añade ese usuario a la base `delcochi_DelcoChile_Inventario` y asigna **All
     Privileges**.
   * Si cambias la contraseña, actualiza la variable de entorno correspondiente
     y reinicia la aplicación antes de volver a ejecutar la migración.
4. Asegúrate de que la base de datos **existe** y que los nombres son correctos.

Tras estos pasos, vuelve a lanzar `python manage.py migrate` y deberías ver las
migraciones aplicarse sin el error `OperationalError: (1045, "Access denied...")`.

### 6.2 Recopila archivos estáticos (si no lo hiciste)
```bash
python manage.py collectstatic --noinput --settings=config.settings_production
```

---

## 🔄 PASO 7: Reinicia la aplicación

### 7.1 En cPanel
En **Python Application Manager**, busca tu app `delcochile.inventario` y haz clic en **"RESTART"**.

Espera 5-10 segundos.

### 7.2 Verifica el log
Aún en **Python Application Manager**, consulta **"View Log"** para ver si hay errores:
```
passenger.log: ...
```

Si todo es verde (sin errores), continúa.

---

## 🌐 PASO 8: Accede a tu aplicación

### 8.1 Abre en el navegador
Ve a: `https://delcochile.inventario`

### 8.2 Si ves el sitio...
✅ **¡Éxito!** Tu aplicación está viva.

### 8.3 Si hay errores...
Revisa:
1. **Error 502/503**: Reinicia la app (Step 7.1)
2. **"DisallowedHost at /"**: Las variables `ALLOWED_HOSTS` no están bien. Reconfigura Step 4.2.
3. **"Connection refused"**: La BD no es accesible. Verifica credenciales y que MySQL esté activo.
4. **Archivos CSS/JS rrotos**: Los estáticos no se sirvieron. Verifica que `collectstatic` se ejecutó (Step 6.2).

---

## 📋 CHECKLIST FINAL

- [ ] Proyecto empaquetado en ZIP sin archivos innecesarios
- [ ] Aplicación Python creada en cPanel con dominio `delcochile.inventario`
- [ ] Archivos descomprimidos en `/home50/delcochi/delcochile_inventario/`
- [ ] Variables de entorno (DB_*, SECRET_KEY, DEBUG=False) configuradas
- [ ] `pip install -r requirements.txt` completado sin errores
- [ ] `python manage.py migrate` ejecutado exitosamente
- [ ] `python manage.py collectstatic` ejecutado
- [ ] Aplicación reiniciada en cPanel
- [ ] `https://delcochile.inventario` carga sin errores
- [ ] Logs revisados (`passenger.log`) y limpios de errores críticos

---

## 🆘 SOPORTE RÁPIDO

| Problema | Solución |
|----------|----------|
| "Allowed host" error | Edita variables → ALLOWED_HOSTS=delcochile.inventario,www.delcochile.inventario |
| "Cannot connect to database" | Verifica DB_NAME, DB_USER, DB_PASSWORD en variables y que la BD exista |
| Static files no cargan | Ejecuta `python manage.py collectstatic --noinput` dentro del shell |
| "ModuleNotFoundError: No module named 'rest_framework'" | `pip install -r requirements.txt` en el virtualenv activado |
| Aplicación no reinicia | Espera 10 segundos y haz click en RESTART de nuevo |

---

**¡Listo!** Ahora tienes la base para mantener tu aplicación en producción. Cualquier actualización futura seguirá pasos similares pero con archivos modificados únicamente.

