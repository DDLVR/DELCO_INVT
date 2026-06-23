# 🔍 SCRIPT DE VERIFICACIÓN - OPTIMIZACIÓN Y CACHÉ

## DELCO INVT - Verificar estado actual

---

## 1. VERIFICACIÓN RÁPIDA EN EL NAVEGADOR

### Paso 1: Abrir DevTools
```
F12 en Chrome/Firefox/Edge
```

### Paso 2: Ver Cache Headers
```javascript
// Ejecutar en Console (F12 → Console)

// Ver headers de un archivo CSS
fetch('/static/css/app.css')
    .then(r => r.headers)
    .then(h => {
        console.log('Cache-Control:', h.get('cache-control'));
        console.log('Expires:', h.get('expires'));
        console.log('ETag:', h.get('etag'));
        console.log('Last-Modified:', h.get('last-modified'));
    });

// Ver headers de una imagen
fetch('/static/img/delco.png')
    .then(r => r.headers)
    .then(h => {
        console.log('Cache-Control:', h.get('cache-control'));
        console.log('Content-Type:', h.get('content-type'));
        console.log('Content-Length:', h.get('content-length'));
    });
```

### Paso 3: Verificar Lazy Loading
```javascript
// En Console:

// Contar imágenes con lazy loading
const lazyImages = document.querySelectorAll('img[loading="lazy"]');
console.log(`Imágenes con lazy loading: ${lazyImages.length}`);

// Contar todas las imágenes
const allImages = document.querySelectorAll('img');
console.log(`Total de imágenes: ${allImages.length}`);

// Porcentaje
const percent = (lazyImages.length / allImages.length * 100).toFixed(2);
console.log(`Cobertura: ${percent}%`);

// Listar imágenes SIN lazy loading
document.querySelectorAll('img:not([loading="lazy"])').forEach(img => {
    console.warn('Sin lazy loading:', img.src);
});
```

### Paso 4: Ver Performance Metrics
```javascript
// En Console:

// Web Vitals
if (window.performance && window.performance.getEntriesByType) {
    const paintEntries = performance.getEntriesByType('paint');
    const navigationTiming = performance.getEntriesByType('navigation')[0];
    
    console.table({
        'First Paint': paintEntries[0]?.startTime.toFixed(2) + 'ms',
        'First Contentful Paint': paintEntries[1]?.startTime.toFixed(2) + 'ms',
        'DOM Content Loaded': navigationTiming.domContentLoadedEventEnd - navigationTiming.domContentLoadedEventStart + 'ms',
        'Load Time': navigationTiming.loadEventEnd - navigationTiming.loadEventStart + 'ms',
        'Total Time': navigationTiming.loadEventEnd - navigationTiming.fetchStart + 'ms'
    });
}
```

---

## 2. VERIFICACIÓN CON CURL (Línea de Comandos)

### Script de prueba en PowerShell

```powershell
# Crear archivo test_cache.ps1

# Variables
$DOMAIN = "http://localhost:8000"
$FILES = @(
    "/static/css/app.css",
    "/static/img/delco.png",
    "/"
)

Write-Host "════════════════════════════════════════════"
Write-Host "VERIFICACIÓN DE HEADERS DE CACHE"
Write-Host "════════════════════════════════════════════"
Write-Host ""

foreach ($file in $FILES) {
    Write-Host "Archivo: $file"
    Write-Host "─────────────────────────────────────────" -ForegroundColor Cyan
    
    $response = Invoke-WebRequest -Uri "$DOMAIN$file" -Method Head -UseBasicParsing
    
    $cacheControl = $response.Headers["Cache-Control"]
    $expires = $response.Headers["Expires"]
    $etag = $response.Headers["ETag"]
    $contentLength = $response.Headers["Content-Length"]
    $contentEncoding = $response.Headers["Content-Encoding"]
    
    Write-Host "Cache-Control: $cacheControl" -ForegroundColor Yellow
    Write-Host "Expires: $expires"
    Write-Host "ETag: $etag"
    Write-Host "Content-Length: $contentLength bytes"
    Write-Host "Content-Encoding: $contentEncoding"
    Write-Host ""
}

Write-Host "════════════════════════════════════════════"
Write-Host "VERIFICACIÓN DE COMPRESIÓN (GZIP)"
Write-Host "════════════════════════════════════════════"
Write-Host ""

$headers = @{
    "Accept-Encoding" = "gzip, deflate"
}

$response = Invoke-WebRequest -Uri "$DOMAIN/" -Headers $headers -UseBasicParsing
$encoding = $response.Headers["Content-Encoding"]

if ($encoding -eq "gzip" -or $encoding -eq "deflate") {
    Write-Host "✅ GZIP/DEFLATE ACTIVO: $encoding" -ForegroundColor Green
} else {
    Write-Host "❌ GZIP/DEFLATE NO DETECTADO" -ForegroundColor Red
}

Write-Host ""
```

