# coding: utf-8
import json
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest import mock

Usuario = get_user_model()


class MoreAppApiModulosTests(TestCase):
    def setUp(self):
        self.password = 'Seguro1234'
        self.admin = Usuario.objects.create_user(
            rut='33333333-3',
            email='admin-api@delco.cl',
            password=self.password,
            nombre='Admin',
            apellido='Api',
            nombre_interno='admin_api',
            rol='ADMIN',
            is_active=True,
        )
        self.tecnico = Usuario.objects.create_user(
            rut='44444444-4',
            email='tec-api@delco.cl',
            password=self.password,
            nombre='Tec',
            apellido='Api',
            nombre_interno='tec_api',
            rol='TECNICO',
            is_active=True,
        )

    def test_catalogo_requiere_login(self):
        resp = self.client.get(reverse('moreapp_api_catalogo'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_tecnico_no_accede_catalogo(self):
        self.client.login(username=self.tecnico.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_api_catalogo'))
        self.assertEqual(resp.status_code, 403)

    def test_administrativo_no_accede_catalogo(self):
        adminis = Usuario.objects.create_user(
            rut='66666666-6',
            email='adm-api@delco.cl',
            password=self.password,
            nombre='Adm',
            apellido='Api',
            nombre_interno='adm_api',
            rol='ADMINISTRATIVO',
            is_active=True,
        )
        self.client.login(username=adminis.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_api_catalogo'))
        self.assertEqual(resp.status_code, 403)
        dash = self.client.get(reverse('dashboard'))
        body = dash.content.decode('utf-8')
        self.assertNotIn('Catálogo MoreApp', body)
        self.assertIn('Formularios asignados', body)

    def test_admin_ve_catalogo_en_administracion(self):
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('dashboard'))
        body = resp.content.decode('utf-8')
        moreapp_block = body.split('MoreApp y reportes', 1)[1].split('Control', 1)[0]
        admin_block = body.split('Administración', 1)[1]
        self.assertNotIn('Catálogo MoreApp', moreapp_block)
        self.assertIn('Formularios asignados', moreapp_block)
        self.assertIn('Catálogo MoreApp', admin_block)

    @override_settings(MOREAPP_API_ENABLED=False)
    def test_json_forms_sin_api_enabled(self):
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_v1_visualizacion_forms_list'))
        self.assertEqual(resp.status_code, 400)
        payload = resp.json()
        self.assertFalse(payload['success'])
        self.assertEqual(payload['module'], 'visualizacion')

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_visualizacion_views.list_forms')
    def test_json_forms_ok_no_expone_api_key(self, mocked_list):
        mocked_list.return_value = [{'id': 'abc123abc123abc123abc123', 'name': 'OT Terreno'}]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_v1_visualizacion_forms_list'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertNotIn('test-key', body)
        payload = resp.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['module'], 'visualizacion')

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_datos_views.list_users')
    def test_json_users_modulo_datos(self, mocked_users):
        mocked_users.return_value = [{'id': 'u1', 'emailAddress': 'tec@delco.cl'}]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_v1_datos_users_list'))
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload['module'], 'datos')
        self.assertEqual(payload['operation'], 'users.list')

    def test_form_id_invalido_no_llama_moreapp(self):
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_v1_visualizacion_form_detail', args=['invalido!formulario'])
        )
        self.assertEqual(resp.status_code, 400)

    def test_registros_requiere_login(self):
        resp = self.client.get(
            reverse('moreapp_api_form_registros', args=['abc123abc123abc123abc123'])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_tecnico_no_accede_registros(self):
        self.client.login(username=self.tecnico.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_api_form_registros', args=['abc123abc123abc123abc123'])
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_registros_views.get_form_version')
    @mock.patch('integraciones.moreapp_registros_views.list_submissions')
    @mock.patch('integraciones.moreapp_registros_views.get_form')
    def test_registros_lista_aplana_info(self, mocked_form, mocked_subs, mocked_version):
        mocked_form.return_value = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Reposición de Suministro',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': 'ver123ver123ver123ver123'},
        }
        mocked_version.return_value = {
            'id': 'ver123ver123ver123ver123',
            'fields': [
                {
                    'widget': 'com.moreapps:number:1',
                    'properties': {'label_text': 'Num Cliente', 'data_name': 'numCliente'},
                }
            ],
        }
        mocked_subs.return_value = [
            {
                'id': 'sub123sub123sub123sub123',
                'info': {'userName': 'tec@delco.cl', 'date': '2026-10-14T12:00:00Z'},
                'meta': {'lastUpdated': '2026-10-14T12:01:00Z'},
                'data': {
                    'numCliente': '9852366',
                    'tecnicoResponsable': {'NOMBRES': 'Pedro Jalvear'},
                },
            }
        ]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_api_form_registros', args=['abc123abc123abc123abc123'])
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertNotIn('test-key', body)
        self.assertIn('9852366', body)
        self.assertIn('Pedro Jalvear', body)
        self.assertIn('Técnico responsable', body)
        self.assertIn('N° cliente', body)
        self.assertIn('14/10/2026', body)
        self.assertIn('Ver contenido', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_registros_views.get_form_version')
    @mock.patch('integraciones.moreapp_registros_views.get_submission')
    @mock.patch('integraciones.moreapp_registros_views.get_form')
    def test_registro_detalle_muestra_campos(self, mocked_form, mocked_sub, mocked_version):
        mocked_form.return_value = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Reposición de Suministro',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': 'ver123ver123ver123ver123'},
        }
        mocked_version.return_value = {
            'fields': [
                {
                    'widget': 'com.moreapps:number:1',
                    'properties': {'label_text': 'Num Cliente', 'data_name': 'numCliente'},
                }
            ]
        }
        mocked_sub.return_value = {
            'id': 'sub123sub123sub123sub123',
            'info': {'userName': 'tec@delco.cl'},
            'meta': {'created': '2026-10-14T12:00:00Z'},
            'data': {
                'numCliente': '9852366',
                'nota': 'Medidor ok',
                'fachada': 'gridfs://registrationFiles/7f555c8d-6a67-439c-ad41-da32206657b9',
            },
        }
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse(
                'moreapp_api_registro',
                args=['abc123abc123abc123abc123', 'sub123sub123sub123sub123'],
            )
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Num Cliente', body)
        self.assertIn('9852366', body)
        self.assertIn('Medidor ok', body)
        self.assertIn('7f555c8d-6a67-439c-ad41-da32206657b9', body)
        self.assertNotIn('test-key', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_registros_views.get_latest_submission')
    def test_ultimo_registro_devuelve_fecha(self, mocked_latest):
        mocked_latest.return_value = {
            'totalSize': 1,
            'elements': [
                {
                    'id': 'sub123sub123sub123sub123',
                    'info': {'date': 1739452535990, 'userId': 'tec@delco.cl'},
                }
            ],
        }
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_api_form_ultimo_registro', args=['abc123abc123abc123abc123'])
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['date'], '13/02/2025 10:15')
        self.assertEqual(payload['day'], '2025-02-13')
        self.assertNotIn('test-key', resp.content.decode('utf-8'))

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.list_all_forms')
    def test_catalogo_filtra_por_nombre(self, mocked_forms):
        mocked_forms.return_value = [
            {'id': 'abc123abc123abc123abc123', 'meta': {'name': 'Reposición de Suministro'}, 'status': 'ACTIVE'},
            {'id': 'def456def456def456def456', 'meta': {'name': 'Mantención medidor'}, 'status': 'ACTIVE'},
        ]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_api_catalogo'), {'query': 'reposicion'})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Reposición de Suministro', body)
        self.assertNotIn('Mantención medidor', body)
        self.assertIn('name="fecha_desde"', body)
        self.assertIn('name="fecha_hasta"', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.list_all_forms')
    def test_catalogo_pasa_fechas_a_registros(self, mocked_forms):
        mocked_forms.return_value = [
            {'id': 'abc123abc123abc123abc123', 'meta': {'name': 'Reposición de Suministro'}, 'status': 'ACTIVE'},
        ]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_api_catalogo'),
            {'fecha_desde': '2025-02-01', 'fecha_hasta': '2025-02-28'},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('fecha_desde=2025-02-01', body)
        self.assertIn('fecha_hasta=2025-02-28', body)
        self.assertIn('name="fecha_desde"', body)
        self.assertIn('js-form-card', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.list_all_forms')
    def test_catalogo_ocultar_es_por_usuario(self, mocked_forms):
        from integraciones.models import MoreAppFormularioOculto

        form_id = 'abc123abc123abc123abc123'
        mocked_forms.return_value = [
            {'id': form_id, 'meta': {'name': 'Reposición de Suministro'}, 'status': 'ACTIVE'},
        ]
        otro = Usuario.objects.create_user(
            rut='55555555-5',
            email='admin2-api@delco.cl',
            password=self.password,
            nombre='Admin',
            apellido='Dos',
            nombre_interno='admin_api_2',
            rol='ADMIN',
            is_active=True,
        )
        self.client.login(username=self.admin.rut, password=self.password)
        hide = self.client.post(
            reverse('moreapp_api_form_ocultar', args=[form_id]),
            {'nombre': 'Reposición de Suministro'},
        )
        self.assertEqual(hide.status_code, 302)
        self.assertTrue(
            MoreAppFormularioOculto.objects.filter(usuario=self.admin, form_id=form_id).exists()
        )
        resp = self.client.get(reverse('moreapp_api_catalogo'))
        self.assertNotIn('Reposición de Suministro', resp.content.decode('utf-8'))
        shown = self.client.get(reverse('moreapp_api_catalogo'), {'mostrar_ocultos': '1'})
        self.assertIn('Reposición de Suministro', shown.content.decode('utf-8'))
        self.assertIn('Oculto en tu catálogo', shown.content.decode('utf-8'))
        self.client.logout()
        self.client.login(username=otro.rut, password=self.password)
        other = self.client.get(reverse('moreapp_api_catalogo'))
        self.assertIn('Reposición de Suministro', other.content.decode('utf-8'))
        restore = self.client.post(reverse('moreapp_api_form_mostrar', args=[form_id]))
        self.assertEqual(restore.status_code, 302)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_registros_views.get_form_version')
    @mock.patch('integraciones.moreapp_registros_views.list_submissions')
    @mock.patch('integraciones.moreapp_registros_views.get_form')
    def test_registros_filtra_por_fecha_y_nombre(self, mocked_form, mocked_subs, mocked_version):
        mocked_form.return_value = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Reposición de Suministro',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': 'ver123ver123ver123ver123'},
        }
        mocked_version.return_value = {'fields': []}
        mocked_subs.return_value = {
            'totalSize': 1,
            'elements': [
                {
                    'id': 'sub123sub123sub123sub123',
                    'info': {'userName': 'Juan Perez', 'userId': 'juan@delco.cl', 'date': '2026-10-14T12:00:00Z'},
                    'data': {
                        'numCliente': 858678,
                        'tecnicoResponsable': {'NOMBRES': 'Juan Perez'},
                    },
                }
            ],
        }
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_api_form_registros', args=['abc123abc123abc123abc123']),
            {
                'fecha_desde': '2026-10-01',
                'fecha_hasta': '2026-10-31',
                'tecnico': 'Juan',
                'num_cliente': '858678',
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Juan Perez', body)
        self.assertIn('858678', body)
        payload = mocked_subs.call_args.kwargs.get('payload') or mocked_subs.call_args[1].get('payload')
        query = payload['query']
        self.assertEqual(query[0]['path'], 'info.date')
        self.assertEqual(query[0]['type'], 'date')
        self.assertIn('start', query[0]['value'])
        self.assertIn('end', query[0]['value'])
        self.assertEqual(query[1]['path'], 'data.numCliente')
        self.assertEqual(query[1]['value'], 858678)
        self.assertIn('tecnico=Juan', body)
        self.assertIn('num_cliente=858678', body)
        self.assertIn('export=xlsx', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_api.list_forms')
    def test_catalogo_junta_varias_paginas(self, mocked_forms):
        mocked_forms.side_effect = [
            [{'id': 'aaa123abc123abc123abc123', 'meta': {'name': 'Formulario A'}, 'status': 'ACTIVE'}],
            [{'id': 'bbb456def456def456def456', 'meta': {'name': 'Formulario B'}, 'status': 'ACTIVE'}],
            [],
        ]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_api_catalogo'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Formulario A', body)
        self.assertIn('Formulario B', body)
        self.assertGreaterEqual(mocked_forms.call_count, 2)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.get_form_version')
    @mock.patch('integraciones.moreapp_catalogo_views.list_form_versions')
    @mock.patch('integraciones.moreapp_catalogo_views.get_form')
    def test_formulario_version_fecha_ddmmaaaa(self, mocked_form, mocked_versions, mocked_version):
        mocked_form.return_value = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Reposición de Suministro',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': 'ver123ver123ver123ver123'},
        }
        mocked_versions.return_value = [
            {
                'id': 'ver123ver123ver123ver123',
                'status': 'PUBLISHED',
                'meta': {'lastUpdated': '2026-10-14T12:00:00Z', 'lastUpdatedBy': 'editor'},
            }
        ]
        mocked_version.return_value = {'fields': []}
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_api_formulario', args=['abc123abc123abc123abc123']))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('14/10/2026', body)
        self.assertNotIn('2026-10-14T12:00:00Z', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.list_datasources')
    def test_datasources_tabla_columnas_y_fecha(self, mocked_ds):
        mocked_ds.return_value = [
            {
                'id': '6491e945a2abd076df165abc',
                'name': 'comunas',
                'searchType': 'LOCAL_FALLBACK',
                'enabled': True,
                'lastUpdated': 1687290265881,
                'columnMapping': [{'id': 'id', 'label': 'Id'}, {'id': 'comuna', 'label': 'Comuna'}],
            }
        ]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_api_datasources'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('comunas', body)
        self.assertIn('Comuna', body)
        self.assertIn('Última actualización', body)
        self.assertIn('20/06/2023', body)
        self.assertNotIn('1687290265881', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.list_datasource_entry_rows')
    @mock.patch('integraciones.moreapp_catalogo_views.get_datasource')
    def test_datasource_muestra_contenido_de_filas(self, mocked_get, mocked_rows):
        mocked_get.return_value = {
            'id': '6491e945a2abd076df165abc',
            'name': 'comunas',
            'columnMapping': [{'id': 'id', 'label': 'Id'}, {'id': 'comuna', 'label': 'Comuna'}],
        }
        mocked_rows.return_value = {
            'total': 2,
            'columns': [{'id': 'id', 'label': 'Id'}, {'id': 'comuna', 'label': 'Comuna'}],
            'rows': [
                {'id': '1', 'comuna': 'CONCHALI'},
                {'id': '2', 'comuna': 'SANTIAGO'},
            ],
            'fetched': 2,
            'truncated': False,
            'limit': 250,
        }
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_api_datasource', args=['6491e945a2abd076df165abc']))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Contenido de la tabla', body)
        self.assertIn('CONCHALI', body)
        self.assertIn('SANTIAGO', body)
        filtrado = self.client.get(
            reverse('moreapp_api_datasource', args=['6491e945a2abd076df165abc']),
            {'query': 'santiago'},
        )
        filtrado_body = filtrado.content.decode('utf-8')
        self.assertIn('SANTIAGO', filtrado_body)
        self.assertNotIn('CONCHALI', filtrado_body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.list_users')
    def test_usuarios_moreapp_filtra_correo(self, mocked_users):
        mocked_users.return_value = [
            {
                'id': 'u1',
                'emailAddress': 'juan@delco.cl',
                'username': 'juan@delco.cl',
                'disabled': False,
                'emailValidated': True,
                'groups': ['g1'],
            },
            {
                'id': 'u2',
                'emailAddress': 'otro@moreapp.com',
                'username': 'otro@moreapp.com',
                'disabled': True,
                'emailValidated': False,
                'groups': [],
            },
        ]
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('usuarios_moreapp'), {'query': 'juan'})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('juan@delco.cl', body)
        self.assertNotIn('otro@moreapp.com', body)
        self.assertIn('Usuario MoreApp', body)
        self.assertIn('Usuario interno', body)
        self.assertIn('No se copian a la intranet', body)
        self.assertNotIn('vincular técnico', body.lower())
        self.assertNotIn('mapear usuario', body.lower())
        self.assertIn('navUsuariosMoreapp-', body)
        self.assertIn('Técnicos', body)
        self.assertIn('Certelec Técnicos', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.list_datasource_entry_rows')
    @mock.patch('integraciones.moreapp_catalogo_views.list_datasources')
    def test_usuarios_moreapp_muestra_tecnicos_y_certelec(self, mocked_ds, mocked_rows):
        mocked_ds.return_value = [
            {
                'id': '690cdeaea4d2441300ec961d',
                'name': 'Tecnicos',
                'columnMapping': [{'id': 'id', 'label': 'Id'}, {'id': 'NOMBRES', 'label': 'NOMBRES'}],
            },
            {
                'id': '68cab36aca9ce33084120ae2',
                'name': 'Certelec Técnicos',
                'columnMapping': [{'id': 'id', 'label': 'Id'}, {'id': 'nombres', 'label': 'Nombres'}],
            },
        ]
        mocked_rows.return_value = {
            'total': 2,
            'columns': [{'id': 'id', 'label': 'Id'}, {'id': 'NOMBRES', 'label': 'NOMBRES'}],
            'rows': [
                {'id': '1', 'NOMBRES': 'ALEXANDER ANDRES GONTHIER'},
                {'id': '2', 'NOMBRES': 'ASHLY LLANQUIMAN'},
            ],
            'fetched': 2,
            'truncated': False,
        }
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('usuarios_moreapp_tecnicos'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('ALEXANDER ANDRES GONTHIER', body)
        self.assertIn('ASHLY LLANQUIMAN', body)
        self.assertNotIn('vincular técnico', body.lower())
        mocked_rows.return_value = {
            'total': 1,
            'columns': [{'id': 'id', 'label': 'Id'}, {'id': 'nombres', 'label': 'Nombres'}],
            'rows': [{'id': '1', 'nombres': 'Juan Andres Maldonado Perez'}],
            'fetched': 1,
            'truncated': False,
        }
        certelec = self.client.get(reverse('usuarios_moreapp_certelec'))
        self.assertEqual(certelec.status_code, 200)
        certelec_body = certelec.content.decode('utf-8')
        self.assertIn('Juan Andres Maldonado Perez', certelec_body)
        self.assertIn('Certelec Técnicos', certelec_body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_registros_views.get_form_version')
    @mock.patch('integraciones.moreapp_registros_views.get_submission')
    @mock.patch('integraciones.moreapp_registros_views.get_form')
    def test_detalle_conserva_filtros_al_volver(self, mocked_form, mocked_sub, mocked_version):
        mocked_form.return_value = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Reposición de Suministro',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': 'ver123ver123ver123ver123'},
        }
        mocked_version.return_value = {'fields': []}
        mocked_sub.return_value = {
            'id': 'sub123sub123sub123sub123',
            'info': {'userName': 'Juan Perez', 'date': '2026-10-14T12:00:00Z'},
            'data': {'numCliente': '858678'},
        }
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse(
                'moreapp_api_registro',
                args=['abc123abc123abc123abc123', 'sub123sub123sub123sub123'],
            ),
            {'tecnico': 'Juan', 'num_cliente': '858678', 'fecha_desde': '2026-10-01'},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('tecnico=Juan', body)
        self.assertIn('num_cliente=858678', body)
        self.assertIn('fecha_desde=2026-10-01', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_registros_views.get_form_version')
    @mock.patch('integraciones.moreapp_registros_views.list_submissions')
    @mock.patch('integraciones.moreapp_registros_views.get_form')
    def test_registros_exporta_excel(self, mocked_form, mocked_subs, mocked_version):
        mocked_form.return_value = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Reposición de Suministro',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': 'ver123ver123ver123ver123'},
        }
        mocked_version.return_value = {'fields': []}
        mocked_subs.return_value = {
            'totalSize': 1,
            'elements': [
                {
                    'id': 'sub123sub123sub123sub123',
                    'info': {'userName': 'Juan Perez', 'date': '2026-10-14T12:00:00Z'},
                    'data': {'numCliente': 858678, 'tecnicoResponsable': {'NOMBRES': 'Juan Perez'}},
                }
            ],
        }
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_api_form_registros', args=['abc123abc123abc123abc123']),
            {'tecnico': 'Juan', 'export': 'xlsx'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resp['Content-Type'],
        )
        self.assertIn('attachment', resp['Content-Disposition'])
        self.assertGreater(len(resp.content), 100)

    def test_usuarios_internos_distinguen_moreapp(self):
        self.client.login(username=self.admin.rut, password=self.password)
        resp = self.client.get(reverse('usuarios_list'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Usuario MoreApp', body)
        self.assertIn('Usuario interno', body)
        self.assertIn('Interno', body)
        self.assertIn('/usuarios/moreapp/', body)
        self.assertIn('data-bs-toggle="collapse"', body)
        self.assertIn('navUsuarios-', body)
        self.assertIn('navUsuariosMoreapp-', body)
        self.assertIn('Técnicos', body)
        self.assertIn('Certelec Técnicos', body)
        self.assertIn('/usuarios/moreapp/tecnicos/', body)
        self.assertIn('/usuarios/moreapp/certelec/', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.get_datasource_entries')
    @mock.patch('integraciones.moreapp_catalogo_views.get_datasource')
    @mock.patch('integraciones.moreapp_catalogo_views.list_datasources')
    def test_guardar_fuente_es_opt_in(self, mocked_list, mocked_get, mocked_entries):
        from integraciones.models import MoreAppFuenteInterna

        mocked_list.return_value = [
            {
                'id': '6491e945a2abd076df165abc',
                'name': 'comunas',
                'searchType': 'LOCAL_FALLBACK',
                'enabled': True,
                'columnMapping': [{'id': 'id', 'label': 'Id'}, {'id': 'comuna', 'label': 'Comuna'}],
            },
            {
                'id': '690cdeaea4d2441300ec961d',
                'name': 'Tecnicos',
                'searchType': 'LOCAL_FALLBACK',
                'enabled': True,
                'columnMapping': [{'id': 'id', 'label': 'Id'}, {'id': 'NOMBRES', 'label': 'NOMBRES'}],
            },
        ]
        mocked_get.return_value = mocked_list.return_value[0]
        mocked_entries.return_value = {'numberOfEntries': 33, 'dataKeyList': mocked_list.return_value[0]['columnMapping']}
        self.client.login(username=self.admin.rut, password=self.password)
        save = self.client.post(
            reverse('moreapp_api_datasource_guardar', args=['6491e945a2abd076df165abc'])
        )
        self.assertEqual(save.status_code, 302)
        self.assertTrue(
            MoreAppFuenteInterna.objects.filter(datasource_id='6491e945a2abd076df165abc').exists()
        )
        self.assertEqual(MoreAppFuenteInterna.objects.count(), 1)
        listing = self.client.get(reverse('moreapp_api_datasources'))
        body = listing.content.decode('utf-8')
        self.assertIn('Guardada', body)
        self.assertIn('No se guarda', body)
        self.assertIn('Guardar en intranet', body)
        only_local = self.client.get(reverse('moreapp_api_datasources'), {'solo_internas': '1'})
        only_body = only_local.content.decode('utf-8')
        self.assertIn('comunas', only_body)
        self.assertNotIn('Tecnicos', only_body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_catalogo_views.get_datasource_entries')
    @mock.patch('integraciones.moreapp_catalogo_views.get_datasource')
    def test_importar_filas_solo_si_esta_guardada(self, mocked_get, mocked_entries):
        from integraciones.models import MoreAppFuenteFila, MoreAppFuenteInterna

        mocked_get.return_value = {
            'id': '6491e945a2abd076df165abc',
            'name': 'comunas',
            'columnMapping': [{'id': 'id', 'label': 'Id'}, {'id': 'comuna', 'label': 'Comuna'}],
        }
        mocked_entries.return_value = {'numberOfEntries': 2, 'dataKeyList': mocked_get.return_value['columnMapping']}
        self.client.login(username=self.admin.rut, password=self.password)
        archivo = SimpleUploadedFile(
            'comunas.json',
            json.dumps([{'id': 'stgo', 'comuna': 'Santiago'}, {'id': 'maipu', 'comuna': 'Maipu'}]).encode('utf-8'),
            content_type='application/json',
        )
        denied = self.client.post(
            reverse('moreapp_api_datasource_importar', args=['6491e945a2abd076df165abc']),
            {'archivo': archivo},
        )
        self.assertEqual(denied.status_code, 302)
        self.assertEqual(MoreAppFuenteFila.objects.count(), 0)
        self.client.post(reverse('moreapp_api_datasource_guardar', args=['6491e945a2abd076df165abc']))
        archivo2 = SimpleUploadedFile(
            'comunas.json',
            json.dumps([{'id': 'stgo', 'comuna': 'Santiago'}, {'id': 'maipu', 'comuna': 'Maipu'}]).encode('utf-8'),
            content_type='application/json',
        )
        imported = self.client.post(
            reverse('moreapp_api_datasource_importar', args=['6491e945a2abd076df165abc']),
            {'archivo': archivo2},
        )
        self.assertEqual(imported.status_code, 302)
        fuente = MoreAppFuenteInterna.objects.get(datasource_id='6491e945a2abd076df165abc')
        self.assertEqual(fuente.filas.count(), 2)
        self.assertEqual(MoreAppFuenteFila.objects.get(entry_id='stgo').valores.get('comuna'), 'Santiago')
        detail = self.client.get(reverse('moreapp_api_datasource', args=['6491e945a2abd076df165abc']))
        self.assertIn('Santiago', detail.content.decode('utf-8'))
        self.assertIn('Copia en la intranet', detail.content.decode('utf-8'))

    def test_listado_formularios_requiere_login(self):
        resp = self.client.get(reverse('moreapp_formularios_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_tecnico_ve_formularios_en_sidebar(self):
        self.client.login(username=self.tecnico.rut, password=self.password)
        resp = self.client.get(reverse('dashboard'))
        body = resp.content.decode('utf-8')
        self.assertIn('Formularios asignados', body)
        self.assertNotIn('Pendientes MoreApp', body)
        self.assertNotIn('Catálogo MoreApp', body)

    def test_tecnico_sin_asignacion_lista_vacia(self):
        self.client.login(username=self.tecnico.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_formularios_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('No tienes formularios asignados', resp.content.decode('utf-8'))

    def test_tecnico_no_asigna_formularios(self):
        self.client.login(username=self.tecnico.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_formulario_asignar', args=['abc123abc123abc123abc123'])
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_formularios_views.list_all_forms')
    @mock.patch('integraciones.moreapp_catalogo_views.list_all_forms')
    def test_admin_lista_y_asigna_formulario(self, mocked_catalogo_forms, mocked_list_forms):
        from integraciones.models import MoreAppFormularioAsignado

        form = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Instalacion',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': '1'},
        }
        extra = {
            'id': 'def456def456def456def456',
            'name': 'Retiro',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': '1'},
        }
        mocked_catalogo_forms.return_value = [form, extra]
        mocked_list_forms.return_value = [form, extra]
        adminis = Usuario.objects.create_user(
            rut='66666666-6',
            email='adm-asig@delco.cl',
            password=self.password,
            nombre='Adm',
            apellido='Asig',
            nombre_interno='adm_api',
            rol='ADMINISTRATIVO',
            is_active=True,
        )
        self.client.login(username=self.admin.rut, password=self.password)
        vacio = self.client.get(reverse('moreapp_formularios_list'))
        self.assertEqual(vacio.status_code, 200)
        self.assertIn('Aún no hay formularios asignados', vacio.content.decode('utf-8'))
        catalogo = self.client.get(reverse('moreapp_api_catalogo'))
        self.assertEqual(catalogo.status_code, 200)
        body = catalogo.content.decode('utf-8')
        self.assertIn('Instalacion', body)
        self.assertIn('Asignar usuarios', body)
        self.assertIn('modalAsignarFormulario', body)
        self.assertIn('type="checkbox"', body)
        self.assertIn('adm_api', body)
        self.assertNotIn('tec_api', body)
        get_page = self.client.get(
            reverse('moreapp_formulario_asignar', args=['abc123abc123abc123abc123'])
        )
        self.assertEqual(get_page.status_code, 302)
        self.assertEqual(get_page.url, reverse('moreapp_api_catalogo'))
        denied = self.client.post(
            reverse('moreapp_formulario_asignar', args=['abc123abc123abc123abc123']),
            {'nombre': 'Instalacion', 'usuarios': [str(self.tecnico.pk)]},
        )
        self.assertEqual(denied.status_code, 302)
        self.assertFalse(
            MoreAppFormularioAsignado.objects.filter(
                usuario=self.tecnico,
                form_id='abc123abc123abc123abc123',
            ).exists()
        )
        post = self.client.post(
            reverse('moreapp_formulario_asignar', args=['abc123abc123abc123abc123']),
            {'nombre': 'Instalacion', 'usuarios': [str(adminis.pk), str(self.admin.pk)]},
        )
        self.assertEqual(post.status_code, 302)
        self.assertEqual(
            MoreAppFormularioAsignado.objects.filter(
                form_id='abc123abc123abc123abc123',
            ).count(),
            2,
        )
        self.assertTrue(
            MoreAppFormularioAsignado.objects.filter(
                usuario=adminis,
                form_id='abc123abc123abc123abc123',
            ).exists()
        )
        listing = self.client.get(reverse('moreapp_formularios_list'))
        self.assertEqual(listing.status_code, 200)
        list_body = listing.content.decode('utf-8')
        self.assertIn('Instalacion', list_body)
        self.assertNotIn('Retiro', list_body)
        self.assertIn('adm_api', list_body)
        self.assertNotIn('Asignar usuarios', list_body)
        self.assertNotIn('Ir al catálogo', list_body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_formularios_views.list_all_forms')
    def test_tecnico_solo_ve_formularios_asignados(self, mocked_forms):
        from integraciones.models import MoreAppFormularioAsignado

        mocked_forms.return_value = [
            {
                'id': 'abc123abc123abc123abc123',
                'name': 'Instalacion',
                'status': 'ACTIVE',
                'publishedVersion': {'formVersion': '1'},
            },
            {
                'id': 'def456def456def456def456',
                'name': 'Retiro',
                'status': 'ACTIVE',
                'publishedVersion': {'formVersion': '1'},
            },
        ]
        MoreAppFormularioAsignado.objects.create(
            usuario=self.tecnico,
            form_id='abc123abc123abc123abc123',
            form_name='Instalacion',
        )
        self.client.login(username=self.tecnico.rut, password=self.password)
        resp = self.client.get(reverse('moreapp_formularios_list'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Instalacion', body)
        self.assertNotIn('Retiro', body)
        self.assertNotIn('Asignar usuarios', body)

    @override_settings(
        MOREAPP_API_ENABLED=True,
        MOREAPP_API_KEY='test-key',
        MOREAPP_CUSTOMER_ID='123',
    )
    @mock.patch('integraciones.moreapp_registros_views.get_form_version')
    @mock.patch('integraciones.moreapp_registros_views.list_submissions')
    @mock.patch('integraciones.moreapp_registros_views.get_form')
    def test_tecnico_con_asignacion_accede_registros(self, mocked_form, mocked_subs, mocked_version):
        from integraciones.models import MoreAppFormularioAsignado

        MoreAppFormularioAsignado.objects.create(
            usuario=self.tecnico,
            form_id='abc123abc123abc123abc123',
            form_name='Instalacion',
        )
        mocked_form.return_value = {
            'id': 'abc123abc123abc123abc123',
            'name': 'Instalacion',
            'status': 'ACTIVE',
            'publishedVersion': {'formVersion': 'ver123ver123ver123ver123'},
        }
        mocked_version.return_value = {'id': 'ver123ver123ver123ver123', 'fields': []}
        mocked_subs.return_value = {'data': []}
        self.client.login(username=self.tecnico.rut, password=self.password)
        resp = self.client.get(
            reverse('moreapp_api_form_registros', args=['abc123abc123abc123abc123'])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Instalacion', resp.content.decode('utf-8'))
