# Alcance MVP vs Fase 2 (Alineado al PDF)

## Criterio

`MVP` = necesario para operar y reducir errores criticos del requerimiento.

`Fase 2` = mejora de capacidad o integracion avanzada no bloqueante para salida controlada.

Actualizacion: 2026-07-15 — MVP cerrado en operacion; ver `MATRIZ_TRAZABILIDAD_PDF.md` (siguiente bloque).

---

## MVP (Obligatorio)

### 1) Clientes y ficha unica (PDF 2 y 3)

- Gestion de clientes (crear, editar, listar, exportar, importar).
- Campos minimos operativos cliente/medidor/modem/SIM-IP.
- Defaults operativos para evitar vacios no controlados.

### 2) Validaciones obligatorias (PDF 4)

- IP: formato, duplicidad, regla de puerto.
- Medidor: serie repetida/asignada.
- Modem: asignacion basica y estado minimo.
- Mensajes de bloqueo/advertencia consistentes.

### 3) OT basica (PDF 5)

- Carga individual/masiva minima.
- Estado inicial y seguimiento minimo.
- Regla de duplicidad minima por cliente/requerimiento.

### 4) Roles y permisos (PDF 11)

- Acceso por rol para modulos principales.
- Restriccion por accion sensible.
- Perfil de solo lectura efectivo (rol AUDITOR).

### 5) Trazabilidad base (PDF 12)

- Registrar al menos usuario, fecha, accion y entidad afectada en cambios criticos.

### 6) Dashboard/alertas minimas (PDF 7 y 13)

- KPI base: total clientes, duplicados IP/medidor, OT abiertas/pendientes.
- Alertas minimas para errores operativos criticos (incl. MoreApp / criticas).

### 7) Terreno via MoreApp (PDF 6 — decision de alcance)

- Sync carpetas + webhook + cola operacional.
- **No** incluye app movil Delco.

### 8) Reportes operativos minimos (PDF 9)

- Hub de 19 informes, export Excel y PDF basico, filtros por periodo/estado/tipo.

### 9) Integraciones minimas (PDF 8 — MVP)

- Import/export Excel + MoreApp.
- API bidireccional queda en Fase 2.

---

## Fase 2 (Posterior al MVP)

### 1) Integracion terreno avanzada (PDF 6 y 8)

- Integracion bidireccional robusta con MoreApp/API.
- Adjuntos multimedia y georreferencia con validacion avanzada.

### 2) Reporteria avanzada (PDF 9)

- Reportes programados / PDF avanzado adicional al export basico ya entregado.

### 3) Catalogo causa/solucion completo (PDF 10)

- Catalogo maestro con mantenimiento por negocio.
- Reglas de recomendacion automatica.

### 4) Auditoria detallada por campo (PDF 12)

- Valor anterior/nuevo por campo en mas flujos.
- Motivo obligatorio por cambio sensible.

### 5) Backlog operativo diferido (sin numero PDF propio)

- Pareja de tecnicos en UI.
- Reasignacion OT pulida.
- Campos denormalizados MoreApp (filtros KPI sin escanear JSON).

---

## Soporte operativo (no es Fase 2 ni punto PDF nuevo)

Optimizacion de rendimiento para volumen alto (paginacion, cache, autosync off por defecto). Ver acta en `ACTAS_CIERRE_PUNTOS.md` y commit `344a525`.

---

## Siguiente bloque (prioridad post-MVP — 2026-07-15)

1. **Ops MoreApp (Puntos 6 y 8):** checklist `MOREAPP_OPS_CHECKLIST.md` (carpetas, sync manual o cron, variables `MOREAPP_*`, despliegue pull+Restart). Sin nuevas features de API.
2. Validacion residual Punto 7 solo si negocio marca una alarma del PDF faltante.
3. Cualquier item de Fase 2 requiere aprobacion explicita.

---

## Fuera de alcance Semana 1 (historico)

1. Rediseno visual no funcional.
2. Integraciones nuevas no exigidas para puntos 1 a 4.
3. Optimizaciones no relacionadas a validaciones, datos o permisos.
   - Nota 2026-07-15: la optimizacion de escala se admite despues del MVP como soporte operativo documentado, no como punto PDF.

---

## Cierre de alcance (aceptacion)

Se considera alcance cerrado cuando:

1. Cada item MVP tiene owner y criterio de aceptacion.
2. Cada item Fase 2 queda explicitamente diferido.
3. No quedan tareas sin referencia al PDF.

Estado 2026-07-15: criterios 1–3 cumplidos para MVP; Fase 2 diferida; siguiente bloque = ops MoreApp.
