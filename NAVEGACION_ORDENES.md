# Navegación - Módulo de Órdenes de Trabajo

## 🗂️ Estructura del Sidebar

```
MENÚ (Lateral Izquierdo)
├── Dashboard
├── Órdenes de Trabajo                  ← NUEVO ✨
│   ├── [Enlace principal - Ver todas]
│   └── Nueva Orden                     ← SOLO ADMIN/ADMINISTRATIVO
├── Inventario
├── Movimientos
├── Reportes MoreApp
├── Usuarios
├── Registro de Errores
└── Gestión Clientes
```

---

## 🔗 Rutas y URLs

### Rutas Principales

| Ruta | URL | Nombre | Acceso |
|------|-----|--------|--------|
| Lista de órdenes | `/ordenes/` | `ordenes_list` | Todos |
| Crear orden | `/ordenes/crear/` | `orden_crear` | Admin, Administrativo |
| Detalle orden | `/ordenes/<id>/` | `orden_detalle` | Todos (según permisos) |
| Cambiar estado | `/ordenes/<id>/cambiar-estado/` | `cambiar_estado_orden` | Admin, Administrativo, Técnico |

---

## 📱 Navegación por Rol

### ADMIN
```
Sidebar
└── Órdenes de Trabajo
    ├── Ver todas las órdenes ✅
    └── Crear nueva orden ✅
        → Puede cambiar a cualquier estado
```

### ADMINISTRATIVO
```
Sidebar
└── Órdenes de Trabajo
    ├── Ver todas las órdenes ✅
    └── Crear nueva orden ✅
        → Puede cambiar a cualquier estado
```

### TECNICO
```
Sidebar
└── Órdenes de Trabajo
    ├── Ver solo sus asignaciones ✅
    └── Crear nueva orden ❌
        → Solo puede cambiar: PENDIENTE → REALIZADO
```

### GERENCIA
```
Sidebar
└── Órdenes de Trabajo
    ├── Ver todas las órdenes (lectura) ✅
    └── Crear nueva orden ❌
        → No puede cambiar estado
```

### AUDITOR
```
Sidebar
└── Órdenes de Trabajo
    ├── Ver todas las órdenes (lectura) ✅
    └── Crear nueva orden ❌
        → No puede cambiar estado
```

---

## 🧭 Flujo de Navegación

### Crear una orden (Admin/Administrativo)
```
Dashboard
    ↓
[Sidebar] Órdenes de Trabajo → Nueva Orden
    ↓
/ordenes/crear/
    ↓
Formulario (Título, Tipo, Técnico, Cliente, Observaciones)
    ↓
[Botón: Crear Orden]
    ↓
/ordenes/<id>/  (Detalle automático)
```

### Ver órdenes asignadas (Técnico)
```
Dashboard
    ↓
[Sidebar] Órdenes de Trabajo
    ↓
/ordenes/  (Vista filtrada: solo del técnico)
    ↓
[Click en orden]
    ↓
/ordenes/<id>/
    ↓
[Botón: Cambiar Estado] → PENDIENTE → REALIZADO
    ↓
Estado actualizado ✓
```

### Cambiar estado de una orden (Admin)
```
/ordenes/  (Lista de todas)
    ↓
[Click en orden]
    ↓
/ordenes/<id>/
    ↓
[Sección: Acciones]
[Dropdown: Cambiar Estado]
    ├── REALIZADO
    ├── CANCELADA
    └── PENDIENTE
    ↓
[Botón: Cambiar Estado]
    ↓
Estado actualizado ✓
```

---

## 📍 Breadcrumb Navigation (Pan de Migas)

```
Dashboard > Órdenes de Trabajo > [Estado actual]

Ejemplos:
- Dashboard > Órdenes de Trabajo > Listado
- Dashboard > Órdenes de Trabajo > Crear
- Dashboard > Órdenes de Trabajo > Orden #42
```

---

## ⌨️ Atajos de Teclado (Opcional para futuro)

```
Ctrl + N  → Nueva orden (si estás en /ordenes/)
Ctrl + L  → Ir a lista de órdenes
Esc       → Volver a lista desde detalle
```

---

## 📋 Cambios Realizados en el Código

### 1. **Sidebar (`templates/partials/sidebar.html`)**
- ✅ Agregado enlace a "Órdenes de Trabajo" (visible para todos)
- ✅ Subenlace "Nueva Orden" (visible solo para ADMIN/ADMINISTRATIVO)
- ✅ Estilos aplicados con indentación para submenús

### 2. **URLs Principales (`web/urls.py`)**
- ✅ Importados views de `ordenes_trabajo`
- ✅ Rutas `/ordenes/*` registradas en el sistema
- ✅ URL names: `ordenes_list`, `orden_crear`, `orden_detalle`, `cambiar_estado_orden`

### 3. **Templates**
- ✅ `crear.html`: Estado inicial PENDIENTE
- ✅ `detalle.html`: Botón de estado dinámico por rol
- ✅ `list.html`: Filtros y tabla de órdenes

---

## ✅ Validación de Enlaces

```
✅ /ordenes/                    → Lista de órdenes
✅ /ordenes/crear/              → Crear orden
✅ /ordenes/1/                  → Detalle de orden
✅ /ordenes/1/cambiar-estado/   → Cambiar estado
✅ Sidebar activo dinamicamente → según URL actual
✅ Permisos validados           → por rol de usuario
```

---

## 🎯 Próximos Pasos

1. **Integración MoreApp** (Fase 2)
   - Webhook para actualizar estado automáticamente
   - Adjuntos desde formularios MoreApp

2. **Reportes** (Fase 3)
   - Resumen de órdenes por técnico
   - Estadísticas por tipo de trabajo
   - Exportar datos

3. **Mejoras UI** (Fase 4)
   - Iconos/badges de estado
   - Animaciones de transición
   - Notificaciones en tiempo real

---

## 🔍 Notas Técnicas

- **Template Tags**: Usamos `in` para validar rol en sidebard
- **URL Reversing**: Todas las rutas usan `{% url 'nombre' %}`
- **Active Link**: Sidebar destaca ruta actual con `.active bg-primary`
- **Responsive**: Sidebar adapta tamaño en móvil/tablet

