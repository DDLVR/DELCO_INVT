# Verificacion de Permisos por Rol (Sin Roles Nuevos)

Fecha: 2026-07-08
Alcance: roles existentes en usuarios.models

Roles oficiales del sistema:

1. ADMIN
2. ADMINISTRATIVO
3. TECNICO
4. GERENCIA
5. AUDITOR

Nota de criterio:

- No se crea ningun rol adicional.
- AUDITOR se usa como rol de validacion operativa.
- Perfil SOLO LECTURA del punto 11 se mapea al rol AUDITOR.
- Rol ANALISTA del requerimiento se mapea a ADMINISTRATIVO (sin crear rol nuevo).

## 0. Mapeo requerido (PDF) vs rol real del sistema

1. Administrador -> ADMIN
2. Analista -> ADMINISTRATIVO
3. Rol 3 del requerimiento (validacion operativa) -> AUDITOR
4. Tecnico -> TECNICO
5. Solo lectura -> AUDITOR

## 1. Verificacion tecnica ejecutada

Pruebas automatizadas:

- web.tests.MatrizRolesPunto11Tests
- ordenes_trabajo.tests.OrdenesRolesTests
- web.tests.PermisosSoloLecturaAuditorTests

Resultado:

- Found 11 test(s)
- Ran 11 tests
- OK

## 2. Matriz de trabajo por rol (estado actual)

### ADMIN

1. Puede crear ordenes.
2. Puede ver todas las ordenes.
3. Puede ejecutar acciones de administracion sensibles.

### ADMINISTRATIVO

1. Puede crear ordenes.
2. Puede ver todas las ordenes.
3. Gestion operativa diaria.
4. Equivalente funcional al rol Analista para:
	- revisar OT
	- validar informacion de terreno
	- corregir datos
	- generar reportes
	- derivar casos
	- revisar alarmas

### TECNICO

1. No puede crear ordenes.
2. Ve solo ordenes donde es tecnico responsable.
3. Puede ejecutar cambios de estado permitidos para su flujo tecnico.

### GERENCIA

1. No puede crear ordenes.
2. Puede ver listado global para monitoreo.
3. Rol de control, no de ejecucion operativa.

### AUDITOR (validacion operativa + solo lectura)

1. No crea ordenes.
2. Puede ver listado global para control.
3. Puede validar estados VALIDADA y OBSERVADA en flujo de orden.
4. Actua tambien como perfil solo lectura para vistas de control y reportes autorizados.

Opciones de SOLO LECTURA (AUDITOR):

1. Ver dashboard de auditor.
2. Ver listado y detalle de ordenes (sin creacion ni eliminacion).
3. Ver reportes MoreApp (listado/detalle) sin sincronizar ni eliminar.
4. Revisar trazabilidad de movimientos para control operativo.

## 3. Archivos verificados/ajustados

1. ordenes_trabajo/models.py
2. ordenes_trabajo/tests.py
3. web/decorators.py
4. ordenes_trabajo/views.py
5. MANUAL_CLIENTE_OPERACION.md
6. REFERENCIA_RAPIDA.md
7. PLAN_SEMANA_1_PUNTOS_1_A_4.md

## 4. Conclusiones

1. El sistema queda alineado a los roles reales definidos en usuarios.
2. Se elimina dependencia funcional de un rol adicional inexistente.
3. El rol AUDITOR cubre validacion operativa y solo lectura.
4. El rol ANALISTA queda cubierto por ADMINISTRATIVO sin introducir roles nuevos.
