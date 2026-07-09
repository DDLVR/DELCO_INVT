# Matriz de Trazabilidad - Requerimiento PDF

## Regla de trabajo

Todo cambio debe mapear a un punto del PDF.
Si no existe punto asociado, no se implementa sin aprobacion explicita.

Estado:

- `LISTO`: cumple el requerimiento con evidencia.
- `PARCIAL`: existe avance, pero faltan condiciones de aceptacion.
- `FALTA`: no implementado.

---

## Vista general (Puntos 1 a 15)

| Punto PDF | Requerimiento | Estado actual | Objetivo Semana 1 |
|---|---|---|---|
| 1 | Objetivo general | LISTO | Definir alcance MVP sin desviaciones |
| 2 | Alcance plataforma | LISTO | Congelar alcance de modulos minimos |
| 3 | Ficha unica por cliente | LISTO | Cerrar modelo de datos y defaults |
| 4 | Validaciones obligatorias | LISTO | Implementar validaciones criticas |
| 5 | Gestion de OT | LISTO | Definir backlog minimo y reglas base |
| 6 | Aplicacion de terreno | FASE2 | Dejar en Fase 2 documentada |
| 7 | Alarmas y alertas | LISTO | Definir catalogo de alertas criticas |
| 8 | Integraciones | LISTO | Mantener import/export y definir API futura |
| 9 | Informes y reportes | LISTO | Definir set minimo obligatorio |
| 10 | Catalogo causa/solucion | FASE2 | DiseÃ±ar estructura de catalogo |
| 11 | Roles de usuario | LISTO | Cerrar matriz de permisos por rol |
| 12 | Trazabilidad y auditoria | LISTO | Definir esquema tecnico de auditoria |
| 13 | Dashboard principal | LISTO | Definir KPIs minimos obligatorios |
| 14 | Requerimientos tecnicos | LISTO | Checklist tecnico de cumplimiento |
| 15 | Evitar errores operativos | LISTO | Alinear validaciones P3+P4 con este objetivo |

---

## Backlog ejecutable Semana 1 (Puntos 1 a 4)

### B1 - Cierre de alcance MVP (PDF 1 y 2)

- Punto PDF: 1, 2
- Estado: PARCIAL
- Tarea: cerrar lista MVP/Fase 2 y congelar alcance de semana
- Criterio de aceptacion:
  - Existe lista `MVP` y lista `Fase 2` sin ambiguedades.
  - Cada modulo tiene estado `Incluido/Excluido`.
- Evidencia:
  - Documento aprobado en repo.

### B2 - Diccionario de datos v1 (PDF 3)

- Punto PDF: 3
- Estado: LISTO
- Tarea: modelo de ficha cliente cerrado con defaults y reglas de unicidad operativa
- Criterio de aceptacion:
  - Campos obligatorios/opcionales definidos. (`OK`)
  - Defaults definidos (`SIN PROYECTO`, `SIN PERFIL`, etc). (`OK`)
  - Reglas de unicidad documentadas. (`OK`)
- Evidencia:
  - Documento de diccionario: `DICCIONARIO_DATOS_CLIENTE_PUNTO_3.md`
  - Acta de cierre: `ACTAS_CIERRE_PUNTOS.md`
  - Pruebas automatizadas:
    - `clientes.tests.ClienteFlujoViewTests`
    - `clientes.tests.ClienteImportarViewTests`
    - `importaciones.tests.ImportacionClientesModoTests`

### B3 - Validaciones criticas IP/Medidor/Modem (PDF 4)

- Punto PDF: 4
- Estado: LISTO
- Tarea: validaciones unificadas en crear/importar y reglas de edicion para duplicidad de serie
- Criterio de aceptacion:
  - IP valida formato. (`OK`)
  - IP sin puerto genera alerta o bloqueo segun regla definida. (`OK`)
  - Serie de medidor duplicada se controla con regla unica. (`OK`)
  - Mensajes consistentes para usuario. (`OK`)
- Evidencia:
  - Pruebas automatizadas passing:
    - `clientes.tests.ClienteFlujoViewTests`
    - `clientes.tests.ClienteImportarViewTests`
    - `importaciones.tests.ImportacionClientesModoTests`
  - Acta de cierre: `ACTAS_CIERRE_PUNTOS.md`

### B4 - Matriz de permisos por rol (PDF 11)

- Punto PDF: 11
- Estado: LISTO
- Tarea: cerrar matriz rol vs modulo vs accion, usando solo roles existentes (AUDITOR como rol de validacion operativa)
- Mapeo operativo acordado:
  - Administrador => `ADMIN`
  - Analista => `ADMINISTRATIVO`
  - Rol 3 del requerimiento (validacion operativa) => `AUDITOR`
  - Tecnico => `TECNICO`
  - Solo lectura => `AUDITOR`
- Criterio de aceptacion:
  - Rutas protegidas por rol. (`OK`)
  - Usuario sin permiso no puede ejecutar accion. (`OK`)
  - Menus visibles coherentes con rol. (`OK`)
  - Perfil solo lectura mapeado a rol AUDITOR con opciones explicitas de lectura. (`OK`)
