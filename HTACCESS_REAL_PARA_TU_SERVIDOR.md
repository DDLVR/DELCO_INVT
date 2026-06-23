# 🔐 .HTACCESS PARA TU SERVIDOR REAL - DELCO INVT

## Situación Actual

Tu proyecto está en **Hostingplus con Passenger** (vía `passenger_wsgi.py`).

```
Tu configuración:
- Servidor: Hostingplus
- WSGI: Passenger (passenger_wsgi.py)
- Framework: Django 5.2.7
- Base de datos: MySQL
- Dominio: inventario.delcochile.cl
```

---

## ⚠️ IMPORTANTE: .htaccess en Hostingplus

### Cómo Funciona en Hostingplus
- ✅ **.htaccess SÍ funciona** (si hay Apache configurado)
- ✅ **Puedes modificarlo** via FTP/SSH
- ⚠️ **Pero NO controla la aplicación Passenger** (eso es Python)
- ✅ **SÍ controla static files** (CSS, JS, imágenes)

### Dónde va tu .htaccess

```
/home/tuusuario/inventario.delcochile.cl/
├── public_html/               ← Raíz web
│   ├── .htaccess             ← AQUÍ va tu .htaccess
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── img/
│   ├── media/
│   └── ...
├── passenger_wsgi.py         ← Tu aplicación Python
└── ...
```

---

## 📝 .HTACCESS PARA HOSTINGPLUS (Tu Caso Específico)

### Versión A: SIMPLE (Recomendado para empezar)

```apache
# .htaccess para Hostingplus + Passenger + Django

# ═════════════════════════════════════════════════════════
# CACHÉ DE ARCHIVOS ESTÁTICOS
# ═════════════════════════════════════════════════════════

<IfModule mod_expires.c>
    ExpiresActive On
    
    # CSS y JavaScript: 1 mes
    <FilesMatch "\.(css|js)$">
        ExpiresDefault "access plus 1 month"
    </FilesMatch>
    
    # Imágenes: 3 meses
    <FilesMatch "\.(jpg|jpeg|png|gif|webp|ico|svg)$">
        ExpiresDefault "access plus 3 months"
    </FilesMatch>
    
    # Fuentes: 1 año
    <FilesMatch "\.(woff|woff2|ttf|otf|eot)$">
        ExpiresDefault "access plus 1 year"
    </FilesMatch>
    
    # HTML: No cachear
    <FilesMatch "\.(html)$">
        ExpiresDefault "access plus 0 seconds"
    </FilesMatch>
</IfModule>

# ═════════════════════════════════════════════════════════
# HEADERS DE CACHE-CONTROL
# ═════════════════════════════════════════════════════════

<IfModule mod_headers.c>
    # CSS/JS
    <FilesMatch "\.(css|js)$">
        Header set Cache-Control "public, max-age=2592000"
    </FilesMatch>
    
    # Imágenes
    <FilesMatch "\.(jpg|jpeg|png|gif|webp)$">
        Header set Cache-Control "public, max-age=7776000"
    </FilesMatch>
    
    # Fuentes
    <FilesMatch "\.(woff|woff2|ttf)$">
        Header set Cache-Control "public, max-age=31536000"
    </FilesMatch>
</IfModule>

# ═════════════════════════════════════════════════════════
# COMPRESIÓN GZIP
# ═════════════════════════════════════════════════════════

<IfModule mod_deflate.c>
    AddOutputFilterByType DEFLATE text/html text/plain text/xml text/css text/javascript application/javascript
</IfModule>
```

---

### Versión B: COMPLETA (Con más optimizaciones)