### Ejecutar verificación

```powershell
# En PowerShell (como administrador)
cd C:\Users\DelcoChile TI\Desktop\APPS PROG\DELCO_INVT

# Ejecutar
.\test_cache.ps1
```

---

## 3. VERIFICACIÓN CON GOOGLE LIGHTHOUSE

### Paso 1: Abrir Chrome
```
1. Ir a tu URL (http://localhost:8000 o https://inventario.delcochile)
2. Abrir DevTools (F12)
3. Ir a pestaña "Lighthouse"
4. Seleccionar "Performance"
5. Click "Analyze page load"
```

### Paso 2: Revisar el reporte

Buscar:
- ✅ **LCP (Largest Contentful Paint)**: Debe ser < 2.5s
- ✅ **FID (First Input Delay)**: Debe ser < 100ms
- ✅ **CLS (Cumulative Layout Shift)**: Debe ser < 0.1
- ✅ **Performance Score**: Debe ser > 90

### Problemas comunes detectados:
- "Offscreen images" → Aplicar lazy loading
- "Unsized images" → Agregaar width/height
- "Unused CSS" → Optimizar estilos
- "Unused JavaScript" → Dividir bundles

---

## 4. VERIFICACIÓN OFFLINE CON PYTHON

### Script Python

```python
# Crear archivo verify_optimization.py

import requests
import json
from datetime import datetime
from urllib.parse import urljoin

class CacheVerifier:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'base_url': base_url,
            'resources': []
        }
    
    def check_resource(self, path):
        """Verificar headers de cache para un recurso"""
        url = urljoin(self.base_url, path)
        
        try:
            response = self.session.head(url, timeout=5)
            
            resource_info = {
                'path': path,
                'status': response.status_code,
                'headers': {
                    'Cache-Control': response.headers.get('Cache-Control'),
                    'Expires': response.headers.get('Expires'),
                    'ETag': response.headers.get('ETag'),
                    'Last-Modified': response.headers.get('Last-Modified'),
                    'Content-Encoding': response.headers.get('Content-Encoding'),
                    'Content-Length': response.headers.get('Content-Length'),
                    'Content-Type': response.headers.get('Content-Type'),
                }
            }
            
            # Analizar calidad del cache
            cache_control = response.headers.get('Cache-Control', '')
            if 'no-cache' in cache_control or 'no-store' in cache_control:
                resource_info['cache_quality'] = '⚠️ Sin cache'
            elif 'max-age=0' in cache_control:
                resource_info['cache_quality'] = '⚠️ Cache corto'
            elif 'max-age=' in cache_control:
                resource_info['cache_quality'] = '✅ Cache activo'
            else:
                resource_info['cache_quality'] = '❌ No configurado'
            
            self.results['resources'].append(resource_info)
            return resource_info
            
        except Exception as e:
            print(f"Error verificando {url}: {e}")
            return None
    
    def verify_gzip(self):
        """Verificar si gzip está activado"""
        headers = {
            'Accept-Encoding': 'gzip, deflate'
        }
        
        try:
            response = self.session.get(
                self.base_url,
                headers=headers,
                timeout=5
            )
            
            encoding = response.headers.get('Content-Encoding', '')
            is_gzip = 'gzip' in encoding or 'deflate' in encoding
            
            self.results['gzip'] = {
                'enabled': is_gzip,
                'encoding': encoding,
                'original_size': len(response.content),
            }
            
            return is_gzip
            
        except Exception as e:
            print(f"Error verificando gzip: {e}")
            return False
    
    def verify_lazy_loading(self):
        """Verificar lazy loading en templates"""
        try:
            response = self.session.get(self.base_url, timeout=5)
            
            html = response.text
            total_images = html.count('<img')
            lazy_images = html.count('loading="lazy"')
            
            self.results['lazy_loading'] = {
                'total_images': total_images,
                'lazy_images': lazy_images,
                'coverage_percent': round(lazy_images / total_images * 100, 2) if total_images > 0 else 0,
                'status': '✅ OK' if lazy_images > 0 else '❌ No configurado'
            }
            
            return lazy_images > 0
            
        except Exception as e:
            print(f"Error verificando lazy loading: {e}")
            return False
    
    def print_report(self):
        """Mostrar reporte en consola"""
        print("\n" + "="*60)
        print("📊 REPORTE DE OPTIMIZACIÓN - DELCO INVT")
        print("="*60)
        
        print(f"\n🔗 URL Base: {self.results['base_url']}")
        print(f"⏰ Fecha: {self.results['timestamp']}")
        
        print("\n" + "─"*60)
        print("📁 RECURSOS VERIFICADOS")
        print("─"*60)
        
        for resource in self.results['resources']:
            print(f"\n📄 {resource['path']} {resource['cache_quality']}")
            print(f"   Status: {resource['status']}")
            if resource['headers'].get('Cache-Control'):
                print(f"   Cache-Control: {resource['headers']['Cache-Control']}")
            if resource['headers'].get('Content-Encoding'):
                print(f"   Encoding: {resource['headers']['Content-Encoding']}")
        
        print("\n" + "─"*60)
        print("🗜️ COMPRESIÓN")
        print("─"*60)
        gzip_status = "✅ ACTIVADA" if self.results.get('gzip', {}).get('enabled') else "❌ DESACTIVADA"
        print(f"{gzip_status}")
        if self.results.get('gzip'):
            print(f"Encoding: {self.results['gzip']['encoding']}")
        
        print("\n" + "─"*60)
        print("🚀 LAZY LOADING")
        print("─"*60)
        ll = self.results.get('lazy_loading', {})
        print(f"{ll.get('status', '❌ No verificado')}")
        print(f"Imágenes: {ll.get('lazy_images', 0)}/{ll.get('total_images', 0)} con lazy loading")
        print(f"Cobertura: {ll.get('coverage_percent', 0)}%")
        
        print("\n" + "="*60)
    
    def save_report(self, filename='cache_verification.json'):
        """Guardar reporte en JSON"""
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\n✅ Reporte guardado en: {filename}")

# Ejecutar verificación
if __name__ == "__main__":
    # Cambiar URL según tu entorno
    verifier = CacheVerifier("http://localhost:8000")
    
    # Verificar recursos típicos
    resources = [
        "/",
        "/static/css/app.css",
        "/static/img/delco.png",
        "/static/js/bootstrap.bundle.min.js",
    ]
    
    for resource in resources:
        print(f"Verificando: {resource}...")
        verifier.check_resource(resource)
    
    print("Verificando compresión...")
    verifier.verify_gzip()
    
    print("Verificando lazy loading...")
    verifier.verify_lazy_loading()
    
    verifier.print_report()
    verifier.save_report()
```

