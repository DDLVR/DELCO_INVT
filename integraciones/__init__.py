"""MoreApp. Abrir el archivo de la pantalla; lo compartido se importa.

Pantallas
    moreapp_tareas_views.py       tareas, lotes y exportación
    moreapp_catalogo_views.py     catálogo, fuentes y usuarios
    moreapp_formularios_views.py  formularios asignados
    moreapp_registros_views.py    registros recibidos y ZIP de Lectura
    moreapp_visualizacion_views.py  JSON de visualización y de datos

Llegada de un informe
    reader.py              lee registration.json
    moreapp_api_ingest.py  lo guarda
    moreapp_api.py         cliente HTTP, id seguro y respuesta JSON

Compartido, importar y no copiar
    moreapp_fechas.py         fechas
    moreapp_asignaciones.py   quién tiene un formulario
    moreapp_fuentes.py        Excel o CSV de una fuente
    moreapp_cuentas.py        destinatarios y cuentas
    moreapp_permisos.py       permisos por formulario
    moreapp_tareas_ciclo.py   ciclo de la tarea y su auditoría
    moreapp_tareas_lote.py    envío por lote
    web/services/listado.py   filtros, páginas, pastillas y resumen
"""
