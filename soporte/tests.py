from django.test import Client, TestCase, override_settings
from django.urls import reverse

from usuarios.models import Usuario

from .models import TicketSoporte


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class SoporteTicketsAdminOnlyTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='10101010-1',
			email='admin_soporte@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Soporte',
			nombre_interno='admin_soporte',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.administrativo = Usuario.objects.create_user(
			rut='20202020-2',
			email='adm_soporte@delco.cl',
			password=self.password,
			nombre='Adm',
			apellido='Soporte',
			nombre_interno='adm_soporte',
			rol='ADMINISTRATIVO',
			is_active=True,
		)
		self.client = Client()

	def test_admin_accede_hub_y_crea_ticket(self):
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		hub = self.client.get(reverse('soporte_hub'))
		self.assertEqual(hub.status_code, 200)
		self.assertContains(hub, 'Centro de Soporte')

		crear = self.client.post(
			reverse('soporte_crear'),
			{
				'titulo': 'Bug en validación OT',
				'descripcion': 'Al rechazar sin comentario no bloquea bien.',
				'categoria': 'BUG',
				'prioridad': 'ALTA',
				'pagina_url': '/ordenes/1/',
			},
		)
		self.assertEqual(crear.status_code, 302)
		ticket = TicketSoporte.objects.get(titulo='Bug en validación OT')
		self.assertEqual(ticket.creado_por_id, self.admin.id)
		self.assertEqual(ticket.prioridad, 'ALTA')

	def test_administrativo_no_accede(self):
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		response = self.client.get(reverse('soporte_hub'))
		self.assertEqual(response.status_code, 403)

	def test_cualquier_usuario_levanta_ticket_rapido(self):
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		response = self.client.post(
			reverse('soporte_ticket_rapido'),
			{
				'categoria': 'PROBLEMA',
				'descripcion': 'No puedo ver el inventario en móvil.',
				'pagina_url': '/inventario/',
			},
		)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data['success'])
		ticket = TicketSoporte.objects.get(pk=data['ticket_id'])
		self.assertEqual(ticket.creado_por_id, self.administrativo.id)
		self.assertEqual(ticket.categoria, 'PROBLEMA')
		self.assertIn('inventario', ticket.descripcion.lower())
