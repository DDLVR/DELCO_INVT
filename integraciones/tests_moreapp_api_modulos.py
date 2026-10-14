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
                'data': {'numCliente': '9852366'},
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
        self.assertIn('tec@delco.cl', body)
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
        self.assertEqual(payload['date'], '2025-02-13 13:15')
        self.assertNotIn('test-key', resp.content.decode('utf-8'))
