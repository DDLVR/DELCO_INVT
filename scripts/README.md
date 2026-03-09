# 🛠️ Scripts de Utilidad

Scripts auxiliares para desarrollo, despliegue y mantenimiento del sistema.

---

## 📋 Scripts Disponibles

### 1. crear_usuarios.py
**Propósito:** Crear usuarios administrativos y de prueba

**Uso:**
```bash
cd Backend
python scripts/crear_usuarios.py
```

**Qué hace:**
- Crea usuarios con diferentes roles (ADMIN, ADMINISTRATIVO, TECNICO)
- Configura contraseñas por defecto
- Útil para setup inicial o testing

---

### 2. generar_requirements.py
**Propósito:** Generar archivo `requirements.txt` con todas las dependencias

**Uso:**
```bash
cd Backend
python scripts/generar_requirements.py
```

**Qué hace:**
- Ejecuta `pip freeze`
- Genera `requirements.txt` automáticamente
- Verifica dependencias críticas (Django, djangorestframework, mysqlclient)
- **OBLIGATORIO antes de desplegar a producción**

---

### 3. verificar_despliegue.py
**Propósito:** Checklist pre-despliegue a Hostingplus

**Uso:**
```bash
cd Backend
python scripts/verificar_despliegue.py
```

---

### 4. preparar_despliegue.py
**Propósito:** Limpiar archivos temporales y crear un ZIP listo para subir

**Uso:**
```bash
cd Backend
python scripts/preparar_despliegue.py
```

**Qué hace:**
- Elimina `.env`, `__pycache__`, archivos `.pyc`, logs, zips/tar previos y carpetas de build/dist
- Muestra el tamaño del proyecto para evitar empaquetar algo inesperadamente grande; si ves varios GB, revisa archivos grandes en la carpeta antes de volver a ejecutar
- Garantiza que exista un `.gitignore` con los patrones necesarios
- Genera `backend_delcochile_v1.zip` y `backend_delcochile_v1.tar.gz` con el contenido limpio del proyecto

**Qué hace:**
- Verifica archivos necesarios (passenger_wsgi.py, .htaccess, settings_production.py)
- Comprueba estructura de directorios
- Lista variables de entorno requeridas
- Checklist manual para completar
- **Ejecutar ANTES de subir a producción**

---

## 🔄 Workflow Recomendado

### Para Desarrollo Local
```bash
# 1. Crear usuarios de prueba
python scripts/crear_usuarios.py
```

### Antes de Desplegar
```bash
# 1. Generar requirements.txt
python scripts/generar_requirements.py

# 2. Verificar que todo esté listo
python scripts/verificar_despliegue.py

# 3. Corregir cualquier problema encontrado

# 4. Subir a Hostingplus
```

---

## 📝 Notas

- Ejecutar todos los scripts desde el directorio `Backend/`
- Asegurarse que el entorno virtual esté activado
- Los scripts usan configuración de desarrollo por defecto (`config.settings`)

---

## 🆕 Agregar Nuevos Scripts

Para scripts futuros, seguir esta estructura:

```python
"""
Descripción clara del script
Ejecutar: python scripts/nombre_script.py
"""
import sys
sys.path.append('.')  # Para importar desde Backend

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Tu código aquí

def main():
    print("🚀 Iniciando script...")
    # Lógica principal
    print("✅ Completado!")

if __name__ == "__main__":
    main()
```

---

**Mantener scripts simples, documentados y con propósito claro.**
