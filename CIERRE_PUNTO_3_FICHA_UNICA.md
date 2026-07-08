# Cierre Punto 3 PDF - Ficha Unica por Cliente

Fecha de cierre: 2026-07-08
Estado: LISTO

## 1. Alcance del punto

Punto PDF 3: Ficha unica por cliente con modelo de datos y defaults operativos definidos.

## 2. Resultado implementado

1. Ficha cliente con clave operativa numero_cliente + meter_serial_n_1.
2. Control de duplicado exacto activo (bloqueado).
3. Caso operativo numero repetido con serie distinta (permitido y trazable).
4. Defaults activos para campos criticos:
   - proyecto => SIN PROYECTO
   - ultimo_perfil_carga => SIN PERFIL

## 3. Evidencia en codigo

1. web/views.py
   - cliente_crear_view
   - cliente_editar_view
2. importaciones/utils.py
   - importar_clientes_excel
3. clientes/tests.py
4. importaciones/tests.py

## 4. Evidencia de pruebas automatizadas

Suites ejecutadas:

1. clientes.tests.ClienteFlujoViewTests
2. clientes.tests.ClienteImportarViewTests
3. importaciones.tests.ImportacionClientesModoTests

Resultado consolidado esperado:

- tests encontrados: 8
- ejecucion: OK

## 5. Criterios de aceptacion del punto 3

1. Campos obligatorios/opcionales definidos: OK.
2. Defaults definidos: OK.
3. Reglas de unicidad documentadas y probadas: OK.

## 6. Comando de verificacion

python manage.py test clientes.tests.ClienteFlujoViewTests clientes.tests.ClienteImportarViewTests importaciones.tests.ImportacionClientesModoTests -v 1

## 7. Estado final

Punto 3 queda marcado como LISTO en la matriz de trazabilidad.
