from django.test import Client, TestCase
from django.urls import reverse

from catalogos.models import CatalogoDiagnostico
from usuarios.models import Usuario


class CatalogoDiagnosticoTests(TestCase):
    def setUp(self):
        self.password = 'admin1234'
        self.admin = Usuario.objects.create_user(
            rut='97979797-7',
            email='admin_cat@delco.cl',
            password=self.password,
            nombre='Admin',
            apellido='Cat',
            nombre_interno='admin_cat',
            rol='ADMIN',
            is_active=True,
            is_staff=True,
        )
        self.client = Client()
        self.client.login(rut=self.admin.rut, password=self.password)

    def test_catalogo_inicial_cargado(self):
        self.assertGreaterEqual(CatalogoDiagnostico.objects.filter(activo=True).count(), 20)

    def test_vista_catalogo_accesible(self):
        from django.test import RequestFactory
        from catalogos.views import catalogo_diagnostico_list_view

        request = RequestFactory().get('/catalogos/diagnostico/')
        request.user = self.admin
        response = catalogo_diagnostico_list_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Medidor en terreno distinto al sistema', response.content.decode())
