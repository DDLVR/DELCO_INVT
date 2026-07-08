# Diccionario de Datos Cliente - Punto 3 PDF

Fecha: 2026-07-08
Estado: LISTO

## 1. Objetivo

Definir formalmente la ficha unica de cliente para el proyecto DELCO_INVT.

## 2. Clave operativa de ficha unica

Para operacion y carga de datos se usa la clave operativa:

- numero_cliente + meter_serial_n_1

Regla principal:

1. Duplicado exacto (mismo numero_cliente y misma serie) en cliente activo: bloqueado.
2. Mismo numero_cliente con serie distinta: permitido (caso operativo controlado).
3. Serie medidor repetida en otro cliente activo: controlada por validaciones de negocio.

## 3. Campos obligatorios en alta manual

En flujo de creacion de cliente se consideran obligatorios:

1. numero_cliente
2. direccion
3. comuna
4. tipo_suministro
5. sector
6. city
7. customer_name
8. installation_address
9. meter_manufacturer_id
10. meter_serial_n_1

## 4. Campos opcionales relevantes

1. proyecto
2. ultimo_perfil_carga
3. ultimo_acceso
4. ultimo_reset
5. ultimo_registro_facturacion
6. note
7. ip
8. puerto
9. modem
10. fecha_registro

## 5. Defaults operativos

1. proyecto vacio => SIN PROYECTO
2. ultimo_perfil_carga vacio => SIN PERFIL

Aplicacion:

- Alta manual de cliente.
- Importacion de clientes con actualizacion incremental/sync.

## 6. Reglas de integridad operativa

1. No existe cliente activo duplicado por clave exacta (numero + serie).
2. En importacion incremental, no se desactivan clientes no presentes en archivo.
3. En importacion sync, se desactivan clientes activos no presentes en archivo importado.
4. En edicion, se conserva numero_cliente existente si llega vacio.

## 7. Evidencia tecnica

1. web/views.py (cliente_crear_view, cliente_editar_view)
2. importaciones/utils.py (importar_clientes_excel)
3. clientes/tests.py
4. importaciones/tests.py

## 8. Pruebas de cierre asociadas

1. clientes.tests.ClienteFlujoViewTests
2. clientes.tests.ClienteImportarViewTests
3. importaciones.tests.ImportacionClientesModoTests
