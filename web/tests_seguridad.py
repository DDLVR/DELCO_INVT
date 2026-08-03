# coding: utf-8
"""Tests de endurecimiento de seguridad de datos."""

import os
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from config.env_utils import require_env


Usuario = get_user_model()


@override_settings(MOREAPP_WEBHOOK_SECRET='test-webhook-secret')
class WebhookSeguridadTests(TestCase):
	def test_webhook_sin_secreto_responde_403(self):
		resp = self.client.post(
			reverse('movimientos_webhook_moreapp'),
			data='{}',
			content_type='application/json',
		)
		self.assertEqual(resp.status_code, 403)

	def test_webhook_con_secreto_invalido_responde_403(self):
		resp = self.client.post(
			reverse('movimientos_webhook_moreapp'),
			data='{}',
			content_type='application/json',
			HTTP_X_MOREAPP_SECRET='wrong',
		)
		self.assertEqual(resp.status_code, 403)

	def test_webhook_con_secreto_valido_pasa_auth(self):
		resp = self.client.post(
			reverse('movimientos_webhook_moreapp'),
			data='{"tipo":"NO_EXISTE"}',
			content_type='application/json',
			HTTP_X_MOREAPP_SECRET='test-webhook-secret',
		)
		# Auth OK: no 403. Payload inválido → 400 (legacy) de negocio.
		self.assertNotEqual(resp.status_code, 403)
		self.assertEqual(resp.status_code, 400)

	@override_settings(MOREAPP_WEBHOOK_SECRET='')
	def test_webhook_sin_config_responde_403(self):
		resp = self.client.post(
			reverse('movimientos_webhook_moreapp'),
			data='{}',
			content_type='application/json',
			HTTP_X_MOREAPP_SECRET='anything',
		)
		self.assertEqual(resp.status_code, 403)


@override_settings(MOREAPP_WEBHOOK_SECRET='test-webhook-secret')
class LegacyWebhookSeguridadTests(TestCase):
	def test_legacy_sin_secreto_403(self):
		resp = self.client.post(
			reverse('webhook_moreapp'),
			data='{}',
			content_type='application/json',
		)
		self.assertEqual(resp.status_code, 403)

	def test_legacy_con_secreto_410(self):
		resp = self.client.post(
			reverse('webhook_moreapp'),
			data='{}',
			content_type='application/json',
			HTTP_X_MOREAPP_SECRET='test-webhook-secret',
		)
		self.assertEqual(resp.status_code, 410)


class MediaProtegidaTests(TestCase):
	def setUp(self):
		self.password = 'Seguro1234'
		self.user = Usuario.objects.create_user(
			rut='11111111-1',
			email='media@delco.cl',
			password=self.password,
			nombre='Media',
			apellido='Test',
			nombre_interno='media_test',
			rol='ADMIN',
			is_active=True,
		)
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.media_root = Path(self.tmp.name)
		(self.media_root / 'privado.txt').write_text('dato-privado', encoding='utf-8')

	def test_media_anonimo_redirige_a_login(self):
		with override_settings(MEDIA_ROOT=str(self.media_root)):
			resp = self.client.get('/media/privado.txt')
		self.assertEqual(resp.status_code, 302)
		self.assertIn('/login', resp.url)

	def test_media_autenticado_sirve_archivo(self):
		self.client.login(username=self.user.rut, password=self.password)
		with override_settings(MEDIA_ROOT=str(self.media_root)):
			resp = self.client.get('/media/privado.txt')
		self.assertEqual(resp.status_code, 200)
		body = b''.join(resp.streaming_content)
		self.assertEqual(body, b'dato-privado')


class ClientesExportRolTests(TestCase):
	def setUp(self):
		self.password = 'Seguro1234'
		self.tecnico = Usuario.objects.create_user(
			rut='22222222-2',
			email='tec@delco.cl',
			password=self.password,
			nombre='Tec',
			apellido='Nico',
			nombre_interno='tec',
			rol='TECNICO',
			is_active=True,
		)

	def test_tecnico_no_puede_exportar_clientes(self):
		self.client.login(username=self.tecnico.rut, password=self.password)
		resp = self.client.get(reverse('clientes_exportar'))
		self.assertEqual(resp.status_code, 403)


class ProductionSettingsRequireEnvTests(TestCase):
	def test_require_env_falla_sin_variable(self):
		with mock.patch.dict(os.environ, {}, clear=True):
			with self.assertRaises(ImproperlyConfigured):
				require_env('SECRET_KEY_INEXISTENTE_XYZ')

	def test_codigo_sin_password_hardcodeado(self):
		prod = Path(__file__).resolve().parents[1] / 'config' / 'settings_production.py'
		texto = prod.read_text(encoding='utf-8')
		self.assertNotIn('Chomuske', texto)
		self.assertIn("_require_env('DB_PASSWORD')", texto)
		settings_py = Path(__file__).resolve().parents[1] / 'config' / 'settings.py'
		settings_texto = settings_py.read_text(encoding='utf-8')
		self.assertNotIn('nC1IeThyHxR1h_DoZ2f8-KG9kGB3Ca98wZPkTiilQA4=', settings_texto)
