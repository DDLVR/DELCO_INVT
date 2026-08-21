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
			'medidor_opcion': 'asignar_lista',
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
		payload['medidor_opcion'] = 'asignar_lista'
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
		self.assertIn('medidorSelect', html)
		self.assertIn('modalCrearMedidor', html)
		self.assertContains(response, self.medidor.serie)

	def test_formulario_excluye_medidor_ya_asignado(self):
		Cliente.objects.create(
			numero_cliente='CLI-ASIG-1',
			direccion='Dir',
			comuna='Santiago',
			meter_serial_n_1=self.medidor.serie,
			medidor_actual=self.medidor,
			activo=True,
		)
		response = self.client.get(reverse('cliente_crear'))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		self.assertNotIn(f'data-serie="{self.medidor.serie}"', html)
		self.assertIn(f'data-serie="{self.medidor_alt.serie}"', html)

	def test_listado_editar_apunta_al_historial_sin_modal(self):
		cliente = Cliente.objects.create(
			numero_cliente='CLI-EDIT-UI',
			direccion='Dir',
			comuna='Santiago',
			meter_serial_n_1=self.medidor.serie,
			medidor_actual=self.medidor,
			activo=True,
		)
		response = self.client.get(reverse('clientes_list'))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		self.assertNotIn('modalEditarCliente', html)
		self.assertNotIn('btn-editar-cliente', html)
		self.assertIn(f'/clientes/{cliente.pk}/historial/?editar=1', html)

	def test_historial_tiene_edicion_inline_sin_modal(self):
		cliente = Cliente.objects.create(
			numero_cliente='CLI-HIST-UI',
			direccion='Dir',
			comuna='Santiago',
			customer_name='Cliente Historial',
			meter_serial_n_1=self.medidor.serie,
			medidor_actual=self.medidor,
			ip='10.20.30.40',
			activo=True,
		)
		response = self.client.get(reverse('cliente_historial', kwargs={'pk': cliente.pk}))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		self.assertNotIn('modalEditarClienteHistorial', html)
		self.assertIn('id="fichaCliente"', html)
		self.assertIn('id="btnEditarFichaCliente"', html)
		self.assertIn('name="customer_name"', html)
		self.assertIn('name="ip"', html)
		self.assertIn('name="modem"', html)
		self.assertIn('name="direccion"', html)
		self.assertIn('name="city"', html)
		self.assertIn('name="empresa"', html)
		self.assertIn('name="referencia"', html)
		self.assertIn('name="estado_telemetria"', html)
		self.assertIn('name="estado_stb"', html)
		self.assertIn('name="sim_operador"', html)
		self.assertIn('name="sim_iccid"', html)
		self.assertIn('name="sim_abonado"', html)
		self.assertIn('name="sim_estado"', html)
		self.assertIn('name="ultimo_acceso"', html)
		self.assertIn('name="fecha_registro"', html)
		self.assertIn('name="trabajo"', html)
		self.assertIn('name="note"', html)
		self.assertIn('class="form-control form-control-sm ficha-edit"', html)
		self.assertIn('id="documentosCliente"', html)
		self.assertIn('Documentos del cliente', html)
		self.assertIn('name="accion" value="subir_adjunto"', html)

	def test_edicion_guarda_campos_extendidos_de_ficha(self):
		cliente = Cliente.objects.create(
			numero_cliente='CLI-EXT-EDIT',
			direccion='Dir Vieja',
			comuna='Santiago',
			customer_name='Antes',
			meter_serial_n_1=self.medidor.serie,
			medidor_actual=self.medidor,
			ip='10.0.0.1',
			activo=True,
		)
		response = self.client.post(
			reverse('cliente_editar', kwargs={'pk': cliente.pk}),
			{
				'numero_cliente': cliente.numero_cliente,
				'sector': 'SUR',
				'tipo_suministro': 'ELECTRICO',
				'comuna': 'Maipu',
				'customer_name': 'Despues',
				'installation_address': 'Inst Nueva',
				'direccion': 'Dir Nueva',
				'city': 'Santiago',
				'empresa': 'Delco',
				'referencia': 'Puerta azul',
				'proyecto': '',
				'meter_manufacturer_id': 'TEST',
				'meter_serial_n_1': self.medidor.serie,
				'ip': '10.0.0.1',
				'puerto': '502',
				'modem': 'MOD-X',
				'estado_telemetria': 'SIN_COMUNICACION',
				'estado_stb': 'PENDIENTE',
				'sim_operador': 'Entel',
				'sim_iccid': '890123',
				'sim_abonado': '56911112222',
				'sim_estado': 'OPERATIVA',
				'estado_restriccion': '',
				'justificacion_restriccion': '',
				'ultimo_acceso': '2026-08-01',
				'ultimo_perfil_carga': 'OK',
				'ultimo_perfil_instrumentacion': 'OK',
				'ultimo_reset': '2026-07-01',
				'ultimo_registro_facturacion': '2026-07-15',
				'fecha_registro': '2026-01-10',
				'trabajo': 'Revision',
				'note': 'Nota ficha',
				'ajax': '1',
			},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
			HTTP_ACCEPT='application/json',
		)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data['success'])
		cliente.refresh_from_db()
		self.assertEqual(cliente.direccion, 'Dir Nueva')
		self.assertEqual(cliente.city, 'Santiago')
		self.assertEqual(cliente.empresa, 'Delco')
		self.assertEqual(cliente.referencia, 'Puerta azul')
		self.assertEqual(cliente.estado_telemetria, 'SIN_COMUNICACION')
		self.assertEqual(cliente.estado_stb, 'PENDIENTE')
		self.assertEqual(cliente.sim_operador, 'Entel')
		self.assertEqual(cliente.sim_iccid, '890123')
		self.assertEqual(cliente.sim_estado, 'OPERATIVA')
		self.assertEqual(cliente.trabajo, 'Revision')
		self.assertEqual(cliente.note, 'Nota ficha')
		self.assertEqual(str(cliente.fecha_registro), '2026-01-10')

		from web.models import AuditLog
		from web.services.audit_labels import label_campo

		logs = AuditLog.objects.filter(
			entity='Cliente',
			entity_id=str(cliente.pk),
			action='CLIENT_UPDATE',
		)
		self.assertTrue(logs.exists())
		campos = set(logs.values_list('field_name', flat=True))
		for esperado in ('direccion', 'empresa', 'note', 'estado_telemetria', 'sim_iccid', 'trabajo'):
			self.assertIn(esperado, campos)
		self.assertEqual(label_campo('direccion'), 'Dirección base')
		self.assertEqual(label_campo('sim_iccid'), 'SIM ICCID')

		hist = self.client.get(reverse('cliente_historial', kwargs={'pk': cliente.pk}))
		self.assertEqual(hist.status_code, 200)
		html = hist.content.decode()
		self.assertIn('Cambios de datos de la ficha', html)
		self.assertIn('Dirección base', html)
		self.assertIn('Dir Nueva', html)

	def test_get_editar_redirige_al_historial(self):
		cliente = Cliente.objects.create(
			numero_cliente='CLI-REDIR',
			direccion='Dir',
			comuna='Santiago',
			meter_serial_n_1=self.medidor_alt.serie,
			medidor_actual=self.medidor_alt,
			activo=True,
		)
		response = self.client.get(reverse('cliente_editar', kwargs={'pk': cliente.pk}))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('cliente_historial', kwargs={'pk': cliente.pk}))


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class ClienteAdjuntoHistorialTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='55555555-5',
			email='adjunto_admin@delco.cl',
			password=self.password,
			nombre='Adj',
			apellido='Admin',
			nombre_interno='adj_admin',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.admin_op = Usuario.objects.create_user(
			rut='66666666-6',
			email='adjunto_op@delco.cl',
			password=self.password,
			nombre='Adj',
			apellido='Op',
			nombre_interno='adj_op',
			rol='ADMINISTRATIVO',
			is_active=True,
		)
		self.medidor = Medidor.objects.create(
			serie='MED-ADJ-1001',
			marca='TEST',
			tipo_medidor='DIRECTO',
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-ADJ-1001',
			direccion='Dir Adj',
			comuna='Santiago',
			meter_serial_n_1=self.medidor.serie,
			medidor_actual=self.medidor,
			activo=True,
		)
		self.client = Client()
		self.png = (
			b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
			b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
			b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
		)

	def test_subir_foto_y_pdf_quedan_en_historial_y_auditoria(self):
		from web.models import AuditLog

		from .models import ClienteAdjunto

		self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
		url = reverse('cliente_historial', kwargs={'pk': self.cliente.pk})

		response = self.client.post(
			url,
			{
				'accion': 'subir_adjunto',
				'tipo': 'FOTO',
				'archivo': SimpleUploadedFile('foto_cliente.png', self.png, content_type='image/png'),
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(ClienteAdjunto.objects.filter(cliente=self.cliente, eliminado=False).count(), 1)

		pdf = SimpleUploadedFile(
			'doc_cliente.pdf',
			b'%PDF-1.4\n%demo\n',
			content_type='application/pdf',
		)
		response = self.client.post(
			url,
			{'accion': 'subir_adjunto', 'tipo': 'PDF', 'archivo': pdf},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(ClienteAdjunto.objects.filter(cliente=self.cliente, eliminado=False).count(), 2)

		hist = self.client.get(url)
		self.assertEqual(hist.status_code, 200)
		html = hist.content.decode()
		self.assertIn('foto_cliente.png', html)
		self.assertIn('doc_cliente.pdf', html)
		self.assertIn('Documentos del cliente', html)

		logs = AuditLog.objects.filter(
			entity='Cliente',
			entity_id=str(self.cliente.pk),
			action='CLIENT_ADJUNTO',
		)
		self.assertEqual(logs.count(), 2)
		nombres = set(logs.values_list('new_value', flat=True))
		self.assertIn('foto_cliente.png', nombres)
		self.assertIn('doc_cliente.pdf', nombres)
		self.assertContains(hist, 'Cliente — Adjunto subido')

	def test_reemplazar_papelera_recuperar_y_borrar_definitivo(self):
		from web.models import AuditLog

		from .models import ClienteAdjunto

		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		url = reverse('cliente_historial', kwargs={'pk': self.cliente.pk})

		self.client.post(
			url,
			{
				'accion': 'subir_adjunto',
				'tipo': 'FOTO',
				'archivo': SimpleUploadedFile('malo.png', self.png, content_type='image/png'),
			},
		)
		adj = ClienteAdjunto.objects.get(cliente=self.cliente, eliminado=False)
		self.assertEqual(adj.nombre_archivo, 'malo.png')

		response = self.client.post(
			url,
			{
				'accion': 'reemplazar_adjunto',
				'adjunto_id': str(adj.pk),
				'tipo': 'FOTO',
				'archivo': SimpleUploadedFile('bueno.png', self.png, content_type='image/png'),
			},
		)
		self.assertEqual(response.status_code, 302)
		adj.refresh_from_db()
		self.assertEqual(adj.nombre_archivo, 'bueno.png')
		self.assertTrue(
			AuditLog.objects.filter(
				entity='Cliente',
				entity_id=str(self.cliente.pk),
				action='CLIENT_ADJUNTO_REPLACE',
			).exists()
		)

		response = self.client.post(
			url,
			{'accion': 'papelera_adjunto', 'adjunto_id': str(adj.pk)},
		)
		self.assertEqual(response.status_code, 302)
		adj.refresh_from_db()
		self.assertTrue(adj.eliminado)

		response = self.client.post(
			url,
			{'accion': 'recuperar_adjunto', 'adjunto_id': str(adj.pk)},
		)
		self.assertEqual(response.status_code, 302)
		adj.refresh_from_db()
		self.assertFalse(adj.eliminado)

		self.client.post(url, {'accion': 'papelera_adjunto', 'adjunto_id': str(adj.pk)})
		response = self.client.post(
			url,
			{'accion': 'borrar_definitivo_adjunto', 'adjunto_id': str(adj.pk)},
		)
		self.assertEqual(response.status_code, 302)
		self.assertFalse(ClienteAdjunto.objects.filter(pk=adj.pk).exists())
		self.assertTrue(
			AuditLog.objects.filter(
				entity='Cliente',
				entity_id=str(self.cliente.pk),
				action='CLIENT_ADJUNTO_PURGE',
			).exists()
		)


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


class ClienteSci4SyncTests(TestCase):
	"""2.1 — Estado SCi4 y alerta por cambios críticos."""

	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='91919191-9',
			email='admin_sci4@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Sci4',
			nombre_interno='admin_sci4',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.medidor_a = Medidor.objects.create(serie='SCI4-MED-A', marca='TEST', tipo_medidor='DIRECTO')
		self.medidor_b = Medidor.objects.create(serie='SCI4-MED-B', marca='TEST', tipo_medidor='DIRECTO')
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-SCI4-001',
			direccion='Dir Sci4',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Sci4',
			installation_address='Inst Sci4',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SCI4-MED-A',
			medidor_actual=self.medidor_a,
			ip='10.10.10.10',
			modem='MOD-OLD',
			estado_sci4='ACTUALIZADO',
			activo=True,
		)
		self.client = Client()
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))

	def test_cambio_serie_marca_pendiente_sci4(self):
		response = self.client.post(
			reverse('cliente_editar', kwargs={'pk': self.cliente.pk}),
			{
				'numero_cliente': self.cliente.numero_cliente,
				'sector': self.cliente.sector,
				'tipo_suministro': self.cliente.tipo_suministro,
				'comuna': self.cliente.comuna,
				'customer_name': self.cliente.customer_name,
				'installation_address': self.cliente.installation_address,
				'proyecto': '',
				'meter_manufacturer_id': 'TEST',
				'meter_serial_n_1': 'SCI4-MED-B',
				'ip': '10.10.10.10',
				'puerto': '',
				'modem': 'MOD-OLD',
				'estado_restriccion': '',
				'justificacion_restriccion': '',
				'ajax': '1',
			},
			HTTP_X_REQUESTED_WITH='XMLHttpRequest',
			HTTP_ACCEPT='application/json',
		)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data['success'])
		self.assertTrue(data.get('sci4_marcado'))
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.estado_sci4, 'PENDIENTE')
		self.assertEqual(self.cliente.meter_serial_n_1, 'SCI4-MED-B')

	def test_marcar_sci4_actualizado(self):
		self.cliente.estado_sci4 = 'PENDIENTE'
		self.cliente.save(update_fields=['estado_sci4'])
		response = self.client.post(
			reverse('cliente_marcar_sci4_actualizado', kwargs={'pk': self.cliente.pk}),
			{'motivo': 'Revisado en SCi4'},
		)
		self.assertEqual(response.status_code, 302)
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.estado_sci4, 'ACTUALIZADO')

	def test_helper_cambio_ip(self):
		from clientes.sci4 import aplicar_pendiente_si_cambio_critico
		before = {'ip': '10.10.10.10', 'modem': 'MOD-OLD', 'meter_serial_n_1': 'SCI4-MED-A'}
		after = {'ip': '10.10.10.99', 'modem': 'MOD-OLD', 'meter_serial_n_1': 'SCI4-MED-A'}
		marcado, campos = aplicar_pendiente_si_cambio_critico(
			self.cliente, before, after, actor_id=self.admin.id,
		)
		self.assertTrue(marcado)
		self.assertIn('ip', campos)
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.estado_sci4, 'PENDIENTE')

	def test_ot_cambio_equipo_marca_sci4_pendiente(self):
		from ordenes_trabajo.models import OrdenTrabajo
		from ordenes_trabajo.sync import sincronizar_orden_completa

		self.cliente.estado_sci4 = 'ACTUALIZADO'
		self.cliente.meter_serial_n_1 = 'SCI4-MED-A'
		self.cliente.save(update_fields=['estado_sci4', 'meter_serial_n_1'])

		orden = OrdenTrabajo.objects.create(
			titulo='OT Cambio Sci4',
			descripcion='Reemplazo medidor',
			tipo_trabajo='CAMBIO',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=None,
			estado='EN_EJECUCION',
			medidor=self.medidor_b,
		)
		result = sincronizar_orden_completa(orden, self.admin, 'VALIDADA')
		self.assertTrue(result.get('sci4_alerta'))
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.estado_sci4, 'PENDIENTE')
		self.assertEqual(self.cliente.meter_serial_n_1, 'SCI4-MED-B')

	def test_ot_inspeccion_no_alerta_sci4(self):
		from ordenes_trabajo.models import OrdenTrabajo
		from ordenes_trabajo.sync import sincronizar_orden_completa

		self.cliente.estado_sci4 = 'ACTUALIZADO'
		self.cliente.save(update_fields=['estado_sci4'])
		orden = OrdenTrabajo.objects.create(
			titulo='OT Inspeccion Sci4',
			descripcion='Sin cambio equipo',
			tipo_trabajo='INSPECCION',
			cliente=self.cliente,
			creada_por=self.admin,
			estado='EN_EJECUCION',
			medidor=self.medidor_b,
		)
		result = sincronizar_orden_completa(orden, self.admin, 'VALIDADA')
		self.assertFalse(result.get('sci4_alerta'))
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.estado_sci4, 'ACTUALIZADO')
