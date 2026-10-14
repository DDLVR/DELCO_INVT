from django.urls import path

from .views import webhook_moreapp
from .moreapp_catalogo_views import (
    catalogo_datasource_detail_view,
    catalogo_datasources_view,
    catalogo_form_detail_view,
    catalogo_forms_view,
)
from .moreapp_datos_views import (
    v1_datos_export_fields,
    v1_datos_file_download,
    v1_datos_submission_detail,
    v1_datos_submissions_list,
    v1_datos_user_detail,
    v1_datos_users_list,
)
from .moreapp_registros_views import (
    registro_archivo_view,
    registro_detail_view,
    registros_form_view,
    ultimo_registro_view,
)
from .moreapp_visualizacion_views import (
    v1_visualizacion_datasource_detail,
    v1_visualizacion_datasources_list,
    v1_visualizacion_form_detail,
    v1_visualizacion_form_version_detail,
    v1_visualizacion_form_versions,
    v1_visualizacion_forms_list,
)

urlpatterns = [
    # Webhook para MoreApp (recibe archivos FPTs)
    path('moreapp/', webhook_moreapp, name='webhook_moreapp'),
    # Pantallas de observación (Fase 1) — no reemplazan reportes actuales
    path(
        'moreapp/api/catalogo/',
        catalogo_forms_view,
        name='moreapp_api_catalogo',
    ),
    path(
        'moreapp/api/catalogo/forms/<str:form_id>/',
        catalogo_form_detail_view,
        name='moreapp_api_formulario',
    ),
    path(
        'moreapp/api/catalogo/datasources/',
        catalogo_datasources_view,
        name='moreapp_api_datasources',
    ),
    path(
        'moreapp/api/catalogo/datasources/<str:datasource_id>/',
        catalogo_datasource_detail_view,
        name='moreapp_api_datasource',
    ),
    path(
        'moreapp/api/catalogo/forms/<str:form_id>/ultimo-registro/',
        ultimo_registro_view,
        name='moreapp_api_form_ultimo_registro',
    ),
    path(
        'moreapp/api/catalogo/forms/<str:form_id>/registros/',
        registros_form_view,
        name='moreapp_api_form_registros',
    ),
    path(
        'moreapp/api/catalogo/forms/<str:form_id>/registros/<str:submission_id>/',
        registro_detail_view,
        name='moreapp_api_registro',
    ),
    path(
        'moreapp/api/archivos/<str:file_id>/',
        registro_archivo_view,
        name='moreapp_api_registro_archivo',
    ),
    # API interna MoreApp v1.0 - Fase 1 (Visualización)
    path(
        'api/moreapp/v1/visualizacion/forms/',
        v1_visualizacion_forms_list,
        name='moreapp_v1_visualizacion_forms_list',
    ),
    path(
        'api/moreapp/v1/visualizacion/forms/<str:form_id>/',
        v1_visualizacion_form_detail,
        name='moreapp_v1_visualizacion_form_detail',
    ),
    path(
        'api/moreapp/v1/visualizacion/forms/<str:form_id>/versions/',
        v1_visualizacion_form_versions,
        name='moreapp_v1_visualizacion_form_versions',
    ),
    path(
        'api/moreapp/v1/visualizacion/forms/<str:form_id>/versions/<str:form_version_id>/',
        v1_visualizacion_form_version_detail,
        name='moreapp_v1_visualizacion_form_version_detail',
    ),
    path(
        'api/moreapp/v1/visualizacion/datasources/',
        v1_visualizacion_datasources_list,
        name='moreapp_v1_visualizacion_datasources_list',
    ),
    path(
        'api/moreapp/v1/visualizacion/datasources/<str:datasource_id>/',
        v1_visualizacion_datasource_detail,
        name='moreapp_v1_visualizacion_datasource_detail',
    ),
    # API interna MoreApp v1.0 - Fase 2 (Datos)
    path(
        'api/moreapp/v1/datos/forms/<str:form_id>/submissions/',
        v1_datos_submissions_list,
        name='moreapp_v1_datos_submissions_list',
    ),
    path(
        'api/moreapp/v1/datos/submissions/<str:submission_id>/',
        v1_datos_submission_detail,
        name='moreapp_v1_datos_submission_detail',
    ),
    path(
        'api/moreapp/v1/datos/files/<str:file_id>/download/',
        v1_datos_file_download,
        name='moreapp_v1_datos_file_download',
    ),
    path(
        'api/moreapp/v1/datos/users/',
        v1_datos_users_list,
        name='moreapp_v1_datos_users_list',
    ),
    path(
        'api/moreapp/v1/datos/users/<str:user_id>/',
        v1_datos_user_detail,
        name='moreapp_v1_datos_user_detail',
    ),
    path(
        'api/moreapp/v1/datos/forms/<str:form_id>/export-fields/',
        v1_datos_export_fields,
        name='moreapp_v1_datos_export_fields',
    ),
]
