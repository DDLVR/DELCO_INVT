# MANUAL CLIENTE - OPERACION DIARIA DELCO_INVT

Documento orientado a usuarios operativos (ADMIN, ADMINISTRATIVO, AUDITOR).

## 1. Objetivo

Asegurar que los registros de terreno (MoreApp) se integren, revisen y cierren con trazabilidad completa.

## 2. Que hacer cada dia

1. Entrar a /reportes/moreapp/.
2. Ejecutar sincronizacion.
3. Revisar /operacional/pendientes/.
4. Gestionar cada caso segun estado de revision.
5. Revisar dashboard para alertas envejecidas.

## 3. Como decidir estado de revision

### REVISADO

Usar cuando:

- El cruce de cliente/equipo es correcto.
- El movimiento generado coincide con la operacion esperada.
- No existen pendientes de identificadores.

### CON_ADVERTENCIA

Usar cuando:

- Hay conflicto de instalacion.
- Faltan datos o hay inconsistencia parcial.
- Se necesita seguimiento antes de cierre final.

### DESCARTADO

Usar cuando:

- El formulario no corresponde al proceso.
- El registro es invalido para operacion.
- Es una prueba o dato no utilizable.

### PENDIENTE

Usar solo como estado transitorio de analisis.

## 4. SLA sugerido de operacion

- Pendientes nuevos: revisar en menos de 24 horas.
- Pendientes con advertencia: resolver en 48-72 horas.
- Pendientes > 7 dias: tratar como alerta critica.

## 5. Control semanal recomendado

Ejecutar:

```bash
python manage.py verificar_calidad --solo-reporte
```

Si se aprueba correccion automatica:

```bash
python manage.py verificar_calidad
```

## 6. Trazabilidad y auditoria

Cada movimiento debe quedar con:

- tipo
- origen_sistema
- responsable
- observacion
- relacion con submission MoreApp cuando aplica

## 7. Indicadores minimos para cliente

- Registros pendientes de revision.
- Registros con advertencia.
- Registros pendientes con antiguedad mayor a 7 dias.
- Volumen de movimientos origen_sistema=MOREAPP.

## 8. Escalamiento

Escalar a responsable tecnico cuando exista:

- Conflicto repetido de instalacion en mismo cliente.
- Aumento sostenido de registros CON_ADVERTENCIA.
- Errores de lectura o JSON recurrentes en MoreApp.

## 9. Buenas practicas

- No cerrar por lote sin revisar detalle.
- Registrar observaciones claras y cortas.
- Mantener estados de inventario inicializados y consistentes.
- Ejecutar control de calidad de forma periodica.
