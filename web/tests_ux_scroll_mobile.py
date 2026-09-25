"""Smoke checks de assets UX (scroll / móvil)."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from usuarios.models import Usuario


class DelcoUxAssetsTests(SimpleTestCase):
	def test_archivos_ux_existen(self):
		base = Path(settings.BASE_DIR)
		self.assertTrue((base / 'static' / 'js' / 'delco_ux.js').is_file())
		css = (base / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
		self.assertIn('.delco-back-to-top', css)
		self.assertIn('delcoPageEnter', css)
		js = (base / 'static' / 'js' / 'delco_ux.js').read_text(encoding='utf-8')
		self.assertIn('delcoBackToTop', js)
		self.assertIn('delcoMainContent', js)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class DelcoUxTemplateTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='88880001-1',
			email='ux_admin@delco.cl',
			password=self.password,
			nombre='Ux',
			apellido='Admin',
			nombre_interno='ux_admin',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)

	def test_dashboard_incluye_boton_volver_arriba_y_script(self):
		self.assertTrue(self.client.login(username=self.admin.rut, password=self.password))
		resp = self.client.get(reverse('dashboard'))
		self.assertEqual(resp.status_code, 200)
		content = resp.content.decode()
		self.assertIn('id="delcoBackToTop"', content)
		self.assertIn('delco_ux.js', content)
		self.assertIn('delcoSidebarOffcanvas', content)
