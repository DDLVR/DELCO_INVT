# ESTRUCTURA BASE DE DATOS - VERSION OPERATIVA

Documento resumido de entidades y relaciones vigentes en DELCO_INVT.

## 1. Dominio usuarios

### usuarios_usuario

Campos clave:

- id
- rut
- email
- nombre_interno
- rol
- is_active

Uso:

- autenticacion
- autorizacion por rol
- responsable de movimientos y acciones operativas

## 2. Dominio ordenes

### ordenes_trabajo_ordentrabajo

Campos clave:

- id
- titulo
- estado
- tecnico_responsable_id
- cliente_id
- fecha_creacion

Relaciona ejecucion de terreno con cliente y equipos.

## 3. Dominio inventario

### inventario_estadoinventario

Estados estandar:

- En bodega
- Instalado
- Retirado
- En reparacion
- Dado de baja
- En peaje
- En custodia tecnico
- En revision

### inventario_medidor
### inventario_simcard
### inventario_modem

Campos operativos relevantes (segun tipo):

- serie / identificadores
- estado_inventario_id
- cliente_id
- medidor_id (asociaciones)
- ubicacion_actual_id
- entregado_a o en_custodia_de

## 4. Trazabilidad de movimientos

### inventario_movimientoinventario

Campos clave:

- id
- fecha_hora
- tipo
- origen_sistema
- origen_id
- destino_id
- responsable_id
- observacion
- orden_trabajo_id

Tipos principales:

- IMPORTACION
- ENTREGA
- RECEPCION
- DEVOLUCION
- INSTALACION
- RETIRO
- ELIMINACION
- AJUSTE
- CORRECCION
- MOREAPP

Origen del movimiento:

- MOREAPP
- MANUAL
- IMPORTACION
- SISTEMA

### inventario_movimientoitem

Detalle por equipo movido:

- tipo_equipo (MEDIDOR/SIM/MODEM)
- medidor_id / simcard_id / modem_id
- cantidad

## 5. Integracion MoreApp

### ordenes_trabajo_integracionmoreapp

Campos clave:

- moreapp_submission_id (unico)
- estado_sincronizacion
- estado_revision
- alerta_doble_trabajo
- descripcion_alerta
- datos_recibidos (JSON)
- datos_procesados (JSON)
- fecha_recepcion
- fecha_procesamiento

Estado de revision operativo:

- PENDIENTE
- CON_ADVERTENCIA
- REVISADO
- DESCARTADO

## 6. Relaciones de negocio

- Usuario 1:N MovimientoInventario (responsable)
- Ubicacion 1:N MovimientoInventario (origen/destino)
- MovimientoInventario 1:N MovimientoItem
- IntegracionMoreApp puede actualizar cliente/equipos y generar movimientos
- Cliente 1:N equipos (medidor/sim/modem segun asignacion)

## 7. Migraciones relevantes recientes

- inventario 0015:
  - campo origen_sistema en MovimientoInventario
  - indice por origen_sistema
  - extension de tipos de movimiento

- ordenes_trabajo 0006:
  - campo estado_revision en IntegracionMoreApp
  - indice por estado_revision

## 8. Integridad y control

- moreapp_submission_id evita duplicados funcionales.
- indices en fecha/tipo/revision mejoran consulta operativa.
- responsable en movimientos conserva trazabilidad auditada.
- estado_revision separa resultado tecnico de cierre operativo.
