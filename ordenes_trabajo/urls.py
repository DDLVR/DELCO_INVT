# urls.py
from django.urls import path
from .views import (
    cambiar_estado_orden_view,
    orden_editar_tecnico_view,
    ordenes_list_view,
    orden_crear_view,
    orden_detalle_view,
    orden_subir_adjunto_view,
    orden_registrar_equipos_view,
    moreapp_webhook_view
)

urlpatterns = [
    # Lista y gestión de órdenes
    path('', ordenes_list_view, name='ordenes_list'),
    path('crear/', orden_crear_view, name='orden_crear'),
    path('<int:pk>/', orden_detalle_view, name='orden_detalle'),
    path('<int:pk>/cambiar-estado/', cambiar_estado_orden_view, name='cambiar_estado_orden'),
    path('<int:pk>/editar/', orden_editar_tecnico_view, name='orden_editar_tecnico'),
    path('<int:pk>/subir-adjunto/', orden_subir_adjunto_view, name='orden_subir_adjunto'),
    path('<int:pk>/registrar-equipos/', orden_registrar_equipos_view, name='orden_registrar_equipos'),
    
    # Webhook MoreApp
    path('api/moreapp/webhook/', moreapp_webhook_view, name='moreapp_webhook'),
]
