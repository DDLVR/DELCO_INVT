from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from web.context_processors import _safe_reverse, delco_api_urls


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


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class DelcoApiUrlsIntegrationTests(TestCase):
	def test_names_registrados_coinciden_con_fallback(self):
		self.assertEqual(reverse('api_buscar_tecnicos'), '/api/buscar-tecnicos/')
		self.assertEqual(reverse('api_buscar_clientes'), '/api/buscar-clientes/')
		self.assertEqual(reverse('api_buscar_medidores'), '/api/buscar-medidores/')
