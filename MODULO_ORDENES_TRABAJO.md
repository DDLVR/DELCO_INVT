# Módulo de Órdenes de Trabajo

## Descripción General
Sistema de gestión de órdenes de trabajo con control de acceso basado en roles y flujo de estados simplificado.

---

## Roles y Permisos

### ADMIN y ADMINISTRATIVO
- ✅ Crear nuevas órdenes de trabajo
- ✅ Ver todas las órdenes (filtros disponibles)
- ✅ Modificar cualquier orden
- ✅ Cambiar a cualquier estado
- ✅ Asignar técnicos responsables

### TECNICO
- ✅ Ver solo sus asignaciones (órdenes donde es técnico responsable)
- ❌ No puede crear órdenes
- ❌ No puede editar los campos de la orden
- ✅ Puede cambiar estado de PENDIENTE → REALIZADO
- ✅ Puede cambiar a CANCELADA (solo si está en PENDIENTE)

### GERENCIA y AUDITOR
- ✅ Ver todas las órdenes
- ❌ No pueden crear ni modificar

---

## Estados de las Órdenes

### Estados disponibles:
1. **PENDIENTE** (inicial)
   - Estado por defecto al crear una orden
   - Técnico debe proceder a realizar el trabajo

2. **REALIZADO**
   - Asignado por el técnico cuando completa el trabajo
   - Solo técnico responsable puede cambiar de PENDIENTE → REALIZADO

3. **CANCELADA**
   - Estado de cancelación
   - Puede asignarse desde cualquier estado
   - Admins: pueden cambiar a CANCELADA en cualquier momento
   - Técnicos: pueden cambiar a CANCELADA solo si está PENDIENTE

---

## Flujo Operativo

```
ADMIN/ADMINISTRATIVO
        │
        ├─► Crea orden (estado: PENDIENTE)
        │
        └─► Asigna TECNICO responsable
                │
                ├─► Técnico ve la orden en su lista
                │
                ├─► Técnico realiza el trabajo
                │
                └─► Técnico cambia estado a REALIZADO
                        │
                        ├─► Registro de fecha/hora de fin
                        │
                        └─► Trabajo completado ✓
```

---

## Funcionalidades Implementadas

### 1. Crear Orden de Trabajo
- **Ruta:** `/ordenes/crear/`
- **Permisos:** ADMIN, ADMINISTRATIVO
- **Campos:**
  - Título (obligatorio)
  - Descripción
  - Tipo de Trabajo (obligatorio)
  - Técnico Responsable (obligatorio)
  - Cliente (opcional)
  - Observaciones Iniciales
- **Estado inicial:** PENDIENTE
- **Redirección:** Detalle de la orden creada

### 2. Listar Órdenes
- **Ruta:** `/ordenes/`
- **Permisos:** Todos (con vista limitada por rol)
- **Filtros disponibles:**
  - Estado
  - Tipo de Trabajo
  - Técnico (solo visible para ADMIN/ADMINISTRATIVO)
  - Cliente
  - Búsqueda por título/descripción
- **Funcionalidad por rol:**
  - ADMIN/ADMINISTRATIVO: ven todas las órdenes
  - TECNICO: solo ve sus asignaciones
  - GERENCIA/AUDITOR: ven todas (solo lectura)

### 3. Detalle de Orden
- **Ruta:** `/ordenes/<id>/`
- **Información mostrada:**
  - Datos generales (título, tipo, descripción)
  - Asignación (cliente, técnico responsable)
  - Equipos utilizados
  - Adjuntos (fotos, PDFs)
  - Control de estado
- **Cambio de estado:**
  - ADMIN/ADMINISTRATIVO: botón desplegable con todos los estados
  - TECNICO: solo opción PENDIENTE → REALIZADO

### 4. Cambiar Estado
- **Ruta:** `/ordenes/<id>/cambiar-estado/`
- **Método:** POST
- **Validación:** Controla permisos por rol
- **Auditoría:** Registra quién hizo el cambio

---

## Restricciones de Acceso

| Acción | ADMIN | ADMIN | TECNICO | GERENCIA | AUDITOR |
|--------|-------|--------|---------|----------|---------|
| Crear orden | ✅ | ✅ | ❌ | ❌ | ❌ |
| Ver todas | ✅ | ✅ | ❌ | ✅ | ✅ |
| Ver propias | ✅ | ✅ | ✅ | ✅ | ✅ |
| Modificar | ✅ | ✅ | ❌ | ❌ | ❌ |
| Cambiar estado | ✅ | ✅ | ✅* | ❌ | ❌ |

*TECNICO solo puede cambiar: PENDIENTE → REALIZADO o CANCELADA

---

## Integración Futura con MoreApp

### Pendiente de Implementación:
1. Webhook de MoreApp para actualizar estado de órdenes
2. Validación de formularios MoreApp antes de cerrar orden
3. Adjuntos automáticos desde MoreApp (fotos, documentos)
4. Sincronización de datos del formulario (equipos, ubicaciones, etc.)

---

## Tablas de Base de Datos

### OrdenTrabajo (actualizada)
```python
ESTADO_CHOICES = [
    ('PENDIENTE', 'Pendiente'),      # Estado inicial
    ('REALIZADO', 'Realizado'),      # Trabajo completado
    ('CANCELADA', 'Cancelada'),      # Orden cancelada
]
```

### Campos de Auditoría
- `creada_por`: Usuario que crea la orden
- `fecha_creacion`: Cuando se crea
- `fecha_asignacion`: Cuando se asigna al técnico
- `fecha_fin_ejecucion`: Cuando técnico marca REALIZADO

---

## Ejemplo de Uso

### Crear una orden:
```bash
POST /ordenes/crear/
{
    "titulo": "Instalación medidor P123",
    "descripcion": "Instalación en Av. Principal 456",
    "tipo_trabajo": "INSTALACION",
    "tecnico_responsable": 5,      # ID del técnico
    "cliente": 3,                   # ID del cliente (opcional)
    "observaciones_tecnicas": "Llevar herramientas especiales"
}
```

### Técnico marca como realizado:
```bash
POST /ordenes/1/cambiar-estado/
{
    "nuevo_estado": "REALIZADO"
}
```

---

## Comandos Útiles

```bash
# Ver órdenes por estado
python manage.py shell
>>> from ordenes_trabajo.models import OrdenTrabajo
>>> OrdenTrabajo.objects.filter(estado='PENDIENTE')
>>> OrdenTrabajo.objects.filter(estado='REALIZADO')

# Buscar órdenes de un técnico
>>> OrdenTrabajo.objects.filter(tecnico_responsable__rut='14785236-9')
```

---

## Notas

- El módulo está listo para la integración con MoreApp
- Los cambios de estado están auditados automáticamente
- El flujo es simple y directo: PENDIENTE → REALIZADO
- Las fechas de inicio/fin se registran automáticamente
- Los permisos se validan en cada vista

---

## Próximos Pasos

1. ✅ Estados simplificados (PENDIENTE, REALIZADO, CANCELADA)
2. ✅ Control de roles ADMIN/ADMINISTRATIVO/TECNICO
3. ✅ Cambio de estado por rol
4. ⏳ Integración MoreApp (webhook)
5. ⏳ Validación de formularios MoreApp
6. ⏳ Reportes y analytics
