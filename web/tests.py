from django.http import HttpResponse
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from inventario.models import Medidor
from usuarios.models import Usuario
from web.decorators import role_required
from web.models import AuditLog
from web.services.audit import AuditEvent, register_audit_event
from web.views import ROLES_REPORTES_GESTION, ROLES_REPORTES_LECTURA


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class PermisosSoloLecturaAuditorTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.auditor = Usuario.objects.create_user(
			rut='70707070-7',
			email='auditor_sololectura@delco.cl',
			password=self.password,
			nombre='Auditor',
			apellido='SoloLectura',
			nombre_interno='auditor_sololectura',
			rol='AUDITOR',
			is_active=True,
		)
		self.client = Client()
		self.assertTrue(self.client.login(rut=self.auditor.rut, password=self.password))

	def test_auditor_tiene_permiso_lectura_reportes(self):
		self.assertIn('AUDITOR', ROLES_REPORTES_LECTURA)
		self.assertNotIn('AUDITOR', ROLES_REPORTES_GESTION)

	def test_auditor_no_puede_sincronizar_reportes(self):
		response = self.client.post(reverse('reportes_moreapp_sincronizar'))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('dashboard'))

	def test_auditor_no_puede_crear_orden(self):
		response = self.client.post(reverse('orden_crear'), {
			'titulo': 'OT no permitida auditor',
			'descripcion': 'Prueba de solo lectura',
			'tipo_trabajo': 'INSTALACION',
		})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('ordenes_list'))


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class MatrizRolesPunto11Tests(TestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.users = {
			'ADMIN': Usuario.objects.create_user(
				rut='80808080-8',
				email='admin_matriz@delco.cl',
				password='admin1234',
				nombre='Admin',
				apellido='Matriz',
				nombre_interno='admin_matriz',
				rol='ADMIN',
				is_active=True,
				is_staff=True,
			),
			'ADMINISTRATIVO': Usuario.objects.create_user(
				rut='81818181-1',
				email='admvo_matriz@delco.cl',
				password='admin1234',
				nombre='Admvo',
				apellido='Matriz',
				nombre_interno='admvo_matriz',
				rol='ADMINISTRATIVO',
				is_active=True,
			),
			'TECNICO': Usuario.objects.create_user(
				rut='82828282-2',
				email='tecnico_matriz@delco.cl',
				password='admin1234',
				nombre='Tecnico',
				apellido='Matriz',
				nombre_interno='tecnico_matriz',
				rol='TECNICO',
				is_active=True,
			),
			'GERENCIA': Usuario.objects.create_user(
				rut='83838383-3',
				email='gerencia_matriz@delco.cl',
				password='admin1234',
				nombre='Gerencia',
				apellido='Matriz',
				nombre_interno='gerencia_matriz',
				rol='GERENCIA',
				is_active=True,
			),
			'AUDITOR': Usuario.objects.create_user(
				rut='84848484-4',
				email='auditor_matriz@delco.cl',
				password='admin1234',
				nombre='Auditor',
				apellido='Matriz',
				nombre_interno='auditor_matriz',
				rol='AUDITOR',
				is_active=True,
			),
		}

	def _run_decorated_view(self, allowed_roles, user):
		@role_required(allowed_roles)
		def dummy_view(request):
			return HttpResponse('ok')

		request = self.factory.get('/dummy/')
		middleware = SessionMiddleware(lambda req: None)
		middleware.process_request(request)
		request.session.save()
		request._messages = FallbackStorage(request)
		request.user = user
		return dummy_view(request)

	def test_administrador_control_total_backend(self):
		response_admin = self._run_decorated_view(['ADMIN'], self.users['ADMIN'])
		self.assertEqual(response_admin.status_code, 200)

		for role in ['ADMINISTRATIVO', 'TECNICO', 'GERENCIA', 'AUDITOR']:
			resp = self._run_decorated_view(['ADMIN'], self.users[role])
			self.assertEqual(resp.status_code, 403)

	def test_analista_mapeado_a_administrativo(self):
		# Acciones tipo analista se validan sobre ADMINISTRATIVO
		resp_admvo = self._run_decorated_view(['ADMIN', 'ADMINISTRATIVO'], self.users['ADMINISTRATIVO'])
		self.assertEqual(resp_admvo.status_code, 200)

		resp_tecnico = self._run_decorated_view(['ADMIN', 'ADMINISTRATIVO'], self.users['TECNICO'])
		self.assertEqual(resp_tecnico.status_code, 403)

	def test_supervisor_y_solo_lectura_mapeados_a_auditor(self):
		# Supervisor funcional: validacion (AUDITOR habilitado)
		resp_supervisor = self._run_decorated_view(['AUDITOR', 'ADMIN', 'ADMINISTRATIVO'], self.users['AUDITOR'])
		self.assertEqual(resp_supervisor.status_code, 200)

		# Solo lectura en reportes: AUDITOR puede leer y no gestionar
		self.assertIn('AUDITOR', ROLES_REPORTES_LECTURA)
		self.assertNotIn('AUDITOR', ROLES_REPORTES_GESTION)

	def test_tecnico_solo_flujo_tecnico(self):
		resp_tecnico_ok = self._run_decorated_view(['TECNICO', 'ADMIN'], self.users['TECNICO'])
		self.assertEqual(resp_tecnico_ok.status_code, 200)

		resp_tecnico_denegado = self._run_decorated_view(['ADMIN', 'ADMINISTRATIVO'], self.users['TECNICO'])
		self.assertEqual(resp_tecnico_denegado.status_code, 403)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class AuditPersistencePunto12Tests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='85858585-5',
			email='admin_audit@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Audit',
			nombre_interno='admin_audit',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.client = Client()
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))

	def test_register_audit_event_persiste_en_db(self):
		register_audit_event(
			AuditEvent(
				actor_id=self.admin.id,
				action='TEST_AUDIT',
				entity='Dummy',
				entity_id='123',
				field_name='estado',
				old_value={'x': 1},
				new_value={'x': 2},
				reason='Prueba persistencia',
			)
		)

		log = AuditLog.objects.get(action='TEST_AUDIT', entity='Dummy', entity_id='123')
		self.assertEqual(log.actor_id, self.admin.id)
		self.assertEqual(log.field_name, 'estado')
		self.assertIn('"x": 1', log.old_value)
		self.assertIn('"x": 2', log.new_value)

	def test_crear_cliente_genera_evento_auditoria(self):
		medidor = Medidor.objects.create(
			serie='SER-AUD-001',
			marca='TEST',
			tipo_medidor='DIRECTO',
		)

		payload = {
			'numero_cliente': 'CLI-AUD-001',
			'direccion': 'Dir Audit 1',
			'comuna': 'Santiago',
			'tipo_suministro': 'ELECTRICO',
			'sector': 'CENTRO',
			'city': 'Santiago',
			'customer_name': 'Cliente Audit',
			'installation_address': 'Inst Audit 1',
			'proyecto': '',
			'meter_manufacturer_id': 'TEST',
			'meter_serial_n_1': medidor.serie,
			'ultimo_acceso': '2026-07-09',
			'ultimo_perfil_carga': '',
			'ultimo_reset': '2026-07-09',
			'ultimo_registro_facturacion': '2026-07-09',
			'note': 'nota audit',
			'ip': '10.30.30.1',
			'puerto': '',
			'modem': 'MODEM-AUD-001',
			'fecha_registro': '2026-07-09',
		}

		response = self.client.post(reverse('cliente_crear'), payload)
		self.assertEqual(response.status_code, 302)

		cliente = Cliente.objects.get(numero_cliente='CLI-AUD-001', activo=True)
		self.assertTrue(
			AuditLog.objects.filter(
				action='CLIENT_CREATE',
				entity='Cliente',
				entity_id=str(cliente.id),
			).exists()
		)
