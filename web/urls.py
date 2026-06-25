from django.urls import path
from .views import (
    login_view, logout_view, dashboard_view,
    inventario_list_view, inventario_exportar_view, inventario_importar_view, inventario_obtener_datos_view, inventario_modificar_view, inventario_eliminar_view, inventario_crear_view, inventario_modificar_masivo_view, profile_view, update_profile_view,
    usuarios_list_view, usuario_crear_view, usuario_editar_view, usuario_reset_password_view, usuario_eliminar_view,
    clientes_list_view, cliente_crear_view, cliente_editar_view, cliente_eliminar_view,
    registro_errores_view, importacion_errores_view, importacion_corregir_fila_view,
    movimientos_list_view, movimientos_detalle_view, movimientos_historial_equipo_view, movimientos_importar_moreapp_webhook,
    reportes_moreapp_list, reportes_moreapp_detalle, reportes_moreapp_sincronizar, reportes_moreapp_eliminar,
    pendientes_operativos_view, moreapp_marcar_revision_view, moreapp_reprocesar_view,
    api_buscar_medidores, api_obtener_medidor,
)
from ordenes_trabajo.views import (
    ordenes_list_view as ordenes_trabajo_list, 
    orden_crear_view, 
    orden_detalle_view, 
    cambiar_estado_orden_view,
    orden_editar_tecnico_view,
    orden_subir_adjunto_view,
    orden_registrar_equipos_view,
    ordenes_importar_view,
    ordenes_exportar_view,
    ordenes_asignar_masivo_view,
    ordenes_modificar_masivo_view,
    orden_subir_informe_view,
    orden_eliminar_view,
)

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
    path('clientes/crear/', cliente_crear_view, name='cliente_crear'),
    path('clientes/<int:pk>/editar/', cliente_editar_view, name='cliente_editar'),
    path('clientes/<int:pk>/eliminar/', cliente_eliminar_view, name='cliente_eliminar'),

    # Órdenes de Trabajo
    path('ordenes/', ordenes_trabajo_list, name='ordenes_list'),
    path('ordenes/crear/', orden_crear_view, name='orden_crear'),
    path('ordenes/importar/', ordenes_importar_view, name='ordenes_importar'),
    path('ordenes/exportar/', ordenes_exportar_view, name='ordenes_exportar'),
    path('ordenes/asignar-masivo/', ordenes_asignar_masivo_view, name='ordenes_asignar_masivo'),
    path('ordenes/modificar-masivo/', ordenes_modificar_masivo_view, name='ordenes_modificar_masivo'),
    path('ordenes/<int:pk>/', orden_detalle_view, name='orden_detalle'),
    path('ordenes/<int:pk>/cambiar-estado/', cambiar_estado_orden_view, name='cambiar_estado_orden'),
    path('ordenes/<int:pk>/editar/', orden_editar_tecnico_view, name='orden_editar_tecnico'),
    path('ordenes/<int:pk>/subir-adjunto/', orden_subir_adjunto_view, name='orden_subir_adjunto'),
    path('ordenes/<int:pk>/registrar-equipos/', orden_registrar_equipos_view, name='orden_registrar_equipos'),
    path('ordenes/<int:pk>/subir-informe/', orden_subir_informe_view, name='orden_subir_informe'),
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

    # Vistas operativas (Puntos 2, 8, 9, 11)
    path('operacional/pendientes/', pendientes_operativos_view, name='pendientes_operativos'),
    path('operacional/moreapp/<int:pk>/marcar-revision/', moreapp_marcar_revision_view, name='moreapp_marcar_revision'),
    path('reportes/moreapp/<int:pk>/reprocesar/', moreapp_reprocesar_view, name='moreapp_reprocesar'),

    # API Webhook MoreApp (tiempo real - sin autenticación Django)
    path('api/moreapp-webhook/', movimientos_importar_moreapp_webhook, name='movimientos_webhook_moreapp'),
    
    # API - Búsqueda de Medidores (Autocomplete)
    path('api/buscar-medidores/', api_buscar_medidores, name='api_buscar_medidores'),
    path('api/medidores/<int:medidor_id>/', api_obtener_medidor, name='api_obtener_medidor'),
]