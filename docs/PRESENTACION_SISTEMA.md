# DELCO Inventario — Desglose del sistema

Documento para presentar el alcance del sistema a gerencia / operaciones.

**URL producción:** https://inventario.delcochile.cl  
**Qué es:** plataforma web que unifica inventario (medidores, SIM, módems), clientes, órdenes de trabajo, ingreso desde MoreApp en terreno, reportes y auditoría.

---

## 1. Mensaje en una frase

Oficina y terreno trabajan sobre **un solo sistema de registro**: equipos, clientes, OT e informes MoreApp quedan trazados y auditados.

---

## 2. Módulos (lo que ven los usuarios)

### Acceso y roles
| Rol | Enfoque |
|-----|---------|
| ADMIN | Todo: usuarios, inventario, clientes, OT, MoreApp, reportes, auditoría, soporte |
| ADMINISTRATIVO | Operación diaria (sin gestión profunda de usuarios) |
| TECNICO | Sus OT y trabajo en terreno |
| GERENCIA | Paneles y visión agregada |
| AUDITOR | Consulta y trazabilidad |

Login con RUT · perfiles · dashboards por rol.

### Inventario
- Medidores, tarjetas SIM y módems
- Estados y ubicaciones (bodega, trayecto, instalado, etc.)
- Movimientos / kardex (quién movió qué, desde dónde hacia dónde)
- Importar / exportar Excel · edición masiva
- Historial por equipo

### Clientes
- Ficha del punto de suministro (nº cliente, dirección, IP, medidor, módem, proyecto, etc.)
- Restricciones de visita / IP con justificación
- Historial de proyectos asociados (Actual / Reemplazado)
- Importar / exportar · edición y eliminación masiva
- Vista historial con OT, MoreApp y auditoría de la ficha

### Órdenes de trabajo (OT)
- Ciclo: creada → asignada → ejecución → validación / cierre
- Tipos: instalación, cambio, retiro, mantención, etc.
- Asignación a técnico · adjuntos · observaciones
- Importar / exportar · acciones masivas
- Alertas de posible trabajo duplicado / reincidencia

### MoreApp (terreno)
- Sincronización de formularios de campo
- Listado, detalle, cola de pendientes / advertencias
- Cruce automático con inventario y clientes
- Bloqueos operativos visibles (ej. módem sin medidor instalado)
- Revisión: pendiente · con advertencia · revisado · descartado

### Reportes
- Hub de informes operativos y de calidad
- Exportación Excel y PDF
- Ejemplos: OT por técnico/fecha, reincidentes, IP/medidor duplicado, pendientes STB/SCi4, etc.

### Auditoría
- Registro de cambios relevantes (quién, qué campo, valor anterior/nuevo, motivo)
- Consulta en `/auditoria/`

### Catálogos y soporte
- Catálogo de diagnóstico (causas / soluciones)
- Tickets internos de soporte / bugs

---

## 3. Flujo operativo (visión gerencial)

```text
MoreApp (terreno)
       │
       ▼
 Sincronización / webhook
       │
       ├─► Actualiza inventario (movimientos)
       ├─► Cruza / alerta sobre clientes
       └─► Vincula o alimenta OT
              │
              ▼
     Validación administrativa
              │
              ▼
     Reportes + Auditoría
```

---

## 4. Capas técnicas (para TI, no hace falta en toda la sala)

| Capa | Contenido |
|------|-----------|
| Apps Django | `usuarios`, `clientes`, `inventario`, `ordenes_trabajo`, `integraciones`, `importaciones`, `reportes`, `catalogos`, `soporte`, `web` |
| UI | Plantillas en `templates/` · CSS/JS en `static/` |
| Reglas | Validadores, métricas dashboard, historial de proyectos, lector MoreApp |
| Datos | MySQL en hosting · SQLite solo en desarrollo local |
| Deploy | Passenger / cPanel · `requirements.txt` · Python 3.8 en producción |

---

## 5. Entregado recientemente (resumen de avance)

- Restricciones de cliente con justificación (punto PDF)
- Alarmas de analistas en dashboard (incl. posibles duplicados)
- Historial de proyectos del cliente (sin fecha “Hasta”; estados Actual / Reemplazado)
- Proyecto en edición como lista desplegable de valores existentes
- Mejoras de alertas MoreApp (mensajes legibles; corrección charset en observaciones)
- Corrección de bugs: movimientos duplicados MoreApp, `medidor_actual` al editar, búsqueda de cliente activa, etc.

---

## 6. Qué no es “producto” (interno / no mostrar en demo)

- Carpetas `venv/`, `venv38/`, `db.sqlite3`, `Registros/` → entorno local / datos de sync
- Scripts en `scripts/` y comandos `*_demo*` / `generar_datos_prueba` → solo desarrollo o carga puntual
- Tests unitarios → calidad interna
- Documento antiguo de esqueleto técnico (reemplazado por este desglose)

---

## 7. Cómo navegar en una demo corta (10–15 min)

1. Login ADMIN → dashboard (alarmas)
2. Inventario → un medidor / movimiento
3. Clientes → ficha + historial de proyecto
4. Órdenes de trabajo → una OT
5. Reportes MoreApp → sync / una alerta legible
6. Reportes operativos → export Excel
7. Auditoría → un cambio reciente

---

*Última actualización: julio 2026*