```apache
# .htaccess COMPLETO para Hostingplus + Passenger + Django

# ═════════════════════════════════════════════════════════
# 1. REESCRITURA DE URLs (Para Passenger/Django)
# ═════════════════════════════════════════════════════════

RewriteEngine On

# Permitir acceso a static files y media directamente
RewriteCond %{REQUEST_FILENAME} ^/(static|media)(/|$)
RewriteRule ^ - [L]

# Todo lo demás va a Passenger (Django)
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^(.*)$ /passenger/wsgi.py/$1 [QSA,L]

# ═════════════════════════════════════════════════════════
# 2. CACHÉ CON MOD_EXPIRES
# ═════════════════════════════════════════════════════════

<IfModule mod_expires.c>
    ExpiresActive On
    ExpiresDefault "access plus 0 seconds"
    
    # Imágenes: 3 meses (90 días)
    ExpiresByType image/jpeg "access plus 3 months"
    ExpiresByType image/gif "access plus 3 months"
    ExpiresByType image/png "access plus 3 months"
    ExpiresByType image/webp "access plus 3 months"
    ExpiresByType image/svg+xml "access plus 3 months"
    ExpiresByType image/x-icon "access plus 3 months"
    
    # CSS: 1 mes (30 días)
    ExpiresByType text/css "access plus 1 month"
    
    # JavaScript: 1 mes
    ExpiresByType application/javascript "access plus 1 month"
    ExpiresByType text/javascript "access plus 1 month"
    
    # Fuentes: 1 año
    ExpiresByType font/ttf "access plus 1 year"
    ExpiresByType font/otf "access plus 1 year"
    ExpiresByType font/woff "access plus 1 year"
    ExpiresByType font/woff2 "access plus 1 year"
    
    # JSON/XML: 1 hora
    ExpiresByType application/json "access plus 1 hour"
    ExpiresByType application/xml "access plus 1 hour"
</IfModule>

# ═════════════════════════════════════════════════════════
# 3. HEADERS DE CACHE-CONTROL (Más explícito)
# ═════════════════════════════════════════════════════════

<IfModule mod_headers.c>
    
    # Static assets con caché largo
    <FilesMatch "\.(jpg|jpeg|png|gif|webp|ico|svg|woff|woff2|ttf)$">
        Header set Cache-Control "public, max-age=31536000, immutable"
    </FilesMatch>
    
    # CSS/JS con caché de 1 mes
    <FilesMatch "\.(css|js)$">
        Header set Cache-Control "public, max-age=2592000"
    </FilesMatch>
    
    # HTML sin caché
    <FilesMatch "\.html$">
        Header set Cache-Control "public, max-age=0, must-revalidate"
    </FilesMatch>
    
    # Headers de seguridad
    Header set X-Content-Type-Options "nosniff"
    Header set X-Frame-Options "SAMEORIGIN"
    
</IfModule>

# ═════════════════════════════════════════════════════════
# 4. COMPRESIÓN GZIP
# ═════════════════════════════════════════════════════════

<IfModule mod_deflate.c>
    # Tipos a comprimir
    AddOutputFilterByType DEFLATE text/html
    AddOutputFilterByType DEFLATE text/plain
    AddOutputFilterByType DEFLATE text/xml
    AddOutputFilterByType DEFLATE text/css
    AddOutputFilterByType DEFLATE text/javascript
    AddOutputFilterByType DEFLATE application/javascript
    AddOutputFilterByType DEFLATE application/json
    AddOutputFilterByType DEFLATE application/xml
    
    # Agregar Vary header
    Header append Vary Accept-Encoding
</IfModule>

# ═════════════════════════════════════════════════════════
# 5. PROTEGER ARCHIVOS SENSIBLES
# ═════════════════════════════════════════════════════════

<FilesMatch "^\.ht|\.env|settings\.py|wsgi\.py">
    <IfModule mod_authz_core.c>
        Require all denied
    </IfModule>
</FilesMatch>
```

---

## 🔧 CÓMO INSTALAR EL .HTACCESS

### Opción 1: Vía FTP (Recomendado para Hostingplus)

1. **Conectar por FTP**:
   - Host: `ftp.inventario.delcochile.cl` (o similar)
   - Usuario: tu usuario FTP
   - Contraseña: tu contraseña

2. **Navegar a la raíz** (`public_html/` o `/`)

3. **Verificar si existe `.htaccess`**:
   - Si existe: NO toques, pide al hosting que lo revise
   - Si no existe: Crear nuevo

4. **Subir o crear el archivo**:
   - Crear archivo vacío: `generaHtaccess.txt`
   - Copiar el contenido de la sección anterior
   - Renombrar a `.htaccess`
   - Subir

5. **Verificar permisos**:
   - Debe ser legible por Apache
   - Permisos: 644 (rw-r--r--)

### Opción 2: Vía SSH (Si tienes acceso)

```bash
# Conectar
ssh tu_usuario@tu_dominio.cl

# Crear archivo
cat > /home/tu_usuario/inventario.delcochile.cl/public_html/.htaccess << 'EOF'
# Pegar aquí el contenido de .htaccess
EOF

# Verificar
ls -la | grep htaccess
```

### Opción 3: Via Panel de Control (Si lo tiene)

- Algunos paneles (cPanel, Plesk) tienen editor de archivos
- Buscar: "File Manager" → public_html → crear .htaccess

---

## ✅ VERIFICAR QUE FUNCIONA

### Paso 1: Ver Headers en el navegador

```javascript
// En Console (F12)
fetch('/static/css/app.css')
    .then(r => r.headers)
    .then(h => {
        console.log('Cache-Control:', h.get('cache-control'));
        console.log('Expires:', h.get('expires'));
        console.log('✅ Si ves valores, funciona');
    });
```

