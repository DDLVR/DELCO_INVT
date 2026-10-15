# coding: utf-8
from django.contrib.auth import get_user_model
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
        resp = self.client.get(reverse('moreapp_api_usuarios'), {'query': 'juan'})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('juan@delco.cl', body)
        self.assertNotIn('otro@moreapp.com', body)
        self.assertIn('Usuarios MoreApp', body)
        self.assertNotIn('vincular técnico', body.lower())
        self.assertNotIn('mapear usuario', body.lower())

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