- Evidencia:
  - Verificacion de permisos: `VERIFICACION_PERMISOS_ROLES_ACTUALES.md`
  - Matriz final: `MATRIZ_PERMISOS_PUNTO_11.md`
  - Acta de cierre: `ACTAS_CIERRE_PUNTOS.md`
  - Pruebas de matriz por rol: `web.tests.MatrizRolesPunto11Tests`
  - Pruebas por rol en ordenes: `ordenes_trabajo.tests.OrdenesRolesTests`
  - Pruebas perfil solo lectura (AUDITOR): `web.tests.PermisosSoloLecturaAuditorTests`

### B5 - Gestion basica de OT (PDF 5)

- Punto PDF: 5
- Estado: LISTO
- Tarea: dejar base operativa de OT con creacion, importacion, listado por rol y alerta de duplicado
- Criterio de aceptacion:
  - Carga individual minima. (`OK`)
  - Carga masiva minima. (`OK`)
  - Estado inicial y seguimiento basico. (`OK`)
  - Duplicidad minima por cliente. (`OK`)
- Evidencia:
  - Pruebas automatizadas: `ordenes_trabajo.tests.OrdenesBasicasWorkflowTests`
  - Comando de verificacion: `python manage.py test ordenes_trabajo.tests.OrdenesBasicasWorkflowTests -v 1`
  - Acta de cierre: `ACTAS_CIERRE_PUNTOS.md`

### B6 - Trazabilidad y auditoria persistente (PDF 12)

- Punto PDF: 12
- Estado: LISTO
- Tarea: persistir auditoria en base de datos para eventos criticos
- Criterio de aceptacion:
  - Registro de actor, accion, entidad, entidad_id y fecha. (`OK`)
  - Soporte de old/new value y motivo. (`OK`)
  - Integracion con flujos criticos (clientes/importaciones). (`OK`)
  - Evidencia automatizada de persistencia. (`OK`)
- Evidencia:
  - Modelo persistente: `web.models.AuditLog`
  - Servicio actualizado: `web.services.audit.register_audit_event`
  - Pruebas: `web.tests.AuditPersistencePunto12Tests`
  - Acta de cierre: `ACTAS_CIERRE_PUNTOS.md`

---

## No hacer (control de cambios)

1. No agregar nuevas vistas/modulos fuera de puntos 1 a 4 durante esta semana.
2. No cambiar UI por estetica si no mejora cumplimiento de requerimiento.
3. No introducir campos nuevos sin trazabilidad al PDF.

---

## Registro de decisiones

| Fecha | Decision | Punto PDF | Impacto |
|---|---|---|---|
| 2026-07-08 | Importacion clientes con modo incremental por defecto y sync opcional | 2, 4, 15 | Evita perdida de clientes al importar |
| 2026-07-08 | Proyecto vacio => `SIN PROYECTO` | 3 | Normaliza ficha cliente |
| 2026-07-08 | Ultimo perfil carga vacio => `SIN PERFIL` | 3 | Evita nulos operativos en analisis |
| 2026-07-08 | Definicion formal de ficha unica cliente por clave operativa (numero_cliente + serie) con control de duplicado exacto | 3 | Punto 3 queda verificable y trazable en pruebas |
| 2026-07-08 | Cierre tecnico de validaciones criticas (IP/Medidor/Modem) con pruebas automatizadas | 4 | Punto 4 pasa a LISTO con evidencia reproducible |
| 2026-07-08 | Alineacion de permisos por rol con solo roles existentes (AUDITOR como validacion operativa) y verificacion automatizada | 11 | Evita roles inexistentes y clarifica responsabilidad por rol |
| 2026-07-08 | Cierre de punto 11 con mapeo formal Administrador/Analista/Rol de validacion operativa/Tecnico/Solo lectura a roles existentes y pruebas de permisos | 11 | Punto 11 pasa a LISTO con evidencia reproducible |
| 2026-07-09 | Cierre tecnico de gestion basica de OT con creacion, importacion, listado por rol y alerta de duplicidad | 5 | Punto 5 pasa a LISTO con evidencia reproducible |
| 2026-07-09 | Implementacion de auditoria persistente en DB (AuditLog) e integracion con eventos criticos | 12 | Punto 12 pasa a LISTO con evidencia reproducible |
| 2026-07-09 | Cierre set minimo de reportes: exportar clientes/inventario/ordenes accesibles y probados | 9 | Punto 9 pasa a LISTO con evidencia reproducible |
| 2026-07-09 | Cierre dashboard KPIs, errores operativos, alarmas de duplicidad e integracion MoreApp | 7,8,13,15 | Puntos 7,8,13,15 pasan a LISTO |
| 2026-07-09 | Puntos 1,2 cerrados: alcance MVP documentado y congelado en ALCANCE_MVP_FASE2_PDF.md | 1,2 | Puntos 1 y 2 pasan a LISTO |
| 2026-07-09 | Punto 14 cerrado: requerimientos tecnicos validados con django check y migraciones OK | 14 | Punto 14 pasa a LISTO |
| 2026-07-09 | Puntos 6 y 10 diferidos formalmente a Fase 2 | 6,10 | Estado FASE2 documentado |

---

## Checkpoint diario

- [x] Cada tarea del dia tiene punto PDF asociado.
- [x] Cada cambio deja evidencia.
- [x] No hay implementaciones fuera de alcance.
