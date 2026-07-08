# Matriz Final de Permisos - Punto 11 PDF

Fecha: 2026-07-08
Estado: Cierre propuesto

Regla de mapeo (sin crear roles nuevos):

1. Administrador -> ADMIN
2. Analista -> ADMINISTRATIVO
3. Rol 3 del requerimiento (validacion operativa) -> AUDITOR
4. Tecnico -> TECNICO
5. Solo lectura -> AUDITOR

## 1. Matriz Requerido vs Implementado

| Rol requerido (PDF) | Rol real | Requerido | Implementado actual | Evidencia | Brecha |
|---|---|---|---|---|---|
| Administrador | ADMIN | Crear usuarios, asignar permisos, cargar bases, modificar catalogos, exportar todo, ver historial completo | Admin-only en rutas sensibles + control total de gestion | web/views.py (rutas @role_required(['ADMIN'])), web/decorators.py, web.tests.MatrizRolesPunto11Tests | Sin brecha critica |
| Analista | ADMINISTRATIVO | Revisar OT, validar terreno, corregir datos, generar reportes, derivar casos, revisar alarmas | Administrativo habilitado en gestion operativa de OT/reportes/importaciones | ordenes_trabajo/views.py, web/views.py, ordenes_trabajo.tests.OrdenesRolesTests | Sin brecha critica |
| Rol de validacion operativa (requerimiento) | AUDITOR | Asignar trabajos, controlar avance diario, revisar productividad, validar trabajos ejecutados, revisar reincidencias | Auditor habilitado para validacion operativa (VALIDADA/OBSERVADA) y monitoreo global | ordenes_trabajo/models.py, ordenes_trabajo/tests.py | Asignacion de trabajos sigue en ADMIN/ADMINISTRATIVO por diseno operativo |
| Tecnico | TECNICO | Ver asignados, registrar visita, completar formulario, adjuntar fotos, informar resultado, registrar cambios de equipo/IP | Tecnico ve sus OT, puede editar/ejecutar flujo tecnico y adjuntar evidencia en su OT | ordenes_trabajo/views.py, ordenes_trabajo/tests.py | Sin brecha critica |
| Solo lectura | AUDITOR | Visualizar info, descargar reportes autorizados, no modificar | Auditor en ROLES_REPORTES_LECTURA y fuera de ROLES_REPORTES_GESTION | web/views.py (ROLES_REPORTES_*), web.tests.PermisosSoloLecturaAuditorTests | Sin brecha critica |

## 2. Validaciones automatizadas usadas

1. web.tests.MatrizRolesPunto11Tests
2. web.tests.PermisosSoloLecturaAuditorTests
3. ordenes_trabajo.tests.OrdenesRolesTests

## 3. Criterio de aceptacion del punto 11

1. Rutas/acciones protegidas por rol: OK.
2. Usuario sin permiso no puede ejecutar accion: OK.
3. Perfil solo lectura asignado a AUDITOR: OK.
4. No se crean roles nuevos: OK.
