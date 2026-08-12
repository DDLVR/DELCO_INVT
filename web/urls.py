from django.urls import path
from .views import (
    login_view, logout_view, dashboard_view,
    inventario_list_view, inventario_exportar_view, inventario_importar_view, inventario_obtener_datos_view, inventario_modificar_view, inventario_eliminar_view, inventario_crear_view, inventario_modificar_masivo_view, profile_view, update_profile_view,
    usuarios_list_view, usuario_crear_view, usuario_editar_view, usuario_reset_password_view, usuario_eliminar_view,
    clientes_list_view, clientes_exportar_view, clientes_importar_view, cliente_crear_view, cliente_editar_view, cliente_historial_view, cliente_eliminar_view,
    cliente_marcar_sci4_actualizado_view,
    clientes_eliminar_masivo_view, clientes_modificar_masivo_view,
    registro_errores_view, importacion_errores_view, importacion_corregir_fila_view,
    movimientos_list_view, movimientos_detalle_view, movimientos_historial_equipo_view, movimientos_importar_moreapp_webhook,
    reportes_moreapp_list, reportes_moreapp_detalle, reportes_moreapp_sincronizar, reportes_moreapp_eliminar,
    reportes_moreapp_eliminar_masivo,
    pendientes_operativos_view, moreapp_marcar_revision_view, moreapp_reprocesar_view,
    auditoria_list_view,
    api_buscar_medidores, api_buscar_clientes, api_buscar_tecnicos, api_obtener_medidor,
)
from reportes.views import reportes_hub_view, reportes_export_view
from catalogos.views import catalogo_diagnostico_list_view
from cargas.views import (
    cargas_hub_view,
    cargas_list_view,
    cargas_crear_view,
    cargas_detalle_view,
    cargas_generar_pendientes_view,
    cargas_importar_view,
    cargas_exportar_view,
    cargas_eliminar_view,
    cargas_eliminar_masivo_view,
    cargas_pdf_view,
)
from ordenes_trabajo.views import (
    ordenes_list_view as ordenes_trabajo_list,
    ordenes_terminadas_view,
    orden_crear_view,
    orden_detalle_view,
    cambiar_estado_orden_view,
    orden_editar_tecnico_view,
    orden_guardar_observaciones_view,
    orden_pdf_completado_view,
    orden_subir_adjunto_view,
    orden_registrar_equipos_view,
    ordenes_importar_view,
    ordenes_exportar_view,
    ordenes_asignar_masivo_view,
    ordenes_modificar_masivo_view,
    orden_subir_informe_view,
    orden_eliminar_view,
    orden_solicitar_validacion_comunicacion_view,
    orden_registrar_validacion_comunicacion_view,
    orden_crear_comprobante_cambio_view,
    comprobantes_cambio_list_view,
)

# Soporte es opcional en deploys parciales: si falta el paquete, el sitio no debe caer.
try:
    from soporte.views import (
        soporte_hub_view,
        soporte_list_view,
        soporte_crear_view,
        soporte_detalle_view,
        soporte_ticket_rapido_view,
    )
    SOPORTE_DISPONIBLE = True
except Exception:  # ImportError u otros fallos de carga del app
    SOPORTE_DISPONIBLE = False
    soporte_hub_view = None
    soporte_list_view = None
    soporte_crear_view = None
    soporte_detalle_view = None
    soporte_ticket_rapido_view = None

