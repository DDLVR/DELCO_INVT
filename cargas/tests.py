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
		# Segunda corrida no duplica abiertas
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
