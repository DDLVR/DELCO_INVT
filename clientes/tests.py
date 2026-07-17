from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from inventario.models import Medidor
from usuarios.models import Usuario

from .models import Cliente


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class ClienteFlujoViewTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.usuario = Usuario.objects.create_user(
			rut='11111111-1',
			email='admin_test@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Test',
			nombre_interno='admin_test',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.medidor = Medidor.objects.create(
			serie='MED-TEST-9001',
			marca='TEST',
			tipo_medidor='DIRECTO',
		)
		self.medidor_alt = Medidor.objects.create(
			serie='MED-TEST-9002',
			marca='TEST',
			tipo_medidor='DIRECTO',
		)
		self.client = Client()
		login_ok = self.client.login(rut=self.usuario.rut, password=self.password)
		self.assertTrue(login_ok)

	def _payload_base(self):
		return {
			'numero_cliente': 'CLI-TEST-9001',
			'comuna': 'Santiago',
			'tipo_suministro': 'ELECTRICO',
			'sector': 'NORTE',
			'customer_name': 'Cliente Prueba',
			'installation_address': 'Inst 123',
			'proyecto': '',
			'medidor_opcion': 'crear_medidor',
			'meter_manufacturer_id': 'SCHNEIDER',
			'meter_serial_n_1': self.medidor.serie,
			'ultimo_acceso': '2026-07-08',
			'ultimo_perfil_carga': '',
			'ultimo_reset': '2026-07-08',
			'ultimo_registro_facturacion': '2026-07-08',
			'note': 'nota',
			'ip': '10.10.10.1',
			'puerto': '',
			'modem': 'MODEM-TEST-001',
			'fecha_registro': '2026-07-08',
		}

	def test_creacion_bloquea_ip_invalida(self):
		payload = self._payload_base()
		payload['numero_cliente'] = 'CLI-TEST-9002'
		payload['ip'] = '999.10.10.1'

		response = self.client.post(reverse('cliente_crear'), payload)

		self.assertEqual(response.status_code, 302)
		self.assertFalse(
			Cliente.objects.filter(numero_cliente='CLI-TEST-9002', activo=True).exists()
		)

	def test_creacion_aplica_defaults_y_edicion_funciona(self):
		payload = self._payload_base()

		response = self.client.post(reverse('cliente_crear'), payload)
		self.assertEqual(response.status_code, 302)

		cliente = Cliente.objects.get(
			numero_cliente='CLI-TEST-9001',
			meter_serial_n_1=self.medidor.serie,
			activo=True,
		)
		self.assertEqual(cliente.proyecto, 'SIN PROYECTO')
		self.assertEqual(cliente.ultimo_perfil_carga, 'SIN PERFIL')

		editar_payload = {
			'numero_cliente': cliente.numero_cliente,
			'sector': 'SUR',
			'tipo_suministro': cliente.tipo_suministro,
			'comuna': cliente.comuna,
			'customer_name': cliente.customer_name,
			'installation_address': cliente.installation_address,
			'proyecto': cliente.proyecto,
			'meter_manufacturer_id': cliente.meter_manufacturer_id,
			'meter_serial_n_1': cliente.meter_serial_n_1,
		}
		edit_response = self.client.post(
			reverse('cliente_editar', kwargs={'pk': cliente.pk}),
			editar_payload,
		)

		self.assertEqual(edit_response.status_code, 302)
		cliente.refresh_from_db()
		self.assertEqual(cliente.sector, 'SUR')

	def test_creacion_bloquea_duplicado_exacto_numero_y_serie(self):
		payload = self._payload_base()
		self.assertEqual(self.client.post(reverse('cliente_crear'), payload).status_code, 302)

		response_dup = self.client.post(reverse('cliente_crear'), payload)
		self.assertEqual(response_dup.status_code, 302)

		self.assertEqual(
			Cliente.objects.filter(
				numero_cliente='CLI-TEST-9001',
				meter_serial_n_1=self.medidor.serie,
				activo=True,
			).count(),
			1,
		)

	def test_creacion_permite_mismo_numero_con_serie_distinta(self):
		payload_1 = self._payload_base()
		self.assertEqual(self.client.post(reverse('cliente_crear'), payload_1).status_code, 302)

		payload_2 = self._payload_base()
		payload_2['meter_serial_n_1'] = self.medidor_alt.serie
		payload_2['ip'] = '10.10.10.2'

		response_2 = self.client.post(reverse('cliente_crear'), payload_2)
		self.assertEqual(response_2.status_code, 302)

		self.assertEqual(
			Cliente.objects.filter(numero_cliente='CLI-TEST-9001', activo=True).count(),
			2,
		)

	def test_creacion_sin_medidor_permite_alta(self):
		payload = self._payload_base()
		payload['numero_cliente'] = 'CLI-TEST-SIN-MED'
		payload['medidor_opcion'] = 'sin_medidor'
		payload['meter_serial_n_1'] = ''
		payload['meter_manufacturer_id'] = ''
		payload['ip'] = '10.10.10.9'

		response = self.client.post(reverse('cliente_crear'), payload)
		self.assertEqual(response.status_code, 302)

		cliente = Cliente.objects.get(numero_cliente='CLI-TEST-SIN-MED', activo=True)
		self.assertFalse(cliente.meter_serial_n_1)
		self.assertIsNone(cliente.medidor_actual)
		self.assertEqual(cliente.estado_telemetria, 'SIN_MEDIDOR')
		self.assertEqual(cliente.direccion, 'Inst 123')

	def test_creacion_crear_medidor_sin_serie_bloquea(self):
		payload = self._payload_base()
		payload['numero_cliente'] = 'CLI-TEST-SIN-SERIE'
		payload['medidor_opcion'] = 'crear_medidor'
		payload['meter_serial_n_1'] = ''

		response = self.client.post(reverse('cliente_crear'), payload)
		self.assertEqual(response.status_code, 302)
		self.assertFalse(
			Cliente.objects.filter(numero_cliente='CLI-TEST-SIN-SERIE', activo=True).exists()
		)

	def test_formulario_crear_no_pide_direccion_base_ni_ciudad(self):
		response = self.client.get(reverse('cliente_crear'))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		self.assertNotIn('Dirección Base', html)
		self.assertNotIn('name="city"', html)
		self.assertIn('Sin medidor', html)
		self.assertIn('Crear medidor', html)
		self.assertIn('modalCrearMedidor', html)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class ClienteImportarViewTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.usuario = Usuario.objects.create_user(
			rut='33333333-3',
			email='import_view_test@delco.cl',
			password=self.password,
			nombre='Import',
			apellido='View',
			nombre_interno='import_view',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.client = Client()
		login_ok = self.client.login(rut=self.usuario.rut, password=self.password)
		self.assertTrue(login_ok)

	def _excel_upload(self, rows):
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.title = 'CLIENTES'
		ws.append([
			'Sector',
			'Tipo Suministro',
			'Numero Cliente',
			'Comuna',
			'Nombre Cliente',
			'Direccion de Instalacion',
			'Marca Medidor',
			'Proyecto',
			'Serie Medidor',
		])
		for row in rows:
			ws.append(row)

		buf = BytesIO()
		wb.save(buf)
		buf.seek(0)
		return SimpleUploadedFile(
			'clientes_import_test.xlsx',
			buf.read(),
			content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
		)

	def test_importar_endpoint_incremental_no_desactiva_existentes(self):
		Cliente.objects.create(
			numero_cliente='CLI-OLD-UI',
			direccion='Dir old',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Old UI',
			installation_address='Inst old',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-OLD-UI',
			activo=True,
		)

		response = self.client.post(
			reverse('clientes_importar'),
			{
				'archivo': self._excel_upload([
					['CENTRO', 'ELECTRICO', 'CLI-NEW-UI', 'Santiago', 'Nuevo UI', 'Inst new', 'TEST', 'PROY X', 'SER-NEW-UI'],
				]),
				'modo_importacion': 'incremental',
			},
		)

		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data.get('modo_importacion'), 'incremental')
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-NEW-UI', activo=True).exists())
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-OLD-UI', activo=True).exists())

	def test_importar_endpoint_sync_desactiva_faltantes(self):
		Cliente.objects.create(
			numero_cliente='CLI-KEEP-UI',
			direccion='Dir keep',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Keep UI',
			installation_address='Inst keep',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-KEEP-UI',
			activo=True,
		)
		Cliente.objects.create(
			numero_cliente='CLI-DROP-UI',
			direccion='Dir drop',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='SUR',
			customer_name='Drop UI',
			installation_address='Inst drop',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-DROP-UI',
			activo=True,
		)

		response = self.client.post(
			reverse('clientes_importar'),
			{
				'archivo': self._excel_upload([
					['NORTE', 'ELECTRICO', 'CLI-KEEP-UI', 'Santiago', 'Keep UI 2', 'Inst keep 2', 'TEST', 'PROY Y', 'SER-KEEP-UI'],
				]),
				'modo_importacion': 'sync',
			},
		)

		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data.get('modo_importacion'), 'sincronizacion_completa')
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-KEEP-UI', activo=True).exists())
		self.assertFalse(Cliente.objects.filter(numero_cliente='CLI-DROP-UI', activo=True).exists())
