# Cierre Punto 9 PDF - Informes y Reportes

Fecha: 2026-07-09
Estado: LISTO

## Set minimo obligatorio implementado

1. Exportar clientes activos a Excel - /clientes/exportar/
2. Exportar inventario medidores a Excel - /inventario/exportar/?tipo=medidor
3. Exportar inventario SIM a Excel - /inventario/exportar/?tipo=sim
4. Exportar inventario modems a Excel - /inventario/exportar/?tipo=modem
5. Exportar ordenes de trabajo a Excel - /ordenes/exportar/
6. Listado de movimientos de inventario - /movimientos/
7. Reportes MoreApp con filtros - /reportes/moreapp/

## Acceso por rol

- Exportaciones de inventario: ADMIN, ADMINISTRATIVO, TECNICO (tecnico ve solo sus equipos)
- Exportacion de clientes: todos los roles autenticados
- Exportacion de ordenes: ADMIN, ADMINISTRATIVO, GERENCIA, AUDITOR
- Movimientos e historial: ADMIN, ADMINISTRATIVO

## Pruebas ejecutadas

Suite: web.tests.ReportesSetMinimoPunto9Tests

- Ran 5 tests
- OK

## Comando de verificacion

python manage.py test web.tests.ReportesSetMinimoPunto9Tests -v 1
