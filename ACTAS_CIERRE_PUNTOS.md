# Actas de Cierre - Puntos PDF

Fecha de consolidacion: 2026-07-09

Comando de verificacion general (todos los tests):

python manage.py test web.tests clientes.tests importaciones.tests ordenes_trabajo.tests -v 1

---

## Punto 3 - Ficha Unica por Cliente

Fecha: 2026-07-08 | Estado: LISTO

Clave operativa: numero_cliente + meter_serial_n_1.
Defaults activos: proyecto => SIN PROYECTO, ultimo_perfil_carga => SIN PERFIL.
Duplicado exacto bloqueado. Numero repetido con serie distinta: permitido.

Archivos: web/views.py (cliente_crear_view, cliente_editar_view), importaciones/utils.py, clientes/tests.py, importaciones/tests.py.

Suites: clientes.tests.ClienteFlujoViewTests, clientes.tests.ClienteImportarViewTests, importaciones.tests.ImportacionClientesModoTests.

---

## Punto 4 - Validaciones Obligatorias

Fecha: 2026-07-08 | Estado: LISTO

Cobertura: formato IP, coherencia IP/Puerto, duplicidad serie medidor, asignacion modem.

Archivos: web/services/validators.py, web/views.py, importaciones/utils.py.

Suites: clientes.tests.ClienteFlujoViewTests, clientes.tests.ClienteImportarViewTests, importaciones.tests.ImportacionClientesModoTests.

---

## Punto 5 - Gestion Basica de OT

Fecha: 2026-07-09 | Estado: LISTO

Cobertura: creacion individual, importacion masiva, listado por rol, alerta duplicidad, estado inicial con asignacion.

Archivos: ordenes_trabajo/models.py, ordenes_trabajo/views.py, ordenes_trabajo/utils.py, ordenes_trabajo/tests.py.

Suite: ordenes_trabajo.tests.OrdenesBasicasWorkflowTests.

---

## Punto 7 - Alarmas y Alertas

Fecha: 2026-07-09 | Estado: LISTO

Cobertura: alerta de duplicidad de OT por cliente en ventana de 14 dias.

Archivos: ordenes_trabajo/utils.py (aplicar_alerta_duplicado, detectar_duplicado_orden), ordenes_trabajo/models.py (campo alerta_duplicado).

Suite: web.tests.AlarmasIntegracionPunto7y8Tests.

---

## Punto 8 - Integraciones

Fecha: 2026-07-09 | Estado: LISTO

Cobertura: importacion/exportacion Excel para clientes, inventario y OT. Webhook MoreApp disponible. Endpoint de reportes MoreApp accesible.

Archivos: importaciones/utils.py, ordenes_trabajo/utils.py, web/views.py (clientes_importar_view, inventario_importar_view, movimientos_importar_moreapp_webhook).

Suite: web.tests.AlarmasIntegracionPunto7y8Tests.

---

## Punto 9 - Informes y Reportes

Fecha: 2026-07-09 | Estado: LISTO

Hub `/reportes/` con 19 informes Excel del PDF y filtros por fecha/técnico/empresa.
Exports legacy siguen activos: clientes, inventario, órdenes, movimientos, MoreApp.

Archivos: `reportes/services.py`, `reportes/views.py`, `templates/reportes/hub.html`
Suites: `reportes.tests.ReportesPunto9Tests`, `web.tests.ReportesSetMinimoPunto9Tests`

---

## Punto 11 - Roles y Permisos

Fecha: 2026-07-08 | Estado: LISTO

Mapeo: Administrador->ADMIN, Analista->ADMINISTRATIVO, Supervisor->AUDITOR, Tecnico->TECNICO, Solo lectura->AUDITOR.

Archivos: web/decorators.py, web/views.py, ordenes_trabajo/views.py, ordenes_trabajo/models.py.

Suites: web.tests.MatrizRolesPunto11Tests, web.tests.PermisosSoloLecturaAuditorTests, ordenes_trabajo.tests.OrdenesRolesTests.

---

## Punto 12 - Trazabilidad y Auditoria

Fecha: 2026-07-09 | Estado: LISTO

AuditLog persistente + `audit_field_changes` integrado en clientes, inventario, OT y MoreApp.
Vista historial `/auditoria/` con filtros por entidad/acción/ID.

Archivos: web/models.py, web/services/audit.py, web/views.py, ordenes_trabajo/models.py, templates/auditoria/list.html
Suites: web.tests.AuditPersistencePunto12Tests, web.tests.AuditoriaExtendidaPunto12Tests

---

## Punto 13 - Dashboard Principal

Fecha: 2026-07-09 | Estado: LISTO

KPIs disponibles: total clientes, total medidores/SIM/modems, porcentajes instalados/bodega, movimientos recientes, pendientes MoreApp, alertas de envejecimiento.

Archivos: web/views.py (dashboard_view).

Suite: web.tests.DashboardKpisPunto13Tests.

---

## Punto 14 - Requerimientos Tecnicos

Fecha: 2026-07-09 | Estado: LISTO

Criterios: django check con 0 issues, migraciones aplicadas y consistentes, SECRET_KEY en .env, ALLOWED_HOSTS configurado, USE_TZ activo.

Verificacion: python manage.py check

---

## Punto 15 - Evitar Errores Operativos

Fecha: 2026-07-09 | Estado: LISTO

Cobertura: IP invalida bloquea creacion de cliente, importacion sin archivo devuelve error JSON, importacion con contenido invalido devuelve error JSON.

Archivos: web/views.py, web/services/validators.py, importaciones/utils.py.

Suite: web.tests.ErroresOperativosPunto15Tests.
