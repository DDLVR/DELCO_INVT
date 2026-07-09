# DELCO_INVT

Plataforma web de gestion de inventario operativo con integracion MoreApp para recepcion de formularios en terreno.

## 1. Objetivo para cliente

El sistema permite:

- Controlar inventario de medidores, SIM y modems.
- Trazar cada cambio con movimientos auditables.
- Registrar y revisar datos recibidos desde MoreApp.
- Detectar pendientes operativos y casos envejecidos.

## 2. Modulos principales

- Inventario: equipos, estados, custodia, edicion simple y masiva.
- Movimientos: kardex operativo con origen/destino/responsable.
- Ordenes de trabajo: gestion individual/masiva con validaciones operativas y alertas.
- Reportes MoreApp: sincronizacion, detalle tecnico, revision.
- Cola operativa: pendientes por revisar y acciones guiadas.

## 3. Cambios operativos ya implementados

- Integracion MoreApp con estado de revision formal:
	- PENDIENTE
	- CON_ADVERTENCIA
	- REVISADO
	- DESCARTADO
- Validacion previa de conflictos de instalacion en procesamiento MoreApp.
- Registro de movimientos con:
	- tipo MOREAPP
	- origen_sistema MOREAPP
- Actualizacion de ubicacion_actual del equipo al generar movimiento.
- Dashboard admin con indicadores de excepcion y envejecimiento (> 7 dias).
- Vista de cola de pendientes operativos con cambio de estado de revision.
- Comando de calidad de datos para deteccion/correccion operativa.

## 4. Rutas funcionales clave

- /dashboard/
- /inventario/
- /movimientos/
- /reportes/moreapp/
- /operacional/pendientes/
- /api/moreapp-webhook/

## 5. Comandos de operacion

### Inicializar estados estandar

```bash
python manage.py inicializar_estados
```

### Verificar calidad de datos (solo reporte)

```bash
python manage.py verificar_calidad --solo-reporte
```

### Verificar calidad de datos (corrige donde aplica)

```bash
python manage.py verificar_calidad
```

### Verificacion general Django

```bash
python manage.py check
```

## 6. Flujo operativo recomendado

1. Sincronizar reportes MoreApp en /reportes/moreapp/.
2. Revisar cola operativa en /operacional/pendientes/.
3. Marcar registros como REVISADO o DESCARTADO segun analisis.
4. Revisar alertas envejecidas (> 7 dias) en dashboard.
5. Ejecutar verificar_calidad al cierre diario o semanal.

## 7. Seguridad y trazabilidad

- Toda accion queda con usuario responsable en movimientos.
- Los cambios MoreApp quedan trazados por submission_id.
- El sistema usa estados de revision para control de cierre operativo.
- Roles controlan acceso a vistas sensibles.

## 8. Estado actual

La base funcional principal esta activa y validada con chequeo Django sin errores.
