# 🚀 IMPLEMENTACIÓN DE LAZY LOADING (Carga Diferida)

## DELCO INVT - Guía Paso a Paso

---

## 1. ¿QUÉ ES LAZY LOADING?

Lazy Loading es una técnica que **retrasa la carga de recursos** hasta que realmente se necesitan (cuando el usuario los ve).

### Beneficios:
- ✅ Reduce tiempo de carga inicial (LCP)
- ✅ Ahorra ancho de banda (especialmente móvil)
- ✅ Mejora Core Web Vitals
- ✅ Sin JavaScript adicional necesario (nativo)
- ✅ Compatible con 95%+ navegadores modernos

### Soportado en:
- ✅ Chrome 76+ (2019)
- ✅ Firefox 75+ (2020)
- ✅ Safari 15.1+ (2021)
- ✅ Edge 79+ (2020)
- ⚠️ IE 11 (no soporta, pero carga normalmente)

---

## 2. IMPLEMENTACIÓN EN TEMPLATES HTML

### 2.1 Imágenes Básicas

#### ❌ ANTES (sin lazy loading)
```html
<img src="{% static 'img/delco.png' %}" 
     alt="Logo Delco" 
     class="logo">
```

#### ✅ DESPUÉS (con lazy loading)
```html
<img src="{% static 'img/delco.png' %}" 
     alt="Logo Delco" 
     class="logo"
     loading="lazy"
     decoding="async">
```

**Atributos:**
- `loading="lazy"` - Carga diferida cuando se acerca al viewport
- `decoding="async"` - Decodificar imagen en paralelo (no bloquea el render)

---

### 2.2 Imágenes con Placeholder

```html
<!-- Imagen con placeholder mientras carga -->
<img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 300'%3E%3Crect fill='%23f0f0f0' width='400' height='300'/%3E%3C/svg%3E"
     data-src="{% static 'img/producto-1.jpg' %}"
     alt="Producto 1"
     class="img-fluid product-image"
     loading="lazy"
     decoding="async">
```

---

### 2.3 Imágenes Responsivas (srcset)

```html
<img src="{% static 'img/hero-small.jpg' %}"
     srcset="{% static 'img/hero-small.jpg' %} 480w,
             {% static 'img/hero-medium.jpg' %} 768w,
             {% static 'img/hero-large.jpg' %} 1200w"
     sizes="(max-width: 480px) 480px,
            (max-width: 768px) 768px,
            1200px"
     alt="Hero Banner"
     class="img-fluid"
     loading="lazy"
     decoding="async">
```

---

### 2.4 Iframes con Lazy Loading

```html
<!-- YouTube, Maps, etc. -->
<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"
        title="Video"
        class="w-100"
        loading="lazy"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowfullscreen>
</iframe>
```

---

## 3. APLICAR A TEMPLATES DELCO INVT

### 3.1 Modificar `templates/base.html`

```html
<!-- En la sección HEAD -->
<head>
    <!-- ... otros tags ... -->
    
    <!-- Preload de recursos críticos -->
    <link rel="preload" 
          href="{% static 'css/app.css' %}" 
          as="style">
    <link rel="preload" 
          href="{% static 'js/main.js' %}" 
          as="script">
    
    <!-- Prefetch de recursos secundarios -->
    <link rel="prefetch" 
          href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    
    <!-- Preconnect a CDNs -->
    <link rel="preconnect" href="https://cdn.jsdelivr.net">
    <link rel="preconnect" href="https://code.jquery.com">
    
    <!-- DNS Prefetch -->
    <link rel="dns-prefetch" href="https://cdn.datatables.net">
</head>

<body>
    <!-- ... contenido ... -->
    
    <!-- Script para verificar soporte Lazy Loading -->
    <script>
    // Verificar si el navegador soporta lazy loading nativo
    if ('loading' in HTMLImageElement.prototype) {
        console.log('✅ Lazy Loading nativo soportado');
    } else {
        console.warn('⚠️ Lazy Loading no soportado, cargar polyfill');
        // Cargar polyfill si es necesario
        // <script src="https://cdn.jsdelivr.net/npm/native-lazyload@17.3.0/dist/native-lazyload.umd.js"></script>
    }
    </script>
</body>
```

---

### 3.2 Modificar `templates/partials/navbar.html`

```html
<!-- Logo con lazy loading -->
<img src="{% static 'img/delco.png' %}" 
     alt="Logo DELCO" 
     height="40"
     loading="lazy"
     decoding="async"
     class="navbar-logo">

<!-- Si hay un icono de usuario -->
<img src="{% static 'img/avatar.png' %}" 
     alt="Avatar"
     class="avatar-img"
     loading="lazy"
     decoding="async">
```