urlpatterns = [
    # Entrada del sistema: http://127.0.0.1:8000/ → directo a login
    path('', login_view, name='home'),

    # Autenticación
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('profile/', profile_view, name='profile'),
    path('profile/update/', update_profile_view, name='update_profile'),

    # Dashboard
    path('dashboard/', dashboard_view, name='dashboard'),

    # Inventario
    path('inventario/', inventario_list_view, name='inventario_list'),
    path('inventario/exportar/', inventario_exportar_view, name='inventario_exportar'),
    path('inventario/importar/', inventario_importar_view, name='inventario_importar'),
    path('inventario/crear/', inventario_crear_view, name='inventario_crear'),
    path('inventario/modificar-masivo/', inventario_modificar_masivo_view, name='inventario_modificar_masivo'),
    path('inventario/<int:pk>/obtener-datos/', inventario_obtener_datos_view, name='inventario_obtener_datos'),
    path('inventario/<int:pk>/modificar/', inventario_modificar_view, name='inventario_modificar'),

    # Eliminar registro de inventario
    path('inventario/<int:pk>/eliminar/', inventario_eliminar_view, name='inventario_eliminar'),

    # Importaciones y errores
    path('registro-errores/', registro_errores_view, name='registro_errores'),
    path('importaciones/<int:pk>/errores/', importacion_errores_view, name='importacion_errores'),
    path('importaciones/<int:importacion_id>/corregir/<int:error_id>/', importacion_corregir_fila_view, name='importacion_corregir_fila'),

    # Usuarios (solo ADMIN)
    path('usuarios/', usuarios_list_view, name='usuarios_list'),
    path('usuarios/crear/', usuario_crear_view, name='usuario_crear'),
    path('usuarios/<int:pk>/editar/', usuario_editar_view, name='usuario_editar'),
    path('usuarios/<int:pk>/eliminar/', usuario_eliminar_view, name='usuario_eliminar'),
    path('usuarios/<int:pk>/reset-password/', usuario_reset_password_view, name='usuario_reset_password'),

    # Clientes
    path('clientes/', clientes_list_view, name='clientes_list'),
    path('clientes/exportar/', clientes_exportar_view, name='clientes_exportar'),
    path('clientes/importar/', clientes_importar_view, name='clientes_importar'),
    path('clientes/crear/', cliente_crear_view, name='cliente_crear'),
    path('clientes/<int:pk>/historial/', cliente_historial_view, name='cliente_historial'),
    path('clientes/<int:pk>/editar/', cliente_editar_view, name='cliente_editar'),
    path('clientes/<int:pk>/sci4-actualizado/', cliente_marcar_sci4_actualizado_view, name='cliente_marcar_sci4_actualizado'),
    path('clientes/<int:pk>/eliminar/', cliente_eliminar_view, name='cliente_eliminar'),
    path('clientes/eliminar-masivo/', clientes_eliminar_masivo_view, name='clientes_eliminar_masivo'),
    path('clientes/modificar-masivo/', clientes_modificar_masivo_view, name='clientes_modificar_masivo'),

    # Órdenes de Trabajo
    path('ordenes/', ordenes_trabajo_list, name='ordenes_list'),
    path('ordenes/terminadas/', ordenes_terminadas_view, name='ordenes_terminadas'),
    path('ordenes/crear/', orden_crear_view, name='orden_crear'),
    path('ordenes/importar/', ordenes_importar_view, name='ordenes_importar'),
    path('ordenes/exportar/', ordenes_exportar_view, name='ordenes_exportar'),
    path('ordenes/asignar-masivo/', ordenes_asignar_masivo_view, name='ordenes_asignar_masivo'),
    path('ordenes/modificar-masivo/', ordenes_modificar_masivo_view, name='ordenes_modificar_masivo'),
    path('ordenes/<int:pk>/', orden_detalle_view, name='orden_detalle'),
    path('ordenes/<int:pk>/cambiar-estado/', cambiar_estado_orden_view, name='cambiar_estado_orden'),
    path('ordenes/<int:pk>/editar/', orden_editar_tecnico_view, name='orden_editar_tecnico'),
    path('ordenes/<int:pk>/observaciones/', orden_guardar_observaciones_view, name='orden_guardar_observaciones'),
    path('ordenes/<int:pk>/pdf/', orden_pdf_completado_view, name='orden_pdf_completado'),
    path('ordenes/<int:pk>/subir-adjunto/', orden_subir_adjunto_view, name='orden_subir_adjunto'),
    path('ordenes/<int:pk>/registrar-equipos/', orden_registrar_equipos_view, name='orden_registrar_equipos'),
    path('ordenes/<int:pk>/subir-informe/', orden_subir_informe_view, name='orden_subir_informe'),
    path(
        'ordenes/<int:pk>/comunicacion/solicitar/',
        orden_solicitar_validacion_comunicacion_view,
        name='orden_solicitar_validacion_comunicacion',
    ),
    path(
        'ordenes/<int:pk>/comunicacion/registrar/',
        orden_registrar_validacion_comunicacion_view,
        name='orden_registrar_validacion_comunicacion',
    ),
    path(
        'ordenes/<int:pk>/comprobante-cambio/',
        orden_crear_comprobante_cambio_view,
        name='orden_crear_comprobante_cambio',
    ),
    path(
        'ordenes/comprobantes-cambio/',
        comprobantes_cambio_list_view,
        name='comprobantes_cambio_list',
    ),
    path('ordenes/<int:pk>/eliminar/', orden_eliminar_view, name='orden_eliminar'),

    # Movimientos de Inventario
    path('movimientos/', movimientos_list_view, name='movimientos_list'),
    path('movimientos/<int:movimiento_id>/', movimientos_detalle_view, name='movimientos_detalle'),
    path('movimientos/historial/', movimientos_historial_equipo_view, name='movimientos_historial_equipo'),

    # Reportes — Integraciones MoreApp (lectura directa de carpetas)
    path('reportes/moreapp/', reportes_moreapp_list, name='reportes_moreapp_list'),
    path('reportes/moreapp/<int:pk>/', reportes_moreapp_detalle, name='reportes_moreapp_detalle'),
    path('reportes/moreapp/sincronizar/', reportes_moreapp_sincronizar, name='reportes_moreapp_sincronizar'),
    path('reportes/moreapp/<int:pk>/eliminar/', reportes_moreapp_eliminar, name='reportes_moreapp_eliminar'),
    path('reportes/moreapp/eliminar-masivo/', reportes_moreapp_eliminar_masivo, name='reportes_moreapp_eliminar_masivo'),

    # Vistas operativas (Puntos 2, 8, 9, 11)
    path('operacional/pendientes/', pendientes_operativos_view, name='pendientes_operativos'),
    path('cargas/', cargas_hub_view, name='cargas_hub'),
    path('cargas/listado/', cargas_list_view, name='cargas_list'),
    path('cargas/crear/', cargas_crear_view, name='cargas_crear'),
    path('cargas/generar-pendientes/', cargas_generar_pendientes_view, name='cargas_generar_pendientes'),
    path('cargas/importar/', cargas_importar_view, name='cargas_importar'),
    path('cargas/exportar/', cargas_exportar_view, name='cargas_exportar'),
    path('cargas/eliminar-masivo/', cargas_eliminar_masivo_view, name='cargas_eliminar_masivo'),
    path('cargas/<int:pk>/eliminar/', cargas_eliminar_view, name='cargas_eliminar'),
    path('cargas/<int:pk>/pdf/', cargas_pdf_view, name='cargas_pdf'),
    path('cargas/<int:pk>/', cargas_detalle_view, name='cargas_detalle'),
    path('reportes/', reportes_hub_view, name='reportes_hub'),
    path('reportes/exportar/<slug:slug>/', reportes_export_view, name='reportes_export'),
    path('auditoria/', auditoria_list_view, name='auditoria_list'),
    path('catalogos/diagnostico/', catalogo_diagnostico_list_view, name='catalogo_diagnostico_list'),
    path('operacional/moreapp/<int:pk>/marcar-revision/', moreapp_marcar_revision_view, name='moreapp_marcar_revision'),
    path('reportes/moreapp/<int:pk>/reprocesar/', moreapp_reprocesar_view, name='moreapp_reprocesar'),

    # API Webhook MoreApp (tiempo real - sin autenticación Django)
    path('api/moreapp-webhook/', movimientos_importar_moreapp_webhook, name='movimientos_webhook_moreapp'),

    # API - Búsqueda autocomplete inventario
    path('api/buscar-medidores/', api_buscar_medidores, name='api_buscar_medidores'),
    path('api/buscar-clientes/', api_buscar_clientes, name='api_buscar_clientes'),
    path('api/buscar-tecnicos/', api_buscar_tecnicos, name='api_buscar_tecnicos'),
    path('api/medidores/<int:medidor_id>/', api_obtener_medidor, name='api_obtener_medidor'),
]

if SOPORTE_DISPONIBLE:
    urlpatterns += [
        path('soporte/', soporte_hub_view, name='soporte_hub'),
        path('soporte/tickets/', soporte_list_view, name='soporte_list'),
        path('soporte/tickets/crear/', soporte_crear_view, name='soporte_crear'),
        path('soporte/tickets/rapido/', soporte_ticket_rapido_view, name='soporte_ticket_rapido'),
        path('soporte/tickets/<int:pk>/', soporte_detalle_view, name='soporte_detalle'),
    ]
