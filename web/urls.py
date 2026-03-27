from django.urls import path
from .views import (
    login_view, logout_view, dashboard_view,
    ordenes_list_view, orden_detalle_view, orden_crear_view,
    inventario_list_view, inventario_exportar_view, inventario_importar_view, inventario_obtener_datos_view, inventario_modificar_view, inventario_eliminar_view, profile_view, update_profile_view,
    usuarios_list_view, usuario_crear_view, usuario_editar_view, usuario_reset_password_view, usuario_eliminar_view,
    clientes_list_view, cliente_crear_view, cliente_editar_view, cliente_eliminar_view,
    importacion_errores_view, importacion_corregir_fila_view,
    movimientos_list_view, movimientos_detalle_view, movimientos_historial_equipo_view, movimientos_importar_moreapp_webhook,
    reportes_moreapp_list, reportes_moreapp_detalle, reportes_moreapp_sincronizar,
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

    # Órdenes de Trabajo
    path('ordenes/', ordenes_list_view, name='ordenes_list'),
    path('ordenes/<int:pk>/', orden_detalle_view, name='orden_detalle'),
    path('ordenes/crear/', orden_crear_view, name='orden_crear'),

    # Inventario
    path('inventario/', inventario_list_view, name='inventario_list'),
    path('inventario/exportar/', inventario_exportar_view, name='inventario_exportar'),
    path('inventario/importar/', inventario_importar_view, name='inventario_importar'),
    path('inventario/<int:pk>/obtener-datos/', inventario_obtener_datos_view, name='inventario_obtener_datos'),
    path('inventario/<int:pk>/modificar/', inventario_modificar_view, name='inventario_modificar'),

    # Eliminar registro de inventario
    path('inventario/<int:pk>/eliminar/', inventario_eliminar_view, name='inventario_eliminar'),

    # Importaciones y errores
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

    # Movimientos de Inventario
    path('movimientos/', movimientos_list_view, name='movimientos_list'),
    path('movimientos/<int:movimiento_id>/', movimientos_detalle_view, name='movimientos_detalle'),
    path('movimientos/historial/', movimientos_historial_equipo_view, name='movimientos_historial_equipo'),
    
    # Reportes — Integraciones MoreApp (lectura directa de carpetas)
    path('reportes/moreapp/', reportes_moreapp_list, name='reportes_moreapp_list'),
    path('reportes/moreapp/<int:pk>/', reportes_moreapp_detalle, name='reportes_moreapp_detalle'),
    path('reportes/moreapp/sincronizar/', reportes_moreapp_sincronizar, name='reportes_moreapp_sincronizar'),

    # API Webhook MoreApp (tiempo real - sin autenticación Django)
    path('api/moreapp-webhook/', movimientos_importar_moreapp_webhook, name='movimientos_webhook_moreapp'),
]