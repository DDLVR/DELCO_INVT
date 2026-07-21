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


class MoreAppMovimientoTrayectoTests(TestCase):
	"""Instalación MoreApp debe mostrar Bodega→Cliente y retirar el módem anterior."""

	def setUp(self):
		from clientes.models import Cliente
		from inventario.models import EstadoInventario, Medidor, Modem, Ubicacion
		from usuarios.models import Usuario

		self.admin = Usuario.objects.create_user(
			rut='11111111-1',
			email='moreapp_mov@delco.cl',
			password='admin1234',
			nombre='More',
			apellido='App',
			nombre_interno='moreapp_sys',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.estado_bodega, _ = EstadoInventario.objects.get_or_create(nombre='En bodega')
		self.estado_instalado, _ = EstadoInventario.objects.get_or_create(nombre='Instalado')
		self.estado_retirado, _ = EstadoInventario.objects.get_or_create(nombre='Retirado')
		self.bodega, _ = Ubicacion.objects.get_or_create(
			nombre='Bodega Principal',
			defaults={'tipo': 'BODEGA_DELCO'},
		)
		self.cliente_loc, _ = Ubicacion.objects.get_or_create(
			nombre='Instalado en cliente',
			defaults={'tipo': 'CLIENTE'},
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-MOV-1',
			direccion='Dir test',
			comuna='Santiago',
			activo=True,
		)
		self.medidor = Medidor.objects.create(
			serie='MED-MOV-1',
			tipo_medidor='DIRECTO',
			estado_inventario=self.estado_instalado,
			ubicacion_actual=self.cliente_loc,
			cliente=self.cliente,
		)
		self.modem_viejo = Modem.objects.create(
			serie='MODEM-OLD-1',
			estado_inventario=self.estado_instalado,
			ubicacion_actual=self.cliente_loc,
			cliente=self.cliente,
			medidor=self.medidor,
		)
		self.modem_nuevo = Modem.objects.create(
			serie='MODEM-NEW-1',
			estado_inventario=self.estado_bodega,
			ubicacion_actual=self.bodega,
		)

	def test_instalacion_modem_origen_bodega_y_retira_anterior(self):
		from inventario.models import MovimientoItem
		from ordenes_trabajo.models import IntegracionMoreApp
		from integraciones.reader import _actualizar_equipo_operativo

		registro = IntegracionMoreApp.objects.create(
			moreapp_submission_id='mov-trayecto-1',
			estado_sincronizacion='PENDIENTE',
			datos_recibidos={},
			datos_procesados={},
		)

		ok = _actualizar_equipo_operativo(
			self.modem_nuevo,
			'MODEM',
			self.estado_instalado,
			self.cliente,
			'Actualización MoreApp (test) | submission: mov-trayecto-1 - instalación módem',
			registro,
			medidor_asociado=self.medidor,
			responsable_movimiento=self.admin,
		)
		self.assertTrue(ok)

		self.modem_nuevo.refresh_from_db()
		self.modem_viejo.refresh_from_db()

		self.assertEqual(self.modem_nuevo.estado_inventario.nombre, 'Instalado')
		self.assertEqual(self.modem_nuevo.ubicacion_actual.nombre, 'Instalado en cliente')
		self.assertEqual(self.modem_nuevo.cliente_id, self.cliente.id)

		self.assertEqual(self.modem_viejo.estado_inventario.nombre, 'Retirado')
		self.assertIsNone(self.modem_viejo.cliente_id)
		self.assertEqual(self.modem_viejo.ubicacion_actual.nombre, 'Bodega Principal')

		mov_nuevo = (
			MovimientoItem.objects.filter(modem=self.modem_nuevo, movimiento__origen_sistema='MOREAPP')
			.select_related('movimiento', 'movimiento__origen', 'movimiento__destino')
			.order_by('-id')
			.first()
		)
		self.assertIsNotNone(mov_nuevo)
		self.assertEqual(mov_nuevo.movimiento.tipo, 'INSTALACION')
		self.assertEqual(mov_nuevo.movimiento.origen.nombre, 'Bodega Principal')
		self.assertEqual(mov_nuevo.movimiento.destino.nombre, 'Instalado en cliente')
		self.assertIn('En bodega', mov_nuevo.movimiento.observacion)
		self.assertIn('Instalado', mov_nuevo.movimiento.observacion)

		mov_viejo = (
			MovimientoItem.objects.filter(modem=self.modem_viejo, movimiento__origen_sistema='MOREAPP')
			.select_related('movimiento', 'movimiento__origen', 'movimiento__destino')
			.order_by('-id')
			.first()
		)
		self.assertIsNotNone(mov_viejo)
		self.assertEqual(mov_viejo.movimiento.tipo, 'RETIRO')
		self.assertEqual(mov_viejo.movimiento.origen.nombre, 'Instalado en cliente')
		self.assertEqual(mov_viejo.movimiento.destino.nombre, 'Bodega Principal')
