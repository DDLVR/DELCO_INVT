from django.urls import path
from .views import (
    login_view, logout_view, dashboard_view,
    ordenes_list_view, orden_detalle_view, orden_crear_view,
    inventario_list_view, inventario_exportar_view, inventario_importar_view, inventario_obtener_datos_view, inventario_modificar_view, profile_view, update_profile_view,
    usuarios_list_view, usuario_crear_view, usuario_editar_view, usuario_reset_password_view, usuario_eliminar_view,
    importacion_errores_view, importacion_corregir_fila_view,
    movimientos_list_view, movimientos_detalle_view, movimientos_historial_equipo_view, movimientos_importar_moreapp_webhook
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

    # Importaciones y errores
    path('importaciones/<int:pk>/errores/', importacion_errores_view, name='importacion_errores'),
    path('importaciones/<int:importacion_id>/corregir/<int:error_id>/', importacion_corregir_fila_view, name='importacion_corregir_fila'),

    # Usuarios (solo ADMIN)
    path('usuarios/', usuarios_list_view, name='usuarios_list'),
    path('usuarios/crear/', usuario_crear_view, name='usuario_crear'),
    path('usuarios/<int:pk>/editar/', usuario_editar_view, name='usuario_editar'),
    path('usuarios/<int:pk>/eliminar/', usuario_eliminar_view, name='usuario_eliminar'),
    path('usuarios/<int:pk>/reset-password/', usuario_reset_password_view, name='usuario_reset_password'),

    # Movimientos de Inventario
    path('movimientos/', movimientos_list_view, name='movimientos_list'),
    path('movimientos/<int:movimiento_id>/', movimientos_detalle_view, name='movimientos_detalle'),
    path('movimientos/historial/', movimientos_historial_equipo_view, name='movimientos_historial_equipo'),
    
    # API Webhook MoreApp (tiempo real - sin autenticación Django)
    path('api/moreapp-webhook/', movimientos_importar_moreapp_webhook, name='movimientos_webhook_moreapp'),
]