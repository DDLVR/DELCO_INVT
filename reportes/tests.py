from django.test import Client, TestCase
from django.urls import reverse

from usuarios.models import Usuario


class ReportesPunto9Tests(TestCase):
    def setUp(self):
        self.password = 'admin1234'
        self.admin = Usuario.objects.create_user(
            rut='96969696-6',
            email='admin_rep@delco.cl',
            password=self.password,
            nombre='Admin',
            apellido='Rep',
            nombre_interno='admin_rep',
            rol='ADMIN',
            is_active=True,
            is_staff=True,
        )
        self.client = Client()
        self.client.login(rut=self.admin.rut, password=self.password)

    def test_hub_reportes_accesible(self):
        from django.test import RequestFactory
        from reportes.views import reportes_hub_view

        request = RequestFactory().get('/reportes/')
        request.user = self.admin
        response = reportes_hub_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Base completa de clientes', response.content.decode())

    def test_export_clientes_completos_excel(self):
        response = self.client.get(reverse('reportes_export', kwargs={'slug': 'clientes_completos'}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_export_slug_invalido(self):
        response = self.client.get('/reportes/exportar/no-existe/')
        self.assertEqual(response.status_code, 400)
