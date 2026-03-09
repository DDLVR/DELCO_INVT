from django.urls import path
from .views import webhook_moreapp

urlpatterns = [
    # Webhook para MoreApp (recibe archivos FPTs)
    path('moreapp/', webhook_moreapp, name='webhook_moreapp'),
]