---

### 3.3 Modificar `templates/dashboards/admin_dashboard.html`

```html
<!-- Gráficos e imágenes en dashboard -->
<div class="card">
    <img src="{% static 'img/chart-placeholder.jpg' %}" 
         alt="Gráfico Vendas"
         class="card-img-top"
         loading="lazy"
         decoding="async">
</div>

<!-- Banderas o iconos -->
{% for cliente in clientes %}
<div class="cliente-item">
    {% if cliente.imagen %}
    <img src="{{ cliente.imagen.url }}"
         alt="{{ cliente.nombre }}"
         loading="lazy"
         decoding="async"
         class="cliente-img">
    {% endif %}
    <h5>{{ cliente.nombre }}</h5>
</div>
{% endfor %}
```

---

### 3.4 Modificar `templates/ordenes/list.html`

```html
<!-- Si hay imágenes en listados -->
<table class="table table-striped">
    <tbody>
    {% for orden in ordenes %}
        <tr>
            <td>{{ orden.id }}</td>
            {% if orden.foto %}
            <td>
                <img src="{{ orden.foto.url }}"
                     alt="Foto Orden"
                     loading="lazy"
                     decoding="async"
                     style="max-width: 50px; height: auto;">
            </td>
            {% endif %}
            <td>{{ orden.descripcion }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
```

---

### 3.5 Modificar `templates/inventario/list.html`

```html
<!-- Imágenes de productos con lazy loading -->
<div class="row">
{% for producto in productos %}
    <div class="col-md-4 mb-4">
        <div class="card h-100">
            {% if producto.imagen %}
            <img src="{{ producto.imagen.url }}"
                 alt="{{ producto.nombre }}"
                 class="card-img-top"
                 loading="lazy"
                 decoding="async"
                 style="object-fit: cover; height: 200px;">
            {% endif %}
            <div class="card-body">
                <h5 class="card-title">{{ producto.nombre }}</h5>
                <p class="card-text">{{ producto.descripcion }}</p>
            </div>
        </div>
    </div>
{% endfor %}
</div>
```

---

## 4. LAZY LOADING PARA DataTables

### Opción A: Paginación (Recomendado)

```html
<script>
$(document).ready(function() {
    $('#dataTable').DataTable({
        // Carga diferida para grandes datasets
        deferRender: true,
        
        // Mostrar 25 filas por página
        pageLength: 25,
        
        // Opciones de paginación
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "Todo"]],
        
        // Lazy loading con AJAX (si tienes API backend)
        serverSide: false,  // Cambiar a true si usas server-side rendering
        
        // Otros ajustes
        language: {
            url: "https://cdn.datatables.net/plug-ins/1.13.7/i18n/es-ES.json"
        }
    });
});
</script>
```

### Opción B: Server-Side Rendering (Para datos muy grandes)

```python
# En views.py
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["POST"])
def ordenes_ajax(request):
    """DataTable server-side data source"""
    draw = int(request.POST.get('draw', 1))
    start = int(request.POST.get('start', 0))
    length = int(request.POST.get('length', 25))
    search = request.POST.get('search[value]', '')
    
    # Consulta con paginación
    queryset = Orden.objects.all()
    
    # Buscar
    if search:
        queryset = queryset.filter(
            Q(id__icontains=search) |
            Q(descripcion__icontains=search)
        )
    
    # Contar total
    total = queryset.count()
    
    # Paginar
    ordenes = queryset[start:start + length]
    
    # Formatear respuesta
    data = [{
        'id': o.id,
        'descripcion': o.descripcion,
        'estado': o.get_estado_display(),
    } for o in ordenes]
    
    return JsonResponse({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': total,
        'data': data,
    })
```

```html
<!-- En template -->
<table id="dataTable" class="table table-striped" width="100%">
    <thead>
        <tr>
            <th>ID</th>
            <th>Descripción</th>
            <th>Estado</th>
        </tr>
    </thead>
</table>

<script>
$(document).ready(function() {
    $('#dataTable').DataTable({
        deferRender: true,
        pageLength: 25,
        serverSide: true,
        ajax: {
            url: "{% url 'api_ordenes_ajax' %}",
            type: 'POST',
            data: function(d) {
                d.csrfmiddlewaretoken = $('[name=csrfmiddlewaretoken]').val();
            }
        },
        columns: [
            { data: 'id' },
            { data: 'descripcion' },
            { data: 'estado' }
        ]
    });
});
</script>
```

---

## 5. LAZY LOADING CON JAVASCRIPT PERSONALIZADO

