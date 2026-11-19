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


class MoreAppApiIngestTests(TestCase):
	def test_extractor_telemetria_sin_v3_en_el_nombre(self):
		from integraciones.reader import _extraer_datos_normalizados, _resolver_formulario

		self.assertEqual(_resolver_formulario('Mantenimiento Telemetría'), 'MANTENIMIENTO_TELEMETRIA_V3')
		datos = _extraer_datos_normalizados({
			'id': 'sub-tel-1',
			'info': {'formName': 'Mantenimiento Telemetría', 'date': '2026-11-02T12:00:00.000Z'},
			'meta': {},
			'data': {
				'cliente': '12345',
				'estado': 'EJECUTADO',
				'diagnostico': {'name': 'MEDIDOR'},
				'tipoDeIncidencia': 'CAMBIO',
				'tecnicoResponsable': {'nombres': 'Juan Perez'},
			},
		})
		self.assertEqual(datos['cliente_codigo'], '12345')
		self.assertEqual(datos['estado'], 'EJECUTADO')
		self.assertEqual(datos['diagnostico'], 'MEDIDOR')
		self.assertEqual(datos['tecnico_responsable'], 'Juan Perez')

	def test_extractor_location_texto_no_rompe_ingesta(self):
		from integraciones.reader import _extraer_datos_normalizados

		datos = _extraer_datos_normalizados({
			'info': {'formName': 'Visita generica'},
			'meta': {},
			'data': {
				'cliente': '555',
				'location': 'Santiago Centro',
				'tecnicoResponsable': 'Ana Soto',
			},
		})
		self.assertEqual(datos['location'], 'Santiago Centro')
		self.assertEqual(datos['cliente_codigo'], '555')
		self.assertEqual(datos['tecnico_responsable'], 'Ana Soto')

	def test_ingest_idempotente_y_sin_operativo(self):
		from integraciones.moreapp_api_ingest import ingest_submission_items

		item = {
			'id': 'api-sub-1',
			'info': {'formName': 'Mantenimiento Telemetría'},
			'data': {'cliente': '999', 'estado': 'INCIDENCIA', 'diagnostico': 'SIM'},
		}
		primero = ingest_submission_items([item], form_name='Mantenimiento Telemetría', aplicar_operativo=False)
		segundo = ingest_submission_items([item], form_name='Mantenimiento Telemetría', aplicar_operativo=False)
		self.assertEqual(primero['nuevos'], 1)
		self.assertEqual(segundo['nuevos'], 0)
		registro = IntegracionMoreApp.objects.get(moreapp_submission_id='api-sub-1')
		self.assertEqual(registro.estado_sincronizacion, 'PROCESADO')
		self.assertEqual(registro.datos_procesados.get('estado'), 'INCIDENCIA')
		self.assertEqual(registro.datos_procesados.get('diagnostico'), 'SIM')
		self.assertFalse(registro.actualizo_cliente)
		self.assertEqual(registro.estado_revision, 'PENDIENTE')


class MoreAppValidacionAdministrativaTests(TestCase):
	"""Un informe que llega queda pendiente hasta que un administrativo lo valide."""

	def test_payload_nuevo_no_queda_revisado(self):
		resultado = procesar_payload_moreapp(_payload_minimo('sub-validar-1'), ruta_context='webhook-test')
		self.assertEqual(resultado['resultado'], 'nuevo')
		registro = IntegracionMoreApp.objects.get(moreapp_submission_id='sub-validar-1')
		self.assertEqual(registro.estado_revision, 'PENDIENTE')

	def test_ingesta_sin_operativo_conserva_advertencia_en_estado(self):
		from unittest import mock
		payload = _payload_minimo('sub-alerta-sin-op')
		with mock.patch('integraciones.reader._detectar_alerta_doble_trabajo', return_value=(True, 'Doble trabajo de prueba')):
			procesar_payload_moreapp(payload, ruta_context='api', aplicar_operativo=False)
		registro = IntegracionMoreApp.objects.get(moreapp_submission_id='sub-alerta-sin-op')
		self.assertTrue(registro.alerta_doble_trabajo)
		self.assertEqual(registro.estado_revision, 'CON_ADVERTENCIA')

	def test_bloqueo_sin_pendiente_no_baja_a_limpio(self):
		from integraciones.reader import _estado_revision_tras_llegada
		registro = IntegracionMoreApp.objects.create(
			moreapp_submission_id='sub-bloqueo-vacio',
			estado_sincronizacion='PROCESADO',
			estado_revision='CON_ADVERTENCIA',
			alerta_doble_trabajo=False,
			descripcion_alerta='BLOQUEO_OPERATIVO | MODEM: sin medidor',
			datos_recibidos={'id': 'sub-bloqueo-vacio', 'info': {}, 'data': {}},
			datos_procesados={},
		)
		_estado_revision_tras_llegada(registro, {'pendientes_revision': []})
		self.assertEqual(registro.estado_revision, 'CON_ADVERTENCIA')

	def test_reproceso_no_reabre_un_informe_ya_validado(self):
		procesar_payload_moreapp(_payload_minimo('sub-validar-2'), ruta_context='webhook-test')
		registro = IntegracionMoreApp.objects.get(moreapp_submission_id='sub-validar-2')
		registro.estado_revision = 'REVISADO'
		registro.save(update_fields=['estado_revision'])

		procesar_payload_moreapp(_payload_minimo('sub-validar-2'), ruta_context='webhook-test')
		registro.refresh_from_db()
		self.assertEqual(registro.estado_revision, 'REVISADO')
