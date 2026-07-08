# Esqueleto Tecnico del Proyecto

Este documento define el punto de partida para construir sin desviarse del PDF.

## 1. Capas base

1. Vistas:
   - Reciben request, validan permisos, delegan logica.
2. Servicios:
   - Reglas de negocio y validaciones reutilizables.
3. Modelos:
   - Persistencia de datos.
4. Auditoria:
   - Registro de cambios y trazabilidad.

## 2. Archivos base creados

1. `web/services/validators.py`
   - Validacion IP, puerto, medidor y modem.
2. `web/services/audit.py`
   - Esqueleto de eventos de auditoria.
3. `ordenes_trabajo/services.py`
   - Validaciones base de OT y reincidencia.

## 3. Orden de implementacion recomendado

### Semana 1 - Puntos 1 a 4

1. Integrar `validators.py` en:
   - crear cliente
   - editar cliente
   - importar clientes
2. Definir politica final de bloqueo vs advertencia.
3. Integrar `audit.py` en cambios criticos de cliente.
4. Cerrar matriz de permisos por rol.

### Semana 2 en adelante

1. Completar flujo OT en `ordenes_trabajo/services.py`.
2. Implementar alertas y dashboard requeridos.
3. Completar auditoria por campo (old/new value).

## 4. Regla de control

No se agregan features nuevas sin referencia a la matriz:

- `MATRIZ_TRAZABILIDAD_PDF.md`
