# Alcance MVP vs Fase 2 (Alineado al PDF)

## Criterio

`MVP` = necesario para operar y reducir errores criticos del requerimiento.

`Fase 2` = mejora de capacidad o integracion avanzada no bloqueante para salida controlada.

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
- Alertas minimas para errores operativos criticos.

---

## Fase 2 (Posterior al MVP)

### 1) Integracion terreno avanzada (PDF 6 y 8)

- Integracion bidireccional robusta con MoreApp/API.
- Adjuntos multimedia y georreferencia con validacion avanzada.

### 2) Reporteria avanzada (PDF 9)

- Reportes completos por tecnico/empresa/causa.
- Exportacion PDF avanzada y programada.

### 3) Catalogo causa/solucion completo (PDF 10)

- Catalogo maestro con mantenimiento por negocio.
- Reglas de recomendacion automatica.

### 4) Auditoria detallada por campo (PDF 12)

- Valor anterior/nuevo por campo.
- Motivo obligatorio por cambio sensible.

---

## Fuera de alcance Semana 1

1. Rediseno visual no funcional.
2. Integraciones nuevas no exigidas para puntos 1 a 4.
3. Optimizaciones no relacionadas a validaciones, datos o permisos.

---

## Cierre de alcance (aceptacion)

Se considera alcance cerrado cuando:

1. Cada item MVP tiene owner y criterio de aceptacion.
2. Cada item Fase 2 queda explicitamente diferido.
3. No quedan tareas sin referencia al PDF.
