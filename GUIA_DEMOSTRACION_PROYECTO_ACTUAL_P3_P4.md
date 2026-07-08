# Guia de Demostracion - Proyecto Actual (Puntos 3 y 4)

Objetivo: demostrar con evidencia real del proyecto DELCO_INVT que la ficha cliente y validaciones funcionan.

## 1. Preparacion

1. Ejecutar migraciones:
   - python manage.py migrate
2. Levantar servidor:
   - python manage.py runserver
3. Iniciar sesion con usuario ADMIN o ADMINISTRATIVO.

## 2. Demostracion funcional en la pagina

### Escenario A - Alta con defaults (Punto 3)

1. Ir a modulo Clientes -> Crear.
2. Completar campos obligatorios.
3. Dejar vacio Proyecto y Ultimo Perfil Carga.
4. Guardar.
5. Resultado esperado:
   - cliente creado
   - proyecto = SIN PROYECTO
   - ultimo_perfil_carga = SIN PERFIL

### Escenario B - Duplicado exacto bloqueado (Punto 3)

1. Repetir alta con mismo numero_cliente y misma serie de medidor.
2. Resultado esperado:
   - no se crea un segundo registro activo identico
   - mensaje de error de duplicado

### Escenario C - Numero repetido con serie distinta (Punto 3)

1. Crear con mismo numero_cliente pero otra serie de medidor valida.
2. Resultado esperado:
   - alta permitida
   - warning operativo de duplicidad por numero

### Escenario D - IP invalida bloqueada (Punto 4)

1. En alta, usar IP invalida (ejemplo: 999.10.10.1).
2. Resultado esperado:
   - bloqueo de alta
   - mensaje de validacion de IP

### Escenario E - Import incremental (Puntos 3, 4, 15)

1. Ir a Clientes -> Importar.
2. Cargar Excel con modo incremental.
3. Resultado esperado:
   - se crean/actualizan filas del archivo
   - clientes activos no presentes en archivo se conservan

### Escenario F - Import sync (Puntos 3, 4, 15)

1. Cargar Excel con modo sync.
2. Resultado esperado:
   - se crean/actualizan filas del archivo
   - clientes activos no presentes en archivo se desactivan

## 3. Evidencia automatizada para presentar

Ejecutar comando:

python manage.py test clientes.tests.ClienteFlujoViewTests clientes.tests.ClienteImportarViewTests importaciones.tests.ImportacionClientesModoTests -v 1

Resultado esperado:

- pruebas encontradas: 8
- estado final: OK

## 4. Evidencia documental a mostrar

1. MATRIZ_TRAZABILIDAD_PDF.md
2. DICCIONARIO_DATOS_CLIENTE_PUNTO_3.md
3. CIERRE_PUNTO_3_FICHA_UNICA.md
4. CIERRE_PUNTO_4_VALIDACIONES.md

## 5. Cierre de demostracion

Si los escenarios A-F y los tests pasan, se considera demostrada la conformidad de P3 y P4 sobre el proyecto actual.
