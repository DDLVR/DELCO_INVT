from django.http import HttpResponse
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from usuarios.models import Usuario
from web.decorators import role_required
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
