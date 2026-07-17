from django.test import TestCase
from django.utils import timezone

from ordenes_trabajo.models import IntegracionMoreApp

from .reader import procesar_payload_moreapp


def _payload_minimo(submission_id='sub-soft-del-1'):
	return {
		'id': submission_id,
		'info': {'formName': 'Form Test Soft Delete'},
		'meta': {},
		'data': {},
	}


class MoreAppSoftDeleteSyncSkipTests(TestCase):
	"""Sync/webhook no debe reprocesar ni recrear submissions soft-deleted."""

	def test_webhook_omite_submission_soft_deleted(self):
		submission_id = 'soft-del-webhook-1'
		registro = IntegracionMoreApp.objects.create(
			moreapp_submission_id=submission_id,
			estado_sincronizacion='PROCESADO',
			estado_revision='REVISADO',
			datos_recibidos={'id': submission_id},
			datos_procesados={'antes': True},
			eliminado=True,
			fecha_eliminacion=timezone.now(),
		)
		total_antes = IntegracionMoreApp.objects.count()

		resultado = procesar_payload_moreapp(_payload_minimo(submission_id), ruta_context='webhook-test')

		self.assertEqual(resultado['resultado'], 'eliminado')
		self.assertEqual(IntegracionMoreApp.objects.count(), total_antes)
		registro.refresh_from_db()
		self.assertTrue(registro.eliminado)
		self.assertEqual(registro.datos_procesados, {'antes': True})
		self.assertEqual(registro.estado_revision, 'REVISADO')

	def test_folder_sync_omite_submission_soft_deleted(self):
		from .reader import _procesar_json
		import json
		import tempfile
		import os

		submission_id = 'soft-del-folder-1'
		IntegracionMoreApp.objects.create(
			moreapp_submission_id=submission_id,
			estado_sincronizacion='PROCESADO',
			datos_recibidos={},
			datos_procesados={},
			eliminado=True,
			fecha_eliminacion=timezone.now(),
		)
		payload = _payload_minimo(submission_id)
		with tempfile.TemporaryDirectory() as tmp:
			json_path = os.path.join(tmp, 'registration.json')
			with open(json_path, 'w', encoding='utf-8') as fh:
				json.dump(payload, fh)
			resultado = _procesar_json(
				json_path=json_path,
				ruta_carpeta=tmp,
				numero_correlativo=1,
				dry_run=False,
				reprocesar_duplicados=True,
			)

		self.assertEqual(resultado['resultado'], 'eliminado')
		self.assertEqual(
			IntegracionMoreApp.objects.filter(moreapp_submission_id=submission_id).count(),
			1,
		)
		existente = IntegracionMoreApp.objects.get(moreapp_submission_id=submission_id)
		self.assertTrue(existente.eliminado)
