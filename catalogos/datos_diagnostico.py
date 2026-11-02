# coding: utf-8
"""Causas y acciones alineadas al flujo actual: Tareas MoreApp, no correo ni OT."""

CATALOGO_DIAGNOSTICO = [
    (
        "INTRANET",
        "El aviso no llega por correo",
        "Es correcto: Delco no envía mail. El técnico ve la tarea en la app MoreApp. Si no aparece, revisar enlace de correo, formulario publicado y acceso en MoreApp.",
    ),
    (
        "INTRANET",
        "El menú se queda y solo cambia el centro",
        "La barra y el menú no se recargan. Espera el círculo de carga. Si un popup queda abierto, ciérralo o recarga con F5. Salir sí recarga todo.",
    ),
    (
        "INTRANET",
        "Tareas MoreApp tarda en abrir",
        "La primera carga consulta MoreApp y puede demorar. El menú sigue usable. No abras varias pestañas del mismo listado: el servidor atiende una petición a la vez.",
    ),
    (
        "INTRANET",
        "No encuentro un formulario en Formularios asignados",
        "Esa pantalla solo muestra lo asignado al usuario. El listado completo está en Catálogo MoreApp (admin). Formularios ocultos no aparecen hasta marcar “mostrar ocultos”.",
    ),
    (
        "TAREAS",
        "El formulario no aparece para crear la tarea",
        "Solo se pueden asignar formularios publicados en MoreApp. Revisar Catálogo MoreApp y publicar la versión en la app.",
    ),
    (
        "TAREAS",
        "El técnico no aparece al elegir el formulario",
        "Solo se listan correos y grupos con acceso a ese formulario en MoreApp. Dar permiso en MoreApp o elegir otro destinatario.",
    ),
    (
        "TAREAS",
        "Error de envío o versión no publicada",
        "Abrir Registro de errores → Tareas MoreApp. Publicar el formulario en MoreApp y reintentar desde el detalle de la tarea.",
    ),
    (
        "TAREAS",
        "Varias tareas del mismo formulario se confunden",
        "En Listado usa cantidad N y anota el nº de cliente u otra nota por tarea. El mensaje corto vale para todas; la nota distingue cada aviso.",
    ),
    (
        "TAREAS",
        "Carga masiva Excel o desde clientes falló en parte",
        "Las filas enviadas quedan en Tareas MoreApp. Las que fallaron aparecen en Registro de errores con el mensaje de MoreApp.",
    ),
    (
        "TAREAS",
        "El técnico no recibió la tarea",
        "Confirmar correo MoreApp enlazado (Usuarios / cuentas MoreApp), que el form esté publicado y que tenga acceso. El estado se actualiza en Tareas MoreApp (Revisar).",
    ),
    ("SISTEMA", "IP errónea del módem", "Corregir la IP en la ficha del cliente y en inventario. Verificar que el módem responda."),
    (
        "SISTEMA",
        "Ficha no actualizada",
        "Actualizar medidor, SIM o módem en Inventario y en la ficha del cliente. Esa es la fuente de la intranet.",
    ),
    (
        "SISTEMA",
        "Caída masiva o error interno",
        "Anotar el código de error si aparece. Levantar ticket en Soporte. Revisar Registro de errores.",
    ),
    ("SIMCARD", "Sin plan de datos", "Cambio de SIMCard"),
    ("SIMCARD", "SIM sucia o mal instalada", "Limpieza y reinstalación"),
    ("SIMCARD", "SIM dañada", "Cambio de SIMCard"),
    ("SIMCARD", "Sin cobertura", "Traslado de equipo, cambio de antena o uso de doble SIM"),
    ("MODEM", "Obsoleto o con falla sin repuesto", "Cambio de módem"),
    ("MODEM", "Desprogramado", "Cambio de módem y reprogramación del equipo retirado"),
    ("MODEM", "Falla franca", "Cambio de módem y baja del equipo retirado"),
    ("MODEM", "No existe módem en terreno", "Instalación de módem y habilitación de telemedida"),
    ("MEDIDOR", "Hurto o intervención", "Informar a Pérdidas"),
    ("MEDIDOR", "No compatible con telemedida", "Cambio de medidor"),
    ("MEDIDOR", "Sin medidor, conectado directo", "Instalar medidor, habilitar telemedida e informar a Pérdidas"),
    ("MEDIDOR", "No comunica, pero registra", "Cambio de medidor"),
    ("MEDIDOR", "Falla franca, no comunica ni registra", "Cambio de medidor e informar a Pérdidas"),
    ("MEDIDOR", "Sin medidor", "Reponer medidor si corresponde"),
    ("MEDIDOR", "Medidor en terreno distinto al sistema", "Actualizar Inventario y la ficha del cliente con el medidor real en terreno"),
    ("ESTADO_CLIENTE", "Sin suministro", "Monitorear estado en la ficha del cliente"),
    ("ESTADO_CLIENTE", "Retirado", "Retirar o inactivar el cliente con apoyo de Morosidad"),
    ("ESTADO_VISITA", "Cerrado", "Reprogramar la tarea en Tareas MoreApp para lograr acceso y diagnóstico"),
    ("ESTADO_VISITA", "Deshabitado", "Realizar seguimiento con lectura pedestre y dejar nota en la tarea"),
    ("ESTADO_VISITA", "No permite acceso", "Reportar a Pérdidas o al área correspondiente y registrar la nota en la tarea"),
]

# Filas viejas (StarBeat) que ya no deben mostrarse.
ORIGENES_DESACTIVAR = (
    ("SISTEMA", "Base de datos no actualizada"),
    ("SISTEMA", "Caída masiva"),
)


def sync_catalogo_diagnostico(model=None):
    if model is None:
        from catalogos.models import CatalogoDiagnostico as model

    vistos = set()
    creados = 0
    actualizados = 0
    for orden, (categoria, origen, solucion) in enumerate(CATALOGO_DIAGNOSTICO, start=1):
        obj, created = model.objects.update_or_create(
            categoria=categoria,
            origen=origen,
            defaults={"solucion": solucion, "orden": orden, "activo": True},
        )
        vistos.add((categoria, origen))
        if created:
            creados += 1
        else:
            actualizados += 1
    desactivados = 0
    for categoria, origen in ORIGENES_DESACTIVAR:
        n = model.objects.filter(categoria=categoria, origen=origen, activo=True).update(activo=False)
        desactivados += n
    return {"creados": creados, "actualizados": actualizados, "desactivados": desactivados, "total": len(vistos)}
