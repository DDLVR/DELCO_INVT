from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from usuarios.models import Usuario

from .models import OrdenTrabajo
from .views import _queryset_ordenes_filtrado


class OrdenesRolesTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='10101010-1',
			email='admin_roles@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Roles',
			nombre_interno='admin_roles',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.administrativo = Usuario.objects.create_user(
			rut='20202020-2',
			email='admvo_roles@delco.cl',
			password=self.password,
			nombre='Admvo',
			apellido='Roles',
			nombre_interno='admvo_roles',
			rol='ADMINISTRATIVO',
			is_active=True,
			is_staff=True,
		)
		self.tecnico_1 = Usuario.objects.create_user(
			rut='30303030-3',
			email='tec1_roles@delco.cl',
			password=self.password,
			nombre='Tec1',
			apellido='Roles',
			nombre_interno='tec1_roles',
			rol='TECNICO',
			is_active=True,
		)
		self.tecnico_2 = Usuario.objects.create_user(
			rut='40404040-4',
			email='tec2_roles@delco.cl',
			password=self.password,
			nombre='Tec2',
			apellido='Roles',
			nombre_interno='tec2_roles',
			rol='TECNICO',
			is_active=True,
		)
		self.gerencia = Usuario.objects.create_user(
			rut='50505050-5',
			email='gerencia_roles@delco.cl',
			password=self.password,
			nombre='Gerencia',
			apellido='Roles',
			nombre_interno='gerencia_roles',
			rol='GERENCIA',
			is_active=True,
		)
		self.auditor = Usuario.objects.create_user(
			rut='60606060-6',
			email='auditor_roles@delco.cl',
			password=self.password,
			nombre='Auditor',
			apellido='Roles',
			nombre_interno='auditor_roles',
			rol='AUDITOR',
			is_active=True,
		)
		self.client = Client()
		self.request_factory = RequestFactory()

	def _payload_crear(self, titulo='OT test rol'):
		return {
			'titulo': titulo,
			'descripcion': 'Prueba de permisos por rol',
			'tipo_trabajo': 'INSTALACION',
		}

	def test_admin_y_administrativo_pueden_crear_orden(self):
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		resp_admin = self.client.post(reverse('orden_crear'), self._payload_crear('OT admin'))
		self.assertEqual(resp_admin.status_code, 302)

		self.client.logout()
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		resp_admvo = self.client.post(reverse('orden_crear'), self._payload_crear('OT admvo'))
		self.assertEqual(resp_admvo.status_code, 302)

		self.assertEqual(OrdenTrabajo.objects.count(), 2)

	def test_tecnico_gerencia_y_auditor_no_pueden_crear_orden(self):
		for user in [self.tecnico_1, self.gerencia, self.auditor]:
			self.client.logout()
			self.assertTrue(self.client.login(rut=user.rut, password=self.password))
			response = self.client.post(reverse('orden_crear'), self._payload_crear(f'OT {user.rol}'))
			self.assertEqual(response.status_code, 302)

		self.assertEqual(OrdenTrabajo.objects.count(), 0)

	def test_auditor_equivale_supervisor_para_validar_estado(self):
		orden = OrdenTrabajo.objects.create(
			titulo='OT validacion auditor',
			descripcion='Validar rol auditor como supervisor',
			tipo_trabajo='INSPECCION',
			creada_por=self.admin,
			estado='PENDIENTE_VALIDACION',
		)

		self.assertTrue(orden.puede_cambiar_estado(self.auditor, 'VALIDADA'))
		self.assertTrue(orden.puede_cambiar_estado(self.auditor, 'OBSERVADA'))
		self.assertFalse(orden.puede_cambiar_estado(self.auditor, 'ASIGNADA'))

	def test_listado_filtra_por_rol_correctamente(self):
		orden_t1 = OrdenTrabajo.objects.create(
			titulo='OT tecnico 1',
			creada_por=self.admin,
			tecnico_responsable=self.tecnico_1,
			estado='ASIGNADA',
		)
		orden_t2 = OrdenTrabajo.objects.create(
			titulo='OT tecnico 2',
			creada_por=self.admin,
			tecnico_responsable=self.tecnico_2,
			estado='ASIGNADA',
		)

		req_admin = self.request_factory.get('/ordenes/')
		req_admin.user = self.admin
		qs_admin = _queryset_ordenes_filtrado(req_admin, aplicar_filtros=False)
		self.assertEqual(set(qs_admin.values_list('id', flat=True)), {orden_t1.id, orden_t2.id})

		req_tec = self.request_factory.get('/ordenes/')
		req_tec.user = self.tecnico_1
		qs_tec = _queryset_ordenes_filtrado(req_tec, aplicar_filtros=False)
		self.assertEqual(set(qs_tec.values_list('id', flat=True)), {orden_t1.id})

		req_aud = self.request_factory.get('/ordenes/')
		req_aud.user = self.auditor
		qs_aud = _queryset_ordenes_filtrado(req_aud, aplicar_filtros=False)
		self.assertEqual(set(qs_aud.values_list('id', flat=True)), {orden_t1.id, orden_t2.id})


class OrdenesValidacionesTests(TestCase):
	def setUp(self):
		self.admin = Usuario.objects.create_user(
			rut='70707070-7',
			email='admin_val@delco.cl',
			password='admin1234',
			nombre='Admin',
			apellido='Val',
			nombre_interno='admin_val',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.cliente = __import__('clientes.models', fromlist=['Cliente']).Cliente.objects.create(
			numero_cliente='CLI-VAL-1',
			direccion='Calle 1',
			comuna='Santiago',
			note='Cliente cerrado reiteradamente',
		)

	def test_evaluar_alertas_ot_abierta_y_antecedentes(self):
		from ordenes_trabajo.services import evaluar_alertas_ot

		OrdenTrabajo.objects.create(
			titulo='OT abierta',
			creada_por=self.admin,
			cliente=self.cliente,
			estado='ASIGNADA',
		)

		result = evaluar_alertas_ot(
			cliente=self.cliente,
			titulo='OT nueva',
			tipo_trabajo='INSTALACION',
		)
		mensajes = ' '.join(result.warnings)
		self.assertIn('OT abierta', mensajes)
		self.assertIn('cerrado', mensajes.lower())

	def test_aplicar_alertas_operativas_persiste_en_orden(self):
		from ordenes_trabajo.services import aplicar_alertas_operativas

		orden = OrdenTrabajo.objects.create(
			titulo='OT alerta',
			creada_por=self.admin,
			cliente=self.cliente,
			estado='CREADA',
		)
		aplicar_alertas_operativas(orden)
		orden.refresh_from_db()
		self.assertTrue(orden.alerta_duplicado)
		self.assertTrue(orden.descripcion_alerta_duplicado)