### Ejecutar

```bash
# En PowerShell
cd C:\Users\DelcoChile TI\Desktop\APPS PROG\DELCO_INVT
python verify_optimization.py
```

---

## 5. MATRIZ DE VERIFICACIÓN

| Componente | Estado Actual | Estado Esperado | Prioridad |
|------------|--------|---------|-----------|
| Cache Headers | ❌ NO | ✅ Configurado | 🔴 Alta |
| Lazy Loading | ❌ NO | ✅ Implementado | 🟠 Media |
| GZIP/Deflate | ❓ Desconocido | ✅ Activado | 🟠 Media |
| .htaccess | ❌ NO existe | ✅ Crear | 🟡 Baja |
| Django Cache | ❌ NO | ✅ Configurado | 🔴 Alta |
| CDN Cache | ✅ Presente | ✅ Optimizado | 🟡 Baja |

---

## 6. CHECKLIST DE ESTADO

### ✅ Paso 1: Verificación
- [ ] Cache Headers en CSS/JS
- [ ] Lazy Loading en imágenes
- [ ] GZIP compresión activa
- [ ] .htaccess presente
- [ ] Django cache configurado

### ✅ Paso 2: Implementación
- [ ] Archivos creados:
  - [ ] OPTIMIZACION_CACHE_LAZYLOADING.md
  - [ ] .htaccess
  - [ ] CONFIGURACION_CACHE_DJANGO.py
  - [ ] IMPLEMENTACION_LAZY_LOADING.md
  - [ ] VERIFICACION_OPTIMIZACION.md

### ✅ Paso 3: Testing
- [ ] Lighthouse audit > 90
- [ ] LCP < 2.5s
- [ ] Lazy loading > 80%
- [ ] GZIP activo

---

## 7. PRÓXIMOS PASOS

1. **Esta semana**:
   - Implementar .htaccess
   - Configurar Django cache
   - Aplicar lazy loading

2. **Próxima semana**:
   - Testing completo
   - Monitoreo con Lighthouse
   - Rollout a producción

3. **Largo plazo**:
   - Optimizar imágenes (WebP)
   - Service Worker
   - Redis en producción

---

**Documento de verificación completado ✅**