### Paso 2: Con curl desde línea de comandos

```bash
curl -i https://inventario.delcochile.cl/static/css/app.css | grep Cache-Control

# Resultado esperado:
# Cache-Control: public, max-age=2592000
```

### Paso 3: Usar curl en PowerShell

```powershell
$response = Invoke-WebRequest -Uri "https://inventario.delcochile.cl/static/css/app.css" -Method Head
$response.Headers['Cache-Control']

# Debe mostrar algo como: public, max-age=2592000
```

---

## ⚠️ PROBLEMAS COMUNES

### Problema 1: "El archivo no funciona"
**Causa**: Apache no tiene mod_expires o mod_headers

**Solución**: 
- Contactar a Hostingplus support
- Pedir que habiliten mod_expires y mod_headers
- Decir: "Necesito mod_expires y mod_headers para caché"

### Problema 2: "La app Django no funciona después de agregar .htaccess"
**Causa**: Las reescrituras de URL rompieron Passenger

**Solución**:
- Eliminar sección de RewriteEngine
- Usar solo la sección 2, 3, 4, 5 (sin RewriteEngine)
- O contactar a soporte

### Problema 3: "Los cambios no se ven"
**Causa**: Caché del navegador anterior

**Solución**:
- Limpiar caché: Ctrl+Shift+Delete
- O usar: Ctrl+Shift+R (reload sin caché)
- Esperar 5 minutos

### Problema 4: "Permiso denegado al crear archivo"
**Causa**: Permisos FTP incorrectos

**Solución**:
- Verificar usuario FTP tiene permisos
- Cambiar permisos a 644
- Contactar a hosting si no puedes

---

## 🎯 CONFIGURACIÓN RECOMENDADA PARA HOSTINGPLUS

### Mínima (Lo menos que necesitas)
```apache
<IfModule mod_expires.c>
    ExpiresActive On
    ExpiresByType image/jpeg "access plus 3 months"
    ExpiresByType text/css "access plus 1 month"
    ExpiresByType application/javascript "access plus 1 month"
</IfModule>

<IfModule mod_deflate.c>
    AddOutputFilterByType DEFLATE text/css application/javascript
</IfModule>
```

### Recomendada (Mejor balance)
Use la "Versión A: SIMPLE" de arriba

### Completa (Máxima optimización)
Use la "Versión B: COMPLETA" de arriba

---

## 🔄 ALTERNATIVA: SIN .HTACCESS (Puro Django)

Si el .htaccess no funciona o prefieres no usarlo, **todo se puede hacer en Django**:

Ya está documentado en: `CONFIGURACION_CACHE_DJANGO.py`

```python
# En config/settings.py puedes configurar:

CACHES = { ... }
MIDDLEWARE = [ 'django.middleware.gzip.GZipMiddleware', ... ]
SECURE_HSTS_SECONDS = 31536000
```

**Ventaja**: No necesitas .htaccess
**Desventaja**: Solo funciona para Django, no para static files (CSS/JS)

---

## 📋 CHECKLIST

### Antes de implementar
- [ ] Verificar que tienes acceso FTP/SSH
- [ ] Contactar a Hostingplus si tienes dudas
- [ ] Hacer backup de .htaccess existente (si existe)
- [ ] Probar primero en local si es posible

### Instalación
- [ ] Crear/editar .htaccess
- [ ] Subir al servidor (public_html)
- [ ] Verificar permisos (644)
- [ ] Revisar que Django sigue funcionando

### Verificación
- [ ] Abrir F12 → Network → ver headers
- [ ] curl para verifica Cache-Control
- [ ] Ejecutar Lighthouse
- [ ] Probar en incógnito (sin caché anterior)

---

## 🆘 CONTACTAR A SOPORTE

Si necesitas ayuda de Hostingplus, diles:

```
Necesito ayuda con .htaccess para caché:

1. Necesito habilitar mod_expires para expiración de archivos
2. Necesito mod_headers para Cache-Control
3. Tengo una aplicación Django en Passenger
4. Los static files (CSS, JS, imágenes) deben cachearse

¿Pueden ayudar? ¿Hay alguna configuración especial en Hostingplus?
```

---

## ✅ PRÓXIMOS PASOS

1. **Intenta**: Crear un .htaccess simple (Versión A)
2. **Sube**: Via FTP al servidor
3. **Verifica**: Que los headers cambiaron
4. **Si funciona**: Sigue con Versión B (si quieres más optimizaciones)
5. **Si no**: Contacta a soporte o usa solo Django Cache

---

**Documento creado para TU servidor real (Hostingplus) ✅**