Para navegadores antiguos o casos especiales:

```html
<script>
// Lazy loading manual con Intersection Observer
document.addEventListener('DOMContentLoaded', function() {
    const images = document.querySelectorAll('img[loading="lazy"]');
    
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src || img.src;
                    img.classList.add('loaded');
                    imageObserver.unobserve(img);
                }
            });
        });
        
        images.forEach(img => imageObserver.observe(img));
    } else {
        // Fallback: cargar todas si no soporta
        images.forEach(img => {
            img.src = img.dataset.src || img.src;
        });
    }
});
</script>

<style>
/* Efecto de fade-in cuando carga */
img.loaded {
    animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}
</style>
```

---

## 6. CHECKLIST DE IMPLEMENTACIÓN

### Fase 1: Templates Principales (30 min)
- [ ] Editar `templates/base.html` (agregar preload/prefetch)
- [ ] Editar `templates/partials/navbar.html` (logo, avatars)
- [ ] Revisar `templates/partials/sidebar.html` (si tiene imágenes)

### Fase 2: Dashboards (20 min)
- [ ] Actualizar `templates/dashboards/admin_dashboard.html`
- [ ] Actualizar `templates/dashboards/inventario_dashboard.html`
- [ ] Actualizar otros dashboards similares

### Fase 3: Listados (30 min)
- [ ] Actualizar `templates/ordenes/list.html`
- [ ] Actualizar `templates/inventario/list.html`
- [ ] Actualizar `templates/clientes/list.html`
- [ ] Actualizar `templates/usuarios/list.html`

### Fase 4: Detalles (20 min)
- [ ] Actualizar `templates/ordenes/detalle.html`
- [ ] Actualizar otros templates de detalle

### Fase 5: Testing (15 min)
- [ ] Verificar en Chrome (F12 → Network → Img)
- [ ] Verificar en Firefox
- [ ] Verificar en móvil (DevTools)
- [ ] Usar Lighthouse para audit

---

## 7. VERIFICACIÓN Y TESTING

### En Chrome DevTools

1. Abrir F12
2. Ir a la pestaña **Network**
3. Recargar la página
4. Filtrar por **Img**
5. Desplazarse hacia abajo
6. Ver cómo se cargan las imágenes bajo demanda

### Usando Lighthouse

1. F12 → Lighthouse
2. Click en "Analyze page load"
3. Buscar en el reporte:
   - "Offscreen images" (debe ser bajo)
   - "Defer offscreen images" (recomendación)

### Línea de comando (curl)

```bash
# Verificar headers de una imagen
curl -i https://inventario.delcochile/static/img/delco.png | grep -E "Cache|Expires"

# Verificar si lazy loading está presente
curl https://inventario.delcochile/ | grep 'loading="lazy"'
```

---

## 8. ALTERNATIVAS Y MEJORAS

### Polyfill para navegadores antiguos
```html
<!-- Para IE 11 y navegadores sin soporte -->
<script src="https://cdn.jsdelivr.net/npm/native-lazyload@17.3.0/dist/native-lazyload.umd.js"></script>
```

### Blur-up effect
```html
<!-- Mostrar versión borrosa mientras carga -->
<img src="data:image/jpeg;base64,..."
     data-src="imagen-real.jpg"
     alt="Imagen"
     loading="lazy"
     class="blur-up">

<style>
img.blur-up {
    filter: blur(10px);
    transition: filter 0.3s ease-out;
}
img.blur-up.loaded {
    filter: blur(0);
}
</style>
```

### Progressive Image Loading
```html
<!-- Cargar versión de baja calidad primero -->
<picture>
    <source srcset="image-low.jpg" media="(max-width: 600px)">
    <img src="image-high.jpg"
         alt="Imagen"
         loading="lazy"
         decoding="async">
</picture>
```

---

## 9. IMPACTO ESPERADO

| Métrica | Valor Esperado |
|---------|---|
| LCP (Largest Contentful Paint) | ⬇️ 40-50% |
| FID (First Input Delay) | ⬇️ 20-30% |
| CLS (Cumulative Layout Shift) | ⬇️ 10-15% |
| Total Bytes Transferred | ⬇️ 30-50% |
| Initial Load Time | ⬇️ 50-70% |

---

## 10. RECURSOS Y REFERENCIAS

- MDN: https://developer.mozilla.org/en-US/docs/Web/Performance/Lazy_loading
- W3C: https://html.spec.whatwg.org/multipage/urls-and-fetches.html#lazy-loading
- Can I Use: https://caniuse.com/loading-lazy-loading
- Google Web Vitals: https://web.dev/vitals/

---

**Implementación completada ✅**
