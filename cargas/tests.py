from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from clientes.models import Cliente
from ordenes_trabajo.models import OrdenTrabajo
from usuarios.models import Usuario

from .models import CargaAdministrativa
from .services import crear_carga, generar_desde_pendientes


class CargasAdministrativasTests(TestCase):
	"""1.3 — Cargas de trabajo administrativas."""

	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='12121212-1',
			email='admin_carga@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Carga',
			nombre_interno='admin_carga',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.admin_op = Usuario.objects.create_user(
			rut='13131313-1',
			email='admvo_carga@delco.cl',
			password=self.password,
			nombre='Admvo',
			apellido='Carga',
			nombre_interno='admvo_carga',
			rol='ADMINISTRATIVO',
			is_active=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-CARGA-001',
			direccion='Dir carga',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Carga',
			installation_address='Inst Carga',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-CARGA-001',
			estado_sci4='PENDIENTE',
			activo=True,
		)
		self.orden = OrdenTrabajo.objects.create(
			titulo='OT pendiente validacion carga',
			descripcion='Para generar carga',
			tipo_trabajo='CAMBIO',
			cliente=self.cliente,
			creada_por=self.admin,
			estado='PENDIENTE_VALIDACION',
		)
		self.client = Client()

	def test_crear_y_completar_carga(self):
		self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
		response = self.client.post(
			reverse('cargas_crear'),
			{
				'titulo': 'Revisar OT demo',
				'tipo': 'VALIDACION_OT',
				'prioridad': 'ALTA',
				'descripcion': 'Probar módulo',
				'asignado_a': str(self.admin_op.pk),
			},
		)
		self.assertEqual(response.status_code, 302)
		carga = CargaAdministrativa.objects.get(titulo='Revisar OT demo')
		self.assertEqual(carga.asignado_a_id, self.admin_op.pk)
		self.assertEqual(carga.estado, 'PENDIENTE')

		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'completar', 'observaciones': 'Listo'},
		)
		self.assertEqual(response.status_code, 302)
		carga.refresh_from_db()
		self.assertEqual(carga.estado, 'COMPLETADA')
		self.assertEqual(carga.observaciones, 'Listo')

	def test_generar_desde_pendientes(self):
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		result = generar_desde_pendientes(self.admin)
		self.assertGreaterEqual(result['creadas'], 2)
		self.assertTrue(
			CargaAdministrativa.objects.filter(tipo='VALIDACION_OT', orden=self.orden, estado='PENDIENTE').exists()
		)
		self.assertTrue(
			CargaAdministrativa.objects.filter(
				tipo='VERIFICACION_SCI4', cliente=self.cliente, estado='PENDIENTE'
			).exists()
		)
		result2 = generar_desde_pendientes(self.admin)
		self.assertEqual(result2['creadas'], 0)
		self.assertGreater(result2['omitidas'], 0)

	def test_hub_requiere_rol_admin(self):
		tecnico = Usuario.objects.create_user(
			rut='14141414-1',
			email='tec_carga@delco.cl',
			password=self.password,
			nombre='Tec',
			apellido='Carga',
			nombre_interno='tec_carga',
			rol='TECNICO',
			is_active=True,
		)
		self.assertTrue(self.client.login(rut=tecnico.rut, password=self.password))
		response = self.client.get(reverse('cargas_hub'))
		self.assertEqual(response.status_code, 403)

	def test_tomar_carga(self):
		carga = crear_carga(self.admin, titulo='Sin dueño', tipo='OTRO')
		self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'tomar'},
		)
		self.assertEqual(response.status_code, 302)
		carga.refresh_from_db()
		self.assertEqual(carga.asignado_a_id, self.admin_op.pk)
		self.assertEqual(carga.estado, 'EN_PROGRESO')

	def test_subir_adjunto_imagen_y_pdf(self):
		carga = crear_carga(
			self.admin,
			titulo='Con adjuntos',
			tipo='VERIFICACION_SCI4',
			cliente=self.cliente,
		)
		self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))

		png = (
			b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
			b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
			b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
		)
		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{
				'accion': 'subir_adjunto',
				'tipo': 'FOTO',
				'archivo': SimpleUploadedFile('captura.png', png, content_type='image/png'),
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(carga.adjuntos.filter(tipo='FOTO').count(), 1)

		pdf = SimpleUploadedFile(
			'moreapp.pdf',
			b'%PDF-1.4\n%demo\n',
			content_type='application/pdf',
		)
		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{
				'accion': 'subir_adjunto',
				'tipo': 'MOREAPP',
				'archivo': pdf,
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(carga.adjuntos.count(), 2)
		self.assertTrue(carga.adjuntos.filter(tipo='MOREAPP').exists())

	def test_historial_cliente_muestra_carga_y_observaciones(self):
		carga = crear_carga(
			self.admin,
			titulo='Actualizar SCi4 cliente',
			tipo='VERIFICACION_SCI4',
			cliente=self.cliente,
			asignado_a=self.admin_op,
		)
		carga.observaciones = 'Captura de pantalla SCi4 actualizada'
		carga.save(update_fields=['observaciones'])

		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		response = self.client.get(reverse('cliente_historial', kwargs={'pk': self.cliente.pk}))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Cargas administrativas')
		self.assertContains(response, 'Actualizar SCi4 cliente')
		self.assertContains(response, 'Captura de pantalla SCi4 actualizada')
		cargas_ctx = response.context['cargas_admin']
		self.assertTrue(any(c.pk == carga.pk for c in cargas_ctx))

	def test_editar_contenido_en_carga_completada(self):
		carga = crear_carga(self.admin, titulo='Cerrada editable', tipo='OTRO', cliente=self.cliente)
		carga.estado = 'COMPLETADA'
		carga.observaciones = 'Original'
		carga.save(update_fields=['estado', 'observaciones'])

		self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'guardar_obs', 'observaciones': 'Corregido tras completar'},
		)
		self.assertEqual(response.status_code, 302)
		carga.refresh_from_db()
		self.assertEqual(carga.observaciones, 'Corregido tras completar')

		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{
				'accion': 'guardar_obs',
				'observaciones': 'Ver <b>negrita</b> y <mark>resaltado</mark><script>alert(1)</script>',
			},
		)
		self.assertEqual(response.status_code, 302)
		carga.refresh_from_db()
		self.assertIn('<b>negrita</b>', carga.observaciones)
		self.assertIn('<mark>resaltado</mark>', carga.observaciones)
		self.assertNotIn('<script>', carga.observaciones)

		detalle = self.client.get(reverse('cargas_detalle', kwargs={'pk': carga.pk}))
		self.assertEqual(detalle.status_code, 200)
		self.assertContains(detalle, 'btnCargaObsBold')
		self.assertContains(detalle, 'btnCargaObsHighlight')
		self.assertContains(detalle, 'observacionesCargaEditor')

		png = (
			b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
			b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
			b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
		)
		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{
				'accion': 'subir_adjunto',
				'tipo': 'FOTO',
				'archivo': SimpleUploadedFile('extra.png', png, content_type='image/png'),
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(carga.adjuntos.filter(eliminado=False).count(), 1)

		response = self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'reabrir'},
		)
		self.assertEqual(response.status_code, 302)
		carga.refresh_from_db()
		self.assertEqual(carga.estado, 'EN_PROGRESO')

	def test_reemplazar_papelera_recuperar_y_borrar_definitivo(self):
		from .models import AdjuntoCarga

		carga = crear_carga(self.admin, titulo='Adjuntos ciclo', tipo='OTRO', cliente=self.cliente)
		self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
		png = (
			b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
			b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
			b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
		)
		self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{
				'accion': 'subir_adjunto',
				'tipo': 'FOTO',
				'archivo': SimpleUploadedFile('malo.png', png, content_type='image/png'),
			},
		)
		adj = AdjuntoCarga.objects.get(carga=carga, eliminado=False)
		self.assertEqual(adj.nombre_archivo, 'malo.png')

		self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{
				'accion': 'reemplazar_adjunto',
				'adjunto_id': str(adj.pk),
				'tipo': 'FOTO',
				'archivo': SimpleUploadedFile('bueno.png', png, content_type='image/png'),
			},
		)
		adj.refresh_from_db()
		self.assertEqual(adj.nombre_archivo, 'bueno.png')

		self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'papelera_adjunto', 'adjunto_id': str(adj.pk)},
		)
		adj.refresh_from_db()
		self.assertTrue(adj.eliminado)

		self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'recuperar_adjunto', 'adjunto_id': str(adj.pk)},
		)
		adj.refresh_from_db()
		self.assertFalse(adj.eliminado)

		self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'papelera_adjunto', 'adjunto_id': str(adj.pk)},
		)
		# Administrativo no puede borrar definitivo
		self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'borrar_definitivo_adjunto', 'adjunto_id': str(adj.pk)},
		)
		self.assertTrue(AdjuntoCarga.objects.filter(pk=adj.pk).exists())

		self.client.logout()
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		self.client.post(
			reverse('cargas_detalle', kwargs={'pk': carga.pk}),
			{'accion': 'borrar_definitivo_adjunto', 'adjunto_id': str(adj.pk)},
		)
		self.assertFalse(AdjuntoCarga.objects.filter(pk=adj.pk).exists())
