from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from usuarios.models import Usuario
from web.context_processors import _safe_reverse, delco_api_urls, _mtime_version, delco_static_version
from web.static_sync import sincronizar_css_fuente_a_staticfiles


class DelcoApiUrlsProcessorTests(SimpleTestCase):
	def test_safe_reverse_usa_fallback_si_falta_el_name(self):
		with patch('web.context_processors.reverse', side_effect=NoReverseMatch('missing')):
			self.assertEqual(
				_safe_reverse('api_buscar_tecnicos'),
				'/api/buscar-tecnicos/',
			)
			self.assertEqual(
				_safe_reverse('api_buscar_clientes'),
				'/api/buscar-clientes/',
			)

	def test_context_processor_siempre_expone_claves(self):
		request = RequestFactory().get('/ordenes/')
		with patch('web.context_processors.reverse', side_effect=NoReverseMatch('missing')):
			ctx = delco_api_urls(request)
		api = ctx['delco_api']
		self.assertEqual(api['buscar_tecnicos'], '/api/buscar-tecnicos/')
		self.assertEqual(api['buscar_clientes'], '/api/buscar-clientes/')
		self.assertEqual(api['buscar_medidores'], '/api/buscar-medidores/')
		self.assertEqual(api['clientes_modificar_masivo'], '/clientes/modificar-masivo/')


class DelcoStaticVersionTests(SimpleTestCase):
	def test_mtime_version_de_app_css(self):
		version = _mtime_version('css/app.css')
		self.assertTrue(version.isdigit())
		self.assertNotEqual(version, '1')

	def test_context_expone_delco_css_v(self):
		request = RequestFactory().get('/')
		ctx = delco_static_version(request)
		self.assertIn('delco_css_v', ctx)
		self.assertTrue(str(ctx['delco_css_v']).isdigit())

	def test_app_css_oculta_input_nativo_del_dropzone(self):
		css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
		self.assertIn('.delco-import-file-zone input[type="file"]', css)
		self.assertIn('opacity: 0', css)
		self.assertIn('.delco-import-mode-grid', css)
		self.assertIn('@media (max-width: 575.98px)', css)


class DelcoCssSyncTests(SimpleTestCase):
	def test_copia_css_y_elimina_gzip_stale(self):
		with TemporaryDirectory() as tmp:
			base = Path(tmp)
			src = base / 'static' / 'css'
			dest = base / 'staticfiles' / 'css'
			src.mkdir(parents=True)
			dest.mkdir(parents=True)
			(src / 'app.css').write_text('.delco-import-file-zone { }', encoding='utf-8')
			(dest / 'app.css').write_text('/* stale */', encoding='utf-8')
			(dest / 'app.css.gz').write_bytes(b'stale-gz')
			(dest / 'app.css.br').write_bytes(b'stale-br')
			copiados = sincronizar_css_fuente_a_staticfiles(base)
			self.assertEqual(copiados, 1)
			self.assertIn('.delco-import-file-zone', (dest / 'app.css').read_text(encoding='utf-8'))
			self.assertFalse((dest / 'app.css.gz').exists())
			self.assertFalse((dest / 'app.css.br').exists())


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class DelcoApiUrlsIntegrationTests(TestCase):
	def test_names_registrados_coinciden_con_fallback(self):
		self.assertEqual(reverse('api_buscar_tecnicos'), '/api/buscar-tecnicos/')
		self.assertEqual(reverse('api_buscar_clientes'), '/api/buscar-clientes/')
		self.assertEqual(reverse('api_buscar_medidores'), '/api/buscar-medidores/')


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class DelcoCssCacheBustIntegrationTests(TestCase):
	def test_html_incluye_query_version_css_y_dropzone(self):
		admin = Usuario.objects.create_user(
			rut='80808080-8',
			email='css_cachebust@delco.cl',
			password='admin1234',
			nombre='Css',
			apellido='Cache',
			nombre_interno='css_cachebust',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.client.force_login(admin)
		res = self.client.get('/clientes/')
		self.assertEqual(res.status_code, 200)
		html = res.content.decode()
		self.assertRegex(html, r'css/app\.css\?v=\d+')
		self.assertIn('delco-import-file-zone', html)
		self.assertIn('delco-import-mode-grid', html)
