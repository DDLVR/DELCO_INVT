# Plan Semana 1 - Puntos 1 a 4

## Objetivo de la semana
Dejar cerrados y operativos los puntos 1, 2, 3 y 4 del requerimiento:

1. Alcance y prioridades.
2. Modelo de datos definitivo.
3. Validaciones obligatorias criticas.
4. Roles y permisos.

## Resultado esperado al cierre de la semana

- [ ] Alcance MVP firmado (que entra y que no entra).
- [ ] Diccionario de datos v1 congelado.
- [ ] Validaciones criticas funcionando en crear/editar/importar.
- [ ] Matriz de permisos por rol aplicada y probada.
- [ ] Checklist de pruebas de humo completado.

## Plan diario

### Dia 1 - Alcance y backlog cerrado

- [ ] Definir alcance MVP vs Fase 2.
- [ ] Confirmar reglas de negocio prioritarias (IP, medidor, duplicados, sincronizacion).
- [ ] Priorizar backlog por impacto y urgencia.
- [ ] Definir criterios de aceptacion por modulo.

Entregables Dia 1:

- Documento de alcance final.
- Backlog priorizado (P1/P2/P3).
- Lista de validaciones que bloquean vs solo advierten.

### Dia 2 - Modelo de datos definitivo

- [ ] Revisar campos de Cliente (obligatorio/opcional/default).
- [ ] Revisar entidades y relaciones: Medidor, Modem, SIM/IP, OT, Alerta, Auditoria.
- [ ] Definir reglas de unicidad y coexistencia.

Entregables Dia 2:

- Diccionario de datos v1.
- Matriz de reglas de unicidad.

### Dia 3 - Migraciones y saneamiento basico

- [ ] Crear/ajustar migraciones necesarias.
- [ ] Normalizar defaults y nulos en campos sensibles.
- [ ] Ejecutar validacion de integridad minima en datos existentes.

Entregables Dia 3:

- Migraciones aplicadas en entorno local.
- Nota de cambios de esquema.

### Dia 4 - Validaciones criticas de negocio

- [ ] IP: formato, estado, duplicidad y coherencia con puerto.
- [ ] Medidor: serie repetida, asignacion a cliente activo, consistencia.
- [ ] Modem: estado y asignacion.

Entregables Dia 4:

- Validaciones activas en crear/editar/importar.
- Mensajes de error/advertencia claros y consistentes.

### Dia 5 - Validaciones OT minimas

- [ ] Regla de OT abierta duplicada para cliente/requerimiento.
- [ ] Reincidencia (>2 visitas/6 meses) como alerta.
- [ ] Estados minimos de OT para control operativo.

Entregables Dia 5:

- Reglas OT minimas implementadas.
- Evidencia de pruebas funcionales.

### Dia 6 - Roles y permisos

- [ ] Matriz final por rol: Admin, Administrativo, Tecnico, Gerencia, Auditor.
- [ ] Aplicar restricciones por vista y accion.
- [ ] Validar navegacion y accesos por perfil.

Entregables Dia 6:

- Matriz de permisos aplicada.
- Lista de rutas protegidas validadas.

### Dia 7 - QA de cierre

- [ ] Pruebas de humo por modulo.
- [ ] Correccion de bloqueantes.
- [ ] Acta de cierre de semana (listo/parcial/falta).

Entregables Dia 7:

- Reporte de cierre Semana 1.
- Plan de continuidad Semana 2.

## Riesgos y mitigacion

1. Cambios de alcance a mitad de semana.
   - Mitigacion: congelar alcance MVP en Dia 1.
2. Reglas distintas entre creacion manual e importacion.
   - Mitigacion: una sola capa de validacion reutilizable.
3. Datos historicos con inconsistencia.
   - Mitigacion: script de saneamiento y reporte de excepciones.

## Criterio de listo

Se considera lista la semana cuando:

1. Los 4 puntos tienen evidencia (documento, codigo y pruebas).
2. No hay bloqueantes abiertos en P1.
3. Existe backlog ordenado para la Semana 2.
