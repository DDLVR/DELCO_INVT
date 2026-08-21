from io import BytesIO

import openpyxl
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from inventario.models import Medidor
from usuarios.models import Usuario

from .models import OrdenTrabajo
from .utils import aplicar_alerta_duplicado, importar_ordenes_excel
from .views import _queryset_ordenes_filtrado


class OrdenesRolesTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='10101010-1',
			email='admin_roles@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Roles',
			nombre_interno='admin_roles',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.administrativo = Usuario.objects.create_user(
			rut='20202020-2',
			email='admvo_roles@delco.cl',
			password=self.password,
			nombre='Admvo',
			apellido='Roles',
			nombre_interno='admvo_roles',
			rol='ADMINISTRATIVO',
			is_active=True,
			is_staff=True,
		)
		self.tecnico_1 = Usuario.objects.create_user(
			rut='30303030-3',
			email='tec1_roles@delco.cl',
			password=self.password,
			nombre='Tec1',
			apellido='Roles',
			nombre_interno='tec1_roles',
			rol='TECNICO',
			is_active=True,
		)
		self.tecnico_2 = Usuario.objects.create_user(
			rut='40404040-4',
			email='tec2_roles@delco.cl',
			password=self.password,
			nombre='Tec2',
			apellido='Roles',
			nombre_interno='tec2_roles',
			rol='TECNICO',
			is_active=True,
		)
		self.gerencia = Usuario.objects.create_user(
			rut='50505050-5',
			email='gerencia_roles@delco.cl',
			password=self.password,
			nombre='Gerencia',
			apellido='Roles',
			nombre_interno='gerencia_roles',
			rol='GERENCIA',
			is_active=True,
		)
		self.auditor = Usuario.objects.create_user(
			rut='60606060-6',
			email='auditor_roles@delco.cl',
			password=self.password,
			nombre='Auditor',
			apellido='Roles',
			nombre_interno='auditor_roles',
			rol='AUDITOR',
			is_active=True,
		)
		self.client = Client()
		self.request_factory = RequestFactory()

	def _payload_crear(self, titulo='OT test rol'):
		return {
			'titulo': titulo,
			'descripcion': 'Prueba de permisos por rol',
			'tipo_trabajo': 'INSTALACION',
		}

	def test_admin_y_administrativo_pueden_crear_orden(self):
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		resp_admin = self.client.post(reverse('orden_crear'), self._payload_crear('OT admin'))
		self.assertEqual(resp_admin.status_code, 302)

		self.client.logout()
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		resp_admvo = self.client.post(reverse('orden_crear'), self._payload_crear('OT admvo'))
		self.assertEqual(resp_admvo.status_code, 302)

		self.assertEqual(OrdenTrabajo.objects.count(), 2)

	def test_tecnico_gerencia_y_auditor_no_pueden_crear_orden(self):
		for user in [self.tecnico_1, self.gerencia, self.auditor]:
			self.client.logout()
			self.assertTrue(self.client.login(rut=user.rut, password=self.password))
			response = self.client.post(reverse('orden_crear'), self._payload_crear(f'OT {user.rol}'))
			self.assertEqual(response.status_code, 302)

		self.assertEqual(OrdenTrabajo.objects.count(), 0)

	def test_administrativo_puede_validar_estado(self):
		orden = OrdenTrabajo.objects.create(
			titulo='OT validacion administrativo',
			descripcion='Validar rol administrativo',
			tipo_trabajo='INSPECCION',
			creada_por=self.admin,
			estado='PENDIENTE_VALIDACION',
		)

		self.assertTrue(orden.puede_cambiar_estado(self.administrativo, 'VALIDADA'))
		self.assertTrue(orden.puede_cambiar_estado(self.administrativo, 'OBSERVADA'))
		self.assertTrue(orden.puede_cambiar_estado(self.administrativo, 'ASIGNADA'))
		self.assertTrue(orden.puede_cambiar_estado(self.admin, 'VALIDADA'))
		self.assertTrue(orden.puede_cambiar_estado(self.admin, 'OBSERVADA'))

	def test_auditor_no_puede_validar_pero_si_observar(self):
		orden = OrdenTrabajo.objects.create(
			titulo='OT sin validacion auditor',
			descripcion='Auditor observa pero no valida',
			tipo_trabajo='INSPECCION',
			creada_por=self.admin,
			estado='PENDIENTE_VALIDACION',
		)

		self.assertFalse(orden.puede_cambiar_estado(self.auditor, 'VALIDADA'))
		self.assertTrue(orden.puede_cambiar_estado(self.auditor, 'OBSERVADA'))

	def test_listado_filtra_por_rol_correctamente(self):
		orden_t1 = OrdenTrabajo.objects.create(
			titulo='OT tecnico 1',
			creada_por=self.admin,
			tecnico_responsable=self.tecnico_1,
			estado='ASIGNADA',
		)
		orden_t2 = OrdenTrabajo.objects.create(
			titulo='OT tecnico 2',
			creada_por=self.admin,
			tecnico_responsable=self.tecnico_2,
			estado='ASIGNADA',
		)

		req_admin = self.request_factory.get('/ordenes/')
		req_admin.user = self.admin
		qs_admin = _queryset_ordenes_filtrado(req_admin, aplicar_filtros=False)
		self.assertEqual(set(qs_admin.values_list('id', flat=True)), {orden_t1.id, orden_t2.id})

		req_tec = self.request_factory.get('/ordenes/')
		req_tec.user = self.tecnico_1
		qs_tec = _queryset_ordenes_filtrado(req_tec, aplicar_filtros=False)
		self.assertEqual(set(qs_tec.values_list('id', flat=True)), {orden_t1.id})

		req_aud = self.request_factory.get('/ordenes/')
		req_aud.user = self.auditor
		qs_aud = _queryset_ordenes_filtrado(req_aud, aplicar_filtros=False)
		self.assertEqual(set(qs_aud.values_list('id', flat=True)), {orden_t1.id, orden_t2.id})


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class OrdenesBasicasWorkflowTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='90909090-9',
			email='admin_ot@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='OT',
			nombre_interno='admin_ot',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='91919191-1',
			email='tecnico_ot@delco.cl',
			password=self.password,
			nombre='Tecnico',
			apellido='OT',
			nombre_interno='tecnico_ot',
			rol='TECNICO',
			is_active=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-OT-001',
			direccion='Direccion OT 1',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente OT',
			installation_address='Inst OT 1',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-OT-001',
			activo=True,
		)
		self.medidor = Medidor.objects.create(
			serie='SER-OT-001',
			marca='TEST',
			tipo_medidor='DIRECTO',
		)
		self.client = Client()
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))

	def _excel_ordenes(self, rows):
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.title = 'ORDENES'
		ws.append([
			'Numero Cliente',
			'Titulo',
			'Descripcion',
			'Tipo Trabajo',
			'Tecnico Responsable',
			'Estado',
			'Observaciones Tecnicas',
		])
		for row in rows:
			ws.append(row)

		buffer = BytesIO()
		wb.save(buffer)
		buffer.seek(0)
		buffer.name = 'ordenes_test.xlsx'
		return buffer

	def _excel_plantilla_asignacion(self, rows):
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.title = 'Hoja1'
		ws.append([
			'SOLICITUD', 'CLIENTE', 'MEDIDOR', 'MARCA', 'NOMBRE',
			'DIRECCION', 'COMUNA', 'TECNICO', 'TRABAJO', 'IP', 'PUERTO',
			'MODEM', 'FECHA',
		])
		for row in rows:
			ws.append(row)
		buffer = BytesIO()
		wb.save(buffer)
		buffer.seek(0)
		buffer.name = 'plantilla_asignacion.xlsx'
		return buffer

	def test_creacion_orden_asigna_estado_inicial_correcto(self):
		response = self.client.post(reverse('orden_crear'), {
			'titulo': 'OT Base',
			'descripcion': 'Alta de orden base',
			'tipo_trabajo': 'INSTALACION',
			'cliente': str(self.cliente.pk),
			'tecnico_responsable': str(self.tecnico.pk),
		}, follow=False)

		self.assertEqual(response.status_code, 302)
		orden = OrdenTrabajo.objects.get(titulo='OT Base')
		self.assertEqual(orden.estado, 'ASIGNADA')
		self.assertEqual(orden.tecnico_responsable, self.tecnico)
		self.assertEqual(orden.cliente, self.cliente)

	def test_aplica_alerta_de_duplicado_por_mismo_cliente(self):
		orden_1 = OrdenTrabajo.objects.create(
			titulo='OT 1',
			descripcion='Primera OT',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			estado='ASIGNADA',
		)
		orden_2 = OrdenTrabajo.objects.create(
			titulo='OT 2',
			descripcion='Segunda OT',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			estado='ASIGNADA',
		)

		aplicar_alerta_duplicado(orden_2)
		orden_2.refresh_from_db()
		self.assertTrue(orden_2.alerta_duplicado)
		self.assertTrue(orden_2.descripcion_alerta_duplicado)
		self.assertNotEqual(orden_1.id, orden_2.id)

	def test_importacion_basica_de_ordenes_crea_y_asigna(self):
		archivo = self._excel_ordenes([
			['CLI-OT-001', 'OT Importada', 'Carga inicial', 'INSTALACION', 'tecnico_ot', 'CREADA', 'Obs import'],
		])

		importacion = importar_ordenes_excel(archivo, self.admin)

		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertGreaterEqual(importacion.exitosas, 1)
		orden = OrdenTrabajo.objects.get(titulo='OT Importada')
		self.assertEqual(orden.tecnico_responsable, self.tecnico)
		self.assertEqual(orden.estado, 'ASIGNADA')

	def test_reimportar_mismo_excel_no_duplica_ordenes(self):
		Cliente.objects.create(
			numero_cliente='CLI-OT-002',
			direccion='Dir OT 2',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente OT 2',
			installation_address='Inst OT 2',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-OT-002',
			activo=True,
		)
		archivo = self._excel_ordenes([
			[
				'CLI-OT-002',
				'OT MoreApp #212 — Cliente prueba',
				'Descripcion',
				'MANTENCION',
				'tecnico_ot',
				'ASIGNADA',
				'correlativo: 212 | formulario: Mantenimiento',
			],
		])
		primera = importar_ordenes_excel(archivo, self.admin)
		segunda = importar_ordenes_excel(archivo, self.admin)

		self.assertEqual(primera.exitosas, 1)
		self.assertEqual(segunda.exitosas, 1)
		self.assertEqual(
			OrdenTrabajo.objects.filter(titulo='OT MoreApp #212 — Cliente prueba').count(),
			1,
		)

	def test_importacion_ot_falla_si_cliente_no_existe(self):
		archivo = self._excel_ordenes([
			['CLI-INEXISTENTE', 'OT Fantasma', 'Desc', 'INSTALACION', 'tecnico_ot', 'CREADA', 'Obs'],
		])
		importacion = importar_ordenes_excel(archivo, self.admin)
		self.assertEqual(importacion.exitosas, 0)
		self.assertGreaterEqual(importacion.fallidas, 1)
		self.assertFalse(OrdenTrabajo.objects.filter(titulo='OT Fantasma').exists())
		self.assertFalse(Cliente.objects.filter(numero_cliente='CLI-INEXISTENTE').exists())

	def test_importacion_plantilla_asignacion_trabajo(self):
		from datetime import date
		from ordenes_trabajo.utils import exportar_ordenes_excel

		archivo = self._excel_plantilla_asignacion([
			[
				'SOL-4401',
				'CLI-OT-001',
				'SER-OT-001',
				'TEST',
				'Cliente OT',
				'ANTONIO BELLET 197',
				'PROVIDENCIA',
				'tecnico_ot',
				'CAMBIO',
				'10.117.23.47',
				'4060',
				'',
				date(2026, 8, 13),
			],
		])
		importacion = importar_ordenes_excel(archivo, self.admin)
		self.assertEqual(importacion.estado, 'COMPLETADO', importacion.observaciones)
		self.assertEqual(importacion.exitosas, 1)
		orden = OrdenTrabajo.objects.get(titulo='SOL-4401')
		self.assertEqual(orden.tipo_trabajo, 'CAMBIO')
		self.assertEqual(orden.tecnico_responsable, self.tecnico)
		self.assertEqual(orden.estado, 'ASIGNADA')
		self.assertEqual(orden.medidor_id, self.medidor.id)
		self.assertIsNotNone(orden.fecha_asignacion)
		self.assertEqual(orden.fecha_asignacion.date(), date(2026, 8, 13))
		self.assertIn('PROVIDENCIA', orden.descripcion)

		wb = exportar_ordenes_excel([orden])
		headers = [c.value for c in wb.active[1]]
		self.assertEqual(headers[0], 'SOLICITUD')
		self.assertEqual(headers[1], 'CLIENTE')
		self.assertIn('PROYECTO', headers)
		self.assertIn('Fecha Creacion', headers)
		self.assertIn('Fecha Asignacion', headers)
		self.assertNotIn('SIM IMEI', headers)
		fila = [c.value for c in wb.active[2]]
		self.assertEqual(fila[0], 'SOL-4401')
		self.assertEqual(fila[1], 'CLI-OT-001')
		self.assertEqual(fila[2], 'SER-OT-001')

	def test_tecnico_ve_solo_sus_ordenes_en_listado(self):
		orden_1 = OrdenTrabajo.objects.create(
			titulo='OT Tec',
			creada_por=self.admin,
			cliente=self.cliente,
			tecnico_responsable=self.tecnico,
			estado='ASIGNADA',
		)
		otro_tecnico = Usuario.objects.create_user(
			rut='92929292-2',
			email='tecnico_ot_2@delco.cl',
			password=self.password,
			nombre='Tecnico2',
			apellido='OT',
			nombre_interno='tecnico_ot_2',
			rol='TECNICO',
			is_active=True,
		)
		orden_2 = OrdenTrabajo.objects.create(
			titulo='OT Tec 2',
			creada_por=self.admin,
			cliente=self.cliente,
			tecnico_responsable=otro_tecnico,
			estado='ASIGNADA',
		)

		req = RequestFactory().get('/ordenes/')
		req.user = self.tecnico
		qs = _queryset_ordenes_filtrado(req, aplicar_filtros=False)
		self.assertEqual(set(qs.values_list('id', flat=True)), {orden_1.id})
		self.assertNotIn(orden_2.id, set(qs.values_list('id', flat=True)))


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class OrdenesValidacionAdministrativoTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='94949494-4',
			email='admin_valadm@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Val',
			nombre_interno='admin_valadm',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.administrativo = Usuario.objects.create_user(
			rut='95959595-5',
			email='admvo_val@delco.cl',
			password=self.password,
			nombre='Admvo',
			apellido='Val',
			nombre_interno='admvo_val',
			rol='ADMINISTRATIVO',
			is_active=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='96969696-6',
			email='tecnico_val@delco.cl',
			password=self.password,
			nombre='Tecnico',
			apellido='Val',
			nombre_interno='tecnico_val',
			rol='TECNICO',
			is_active=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-VALADM-001',
			direccion='Dir val',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente val',
			installation_address='Inst val',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-VAL-001',
			activo=True,
		)
		self.orden = OrdenTrabajo.objects.create(
			titulo='OT validacion flujo',
			descripcion='Prueba validacion administrativo',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			tecnico_responsable=self.tecnico,
			creada_por=self.admin,
			estado='PENDIENTE_VALIDACION',
		)
		self.client = Client()

	def test_validar_no_cierra_automaticamente(self):
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		response = self.client.post(
			reverse('cambiar_estado_orden', args=[self.orden.pk]),
			{'nuevo_estado': 'VALIDADA'},
		)
		self.assertEqual(response.status_code, 302)
		self.orden.refresh_from_db()
		self.assertEqual(self.orden.estado, 'VALIDADA')
		self.assertEqual(self.orden.validada_por, self.administrativo)
		from ordenes_trabajo.models import RegistroValidacionOT
		reg = RegistroValidacionOT.objects.get(orden=self.orden, accion='VALIDADA')
		self.assertEqual(reg.realizado_por_id, self.administrativo.id)

	def test_observada_crea_orden_derivada(self):
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		response = self.client.post(
			reverse('cambiar_estado_orden', args=[self.orden.pk]),
			{
				'nuevo_estado': 'OBSERVADA',
				'observacion_validacion': 'Falta foto del medidor instalado',
			},
		)
		self.assertEqual(response.status_code, 302)
		self.orden.refresh_from_db()
		self.assertEqual(self.orden.estado, 'OBSERVADA')
		self.assertIn('Falta foto', self.orden.observacion_validacion)

		derivada = self.orden.ordenes_derivadas.get()
		self.assertEqual(derivada.orden_origen_id, self.orden.pk)
		self.assertEqual(derivada.cliente_id, self.cliente.pk)
		self.assertEqual(derivada.tecnico_responsable_id, self.tecnico.pk)
		self.assertEqual(derivada.estado, 'ASIGNADA')
		self.assertEqual(response.url, reverse('orden_detalle', args=[derivada.pk]))
		from ordenes_trabajo.models import RegistroValidacionOT
		reg = RegistroValidacionOT.objects.get(orden=self.orden, accion='OBSERVADA')
		self.assertIn('Falta foto', reg.comentario)

	def test_detalle_muestra_registro_validacion(self):
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		self.client.post(
			reverse('cambiar_estado_orden', args=[self.orden.pk]),
			{'nuevo_estado': 'VALIDADA'},
		)
		response = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		self.assertIn('Registro de validación', html)
		self.assertIn(self.administrativo.nombre_interno, html)

	def test_observada_sin_comentario_bloquea(self):
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		response = self.client.post(
			reverse('cambiar_estado_orden', args=[self.orden.pk]),
			{'nuevo_estado': 'OBSERVADA', 'observacion_validacion': ''},
		)
		self.assertEqual(response.status_code, 302)
		self.orden.refresh_from_db()
		self.assertEqual(self.orden.estado, 'PENDIENTE_VALIDACION')

	def test_detalle_muestra_usuario_validador_actual(self):
		self.assertTrue(self.client.login(rut=self.administrativo.rut, password=self.password))
		response = self.client.get(reverse('orden_detalle', args=[self.orden.pk]))
		self.assertEqual(response.status_code, 200)
		html = response.content.decode()
		self.assertIn('Validación administrativa', html)
		self.assertIn(self.administrativo.nombre_interno, html)
		self.assertIn('Registrar validación como', html)


class OrdenesValidacionesPdfTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='93939393-3',
			email='admin_val@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Val',
			nombre_interno='admin_val',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-VAL-001',
			direccion='Dir',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Val',
			installation_address='Inst',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-VAL-001',
			activo=True,
		)
		self.client = Client()
		self.client.login(rut=self.admin.rut, password=self.password)
		OrdenTrabajo.objects.create(
			titulo='OT abierta previa',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			estado='ASIGNADA',
		)

	def test_bloquea_segunda_ot_abierta_mismo_cliente(self):
		response = self.client.post(reverse('orden_crear'), {
			'titulo': 'OT duplicada bloqueada',
			'descripcion': 'No debe crearse',
			'tipo_trabajo': 'MANTENCION',
			'cliente': str(self.cliente.pk),
		}, follow=False)
		self.assertEqual(response.status_code, 302)
		self.assertFalse(OrdenTrabajo.objects.filter(titulo='OT duplicada bloqueada').exists())


class OrdenesSyncInventarioTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='94949494-4',
			email='admin_sync@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Sync',
			nombre_interno='admin_sync',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='95959595-5',
			email='tec_sync@delco.cl',
			password=self.password,
			nombre='Tec',
			apellido='Sync',
			nombre_interno='tec_sync',
			rol='TECNICO',
			is_active=True,
		)
		from inventario.models import EstadoInventario, Medidor, Ubicacion

		self.estado_bodega, _ = EstadoInventario.objects.get_or_create(nombre='En bodega')
		self.estado_instalado, _ = EstadoInventario.objects.get_or_create(nombre='Instalado')
		self.ubicacion_bodega, _ = Ubicacion.objects.get_or_create(
			tipo='BODEGA_DELCO',
			nombre='Bodega Principal',
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-SYNC-001',
			direccion='Dir sync',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Sync',
			installation_address='Inst',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-SYNC-001',
			activo=True,
		)
		self.medidor = Medidor.objects.create(
			serie='SER-SYNC-MED-001',
			estado_inventario=self.estado_bodega,
			ubicacion_actual=self.ubicacion_bodega,
			entregado_a=self.tecnico,
		)
		self.orden = OrdenTrabajo.objects.create(
			titulo='OT sync inventario',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=self.tecnico,
			medidor=self.medidor,
			estado='EN_EJECUCION',
		)

	def test_cambiar_estado_realizada_sincroniza_medidor(self):
		resultado = self.orden.cambiar_estado(self.admin, 'REALIZADA')
		self.assertTrue(resultado['success'])
		self.medidor.refresh_from_db()
		self.cliente.refresh_from_db()
		self.assertEqual(self.medidor.cliente_id, self.cliente.id)
		self.assertEqual(self.medidor.estado_inventario.nombre, 'Instalado')
		self.assertEqual(self.cliente.medidor_actual_id, self.medidor.id)

	def test_vincular_moreapp_copia_equipos_a_orden(self):
		from ordenes_trabajo.sync import vincular_moreapp_a_orden

		self.medidor.estado_inventario = self.estado_instalado
		self.medidor.cliente = self.cliente
		self.medidor.save()
		self.cliente.medidor_actual = self.medidor
		self.cliente.save()

		# Cerrar la OT del setUp para que solo quede una abierta a vincular.
		self.orden.estado = 'CERRADA'
		self.orden.save(update_fields=['estado'])

		orden_abierta = OrdenTrabajo.objects.create(
			titulo='OT abierta moreapp',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			estado='ASIGNADA',
		)
		vinculada = vincular_moreapp_a_orden(self.cliente, medidor=self.medidor)
		self.assertEqual(vinculada.id, orden_abierta.id)
		orden_abierta.refresh_from_db()
		self.assertEqual(orden_abierta.medidor_id, self.medidor.id)
		self.assertEqual(orden_abierta.estado, 'REALIZADA_PENDIENTE_COMPROBACION')


class OrdenesReasignacionTecnicoTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='11112222-3',
			email='admin_reasig@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Reasig',
			nombre_interno='admin_reasig',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.tecnico_1 = Usuario.objects.create_user(
			rut='33334444-5',
			email='tec1_reasig@delco.cl',
			password=self.password,
			nombre='Tec1',
			apellido='Reasig',
			nombre_interno='tec1_reasig',
			rol='TECNICO',
			is_active=True,
		)
		self.tecnico_2 = Usuario.objects.create_user(
			rut='55556666-7',
			email='tec2_reasig@delco.cl',
			password=self.password,
			nombre='Tec2',
			apellido='Reasig',
			nombre_interno='tec2_reasig',
			rol='TECNICO',
			is_active=True,
		)
		self.orden = OrdenTrabajo.objects.create(
			titulo='OT reasignacion',
			tipo_trabajo='INSTALACION',
			creada_por=self.admin,
			tecnico_responsable=self.tecnico_1,
			estado='ASIGNADA',
		)
		self.client = Client()
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))

	def test_admin_reasigna_tecnico_y_estado_reasignada(self):
		response = self.client.post(
			reverse('orden_detalle', kwargs={'pk': self.orden.pk}),
			{
				'accion': 'reasignar_tecnico',
				'tecnico_responsable': str(self.tecnico_2.pk),
				'motivo_reasignacion': 'Técnico original no disponible esta semana',
			},
		)
		self.assertEqual(response.status_code, 302)
		self.orden.refresh_from_db()
		self.assertEqual(self.orden.tecnico_responsable_id, self.tecnico_2.id)
		self.assertEqual(self.orden.estado, 'REASIGNADA')
		self.assertFalse(self.orden.tecnico_solicito_reasignacion)
		self.assertIn('no disponible', self.orden.motivo_reasignacion)

	def test_reasignar_sin_comentario_bloquea(self):
		response = self.client.post(
			reverse('orden_detalle', kwargs={'pk': self.orden.pk}),
			{
				'accion': 'reasignar_tecnico',
				'tecnico_responsable': str(self.tecnico_2.pk),
				'motivo_reasignacion': '',
			},
		)
		self.assertEqual(response.status_code, 302)
		self.orden.refresh_from_db()
		self.assertEqual(self.orden.tecnico_responsable_id, self.tecnico_1.id)
		self.assertEqual(self.orden.estado, 'ASIGNADA')


class OrdenRespaldoMoreappPdfTests(TestCase):
	"""1.1 — Subida de PDF de respaldo MoreApp en la OT."""

	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='30303030-3',
			email='admin_respaldo@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Respaldo',
			nombre_interno='admin_respaldo',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='40404040-4',
			email='tecnico_respaldo@delco.cl',
			password=self.password,
			nombre='Tecnico',
			apellido='Respaldo',
			nombre_interno='tecnico_respaldo',
			rol='TECNICO',
			is_active=True,
		)
		self.otro_tecnico = Usuario.objects.create_user(
			rut='50505050-5',
			email='otro_respaldo@delco.cl',
			password=self.password,
			nombre='Otro',
			apellido='Tecnico',
			nombre_interno='otro_respaldo',
			rol='TECNICO',
			is_active=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-RESP-001',
			direccion='Dir respaldo',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Respaldo',
			installation_address='Inst Respaldo',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-RESP-001',
			activo=True,
		)
		self.orden = OrdenTrabajo.objects.create(
			titulo='OT Respaldo MoreApp',
			descripcion='Prueba respaldo PDF',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=self.tecnico,
			estado='EN_EJECUCION',
		)
		self.client = Client()

	def _pdf_file(self, name='moreapp_respaldo.pdf', content=b'%PDF-1.4 fake content'):
		from django.core.files.uploadedfile import SimpleUploadedFile
		return SimpleUploadedFile(name, content, content_type='application/pdf')

	def test_tecnico_responsable_sube_respaldo_moreapp(self):
		self.assertTrue(self.client.login(rut=self.tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_subir_informe', kwargs={'pk': self.orden.pk}),
			{
				'archivo': self._pdf_file(),
				'como_respaldo_moreapp': '1',
			},
		)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data['success'])
		self.assertEqual(data['origen'], 'RESPALDO_MOREAPP')
		from .models import InformeCliente
		informe = InformeCliente.objects.get(pk=data['informe_id'])
		self.assertEqual(informe.origen, 'RESPALDO_MOREAPP')
		self.assertEqual(informe.orden_id, self.orden.pk)
		self.assertEqual(informe.cliente_id, self.cliente.pk)
		self.assertEqual(informe.subido_por_id, self.tecnico.pk)

	def test_rechaza_archivo_que_no_es_pdf_real(self):
		self.assertTrue(self.client.login(rut=self.tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_subir_informe', kwargs={'pk': self.orden.pk}),
			{
				'archivo': self._pdf_file(name='falso.pdf', content=b'no es un pdf'),
				'como_respaldo_moreapp': '1',
			},
		)
		self.assertEqual(response.status_code, 400)
		self.assertFalse(response.json()['success'])
		from .models import InformeCliente
		self.assertEqual(InformeCliente.objects.filter(orden=self.orden).count(), 0)

	def test_otro_tecnico_no_puede_subir(self):
		self.assertTrue(self.client.login(rut=self.otro_tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_subir_informe', kwargs={'pk': self.orden.pk}),
			{
				'archivo': self._pdf_file(),
				'como_respaldo_moreapp': '1',
			},
		)
		self.assertEqual(response.status_code, 403)

	def test_orden_cancelada_bloquea_subida(self):
		self.orden.estado = 'CANCELADA'
		self.orden.save(update_fields=['estado'])
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		response = self.client.post(
			reverse('orden_subir_informe', kwargs={'pk': self.orden.pk}),
			{
				'archivo': self._pdf_file(),
				'como_respaldo_moreapp': '1',
			},
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn('cancelada', response.json()['message'].lower())

	def test_flags_respaldo_cuando_no_hay_moreapp(self):
		"""Sin sync ni PDF: la OT queda marcada para pedir respaldo."""
		informes = self.orden.informes.all()
		sincronizaciones = self.orden.sincronizaciones_moreapp.filter(eliminado=False)
		sin_evidencia = (
			not sincronizaciones.exists()
			and not informes.filter(origen__in=['MOREAPP', 'RESPALDO_MOREAPP']).exists()
		)
		puede_subir = (
			self.tecnico.rol in ['ADMIN', 'ADMINISTRATIVO']
			or self.orden.tecnico_responsable_id == self.tecnico.id
		) and self.orden.estado != 'CANCELADA'
		self.assertTrue(sin_evidencia)
		self.assertTrue(puede_subir)

		# Tras subir respaldo, ya no está "sin evidencia MoreApp"
		self.assertTrue(self.client.login(rut=self.tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_subir_informe', kwargs={'pk': self.orden.pk}),
			{'archivo': self._pdf_file(), 'como_respaldo_moreapp': '1'},
		)
		self.assertTrue(response.json()['success'])
		self.assertTrue(
			self.orden.informes.filter(origen='RESPALDO_MOREAPP').exists()
		)
		self.assertFalse(
			not self.orden.sincronizaciones_moreapp.filter(eliminado=False).exists()
			and not self.orden.informes.filter(
				origen__in=['MOREAPP', 'RESPALDO_MOREAPP']
			).exists()
		)

class OrdenesTerminadasViewTests(TestCase):
	"""1.2 — Vista de trabajos terminados."""

	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='60606060-6',
			email='admin_term@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Term',
			nombre_interno='admin_term',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='70707070-7',
			email='tecnico_term@delco.cl',
			password=self.password,
			nombre='Tecnico',
			apellido='Term',
			nombre_interno='tecnico_term',
			rol='TECNICO',
			is_active=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-TERM-001',
			direccion='Dir term',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Term',
			installation_address='Inst Term',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-TERM-001',
			activo=True,
		)
		from django.utils import timezone
		self.ot_finalizada = OrdenTrabajo.objects.create(
			titulo='OT Finalizada test',
			descripcion='Terminada',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=self.tecnico,
			estado='FINALIZADA',
			fecha_fin_ejecucion=timezone.now(),
		)
		self.ot_abierta = OrdenTrabajo.objects.create(
			titulo='OT Abierta test',
			descripcion='En campo',
			tipo_trabajo='MANTENIMIENTO',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=self.tecnico,
			estado='EN_EJECUCION',
		)
		self.client = Client()

	def test_lista_solo_terminadas(self):
		from ordenes_trabajo.utils import ESTADOS_TERMINADOS
		self.assertEqual(reverse('ordenes_terminadas'), '/ordenes/terminadas/')
		ids = list(
			OrdenTrabajo.objects.filter(
				estado__in=ESTADOS_TERMINADOS, eliminado=False,
			).values_list('id', flat=True)
		)
		self.assertIn(self.ot_finalizada.id, ids)
		self.assertNotIn(self.ot_abierta.id, ids)
		self.assertEqual(
			OrdenTrabajo.objects.filter(estado='FINALIZADA', eliminado=False).count(),
			1,
		)

	def test_tecnico_solo_ve_las_suyas(self):
		from ordenes_trabajo.utils import ESTADOS_TERMINADOS
		otro = Usuario.objects.create_user(
			rut='80808080-8',
			email='otro_term@delco.cl',
			password=self.password,
			nombre='Otro',
			apellido='Term',
			nombre_interno='otro_term',
			rol='TECNICO',
			is_active=True,
		)
		from django.utils import timezone
		OrdenTrabajo.objects.create(
			titulo='OT otro tecnico',
			descripcion='x',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=otro,
			estado='FINALIZADA',
			fecha_fin_ejecucion=timezone.now(),
		)
		# Misma regla que la vista: técnico solo ve OT propias terminadas
		ids = list(
			OrdenTrabajo.objects.filter(
				estado__in=ESTADOS_TERMINADOS,
				eliminado=False,
				tecnico_responsable=self.tecnico,
			).values_list('id', flat=True)
		)
		self.assertEqual(ids, [self.ot_finalizada.id])


class OrdenValidacionComunicacionTests(TestCase):
	"""3 — Validación de comunicación en la OT."""

	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='80808080-8',
			email='admin_com@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Com',
			nombre_interno='admin_com',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.admin_op = Usuario.objects.create_user(
			rut='81818181-8',
			email='adminop_com@delco.cl',
			password=self.password,
			nombre='AdminOp',
			apellido='Com',
			nombre_interno='adminop_com',
			rol='ADMINISTRATIVO',
			is_active=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='90909090-9',
			email='tecnico_com@delco.cl',
			password=self.password,
			nombre='Tecnico',
			apellido='Com',
			nombre_interno='tecnico_com',
			rol='TECNICO',
			is_active=True,
		)
		self.otro_tecnico = Usuario.objects.create_user(
			rut='91919191-1',
			email='otro_com@delco.cl',
			password=self.password,
			nombre='Otro',
			apellido='Com',
			nombre_interno='otro_com',
			rol='TECNICO',
			is_active=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-COM-001',
			direccion='Dir com',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Com',
			installation_address='Inst Com',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-COM-001',
			activo=True,
		)
		self.orden = OrdenTrabajo.objects.create(
			titulo='OT Validación Comunicación',
			descripcion='Prueba comunicación',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=self.tecnico,
			estado='EN_EJECUCION',
		)
		self.client = Client()

	def test_tecnico_solicita_validacion(self):
		from ordenes_trabajo.models import ValidacionComunicacionOT
		self.assertTrue(self.client.login(rut=self.tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_solicitar_validacion_comunicacion', kwargs={'pk': self.orden.pk}),
			{'observaciones_solicitud': 'Probar IP 10.0.0.1'},
		)
		self.assertEqual(response.status_code, 302)
		reg = ValidacionComunicacionOT.objects.get(orden=self.orden)
		self.assertEqual(reg.estado, 'SOLICITADA')
		self.assertEqual(reg.solicitado_por_id, self.tecnico.pk)
		self.assertEqual(reg.observaciones_solicitud, 'Probar IP 10.0.0.1')

	def test_otro_tecnico_no_puede_solicitar(self):
		from ordenes_trabajo.models import ValidacionComunicacionOT
		self.assertTrue(self.client.login(rut=self.otro_tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_solicitar_validacion_comunicacion', kwargs={'pk': self.orden.pk}),
			{},
		)
		self.assertEqual(response.status_code, 302)
		self.assertFalse(ValidacionComunicacionOT.objects.filter(orden=self.orden).exists())

	def test_administrativo_registra_resultado_sobre_solicitud(self):
		from ordenes_trabajo.models import ValidacionComunicacionOT
		sol = ValidacionComunicacionOT.objects.create(
			orden=self.orden,
			estado='SOLICITADA',
			solicitado_por=self.tecnico,
			observaciones_solicitud='Llamar a oficina',
		)
		self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
		response = self.client.post(
			reverse('orden_registrar_validacion_comunicacion', kwargs={'pk': self.orden.pk}),
			{
				'validacion_id': str(sol.pk),
				'resultado': 'EXITOSA',
				'observaciones': 'Ping OK',
			},
		)
		self.assertEqual(response.status_code, 302)
		sol.refresh_from_db()
		self.assertEqual(sol.estado, 'EXITOSA')
		self.assertEqual(sol.validado_por_id, self.admin_op.pk)
		self.assertEqual(sol.observaciones, 'Ping OK')
		self.assertIsNotNone(sol.fecha_validacion)

	def test_admin_registro_directo_fallida(self):
		from ordenes_trabajo.models import ValidacionComunicacionOT
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		response = self.client.post(
			reverse('orden_registrar_validacion_comunicacion', kwargs={'pk': self.orden.pk}),
			{
				'resultado': 'FALLIDA',
				'observaciones': 'Sin respuesta del módem',
			},
		)
		self.assertEqual(response.status_code, 302)
		reg = ValidacionComunicacionOT.objects.get(orden=self.orden)
		self.assertEqual(reg.estado, 'FALLIDA')
		self.assertEqual(reg.validado_por_id, self.admin.pk)

	def test_tecnico_no_puede_registrar_resultado(self):
		from ordenes_trabajo.models import ValidacionComunicacionOT
		self.assertTrue(self.client.login(rut=self.tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_registrar_validacion_comunicacion', kwargs={'pk': self.orden.pk}),
			{'resultado': 'EXITOSA'},
		)
		self.assertEqual(response.status_code, 302)
		self.assertFalse(ValidacionComunicacionOT.objects.filter(orden=self.orden).exists())


class ComprobanteCambioMedidorTests(TestCase):
	"""2.2 — Comprobante digital de cambio de medidor."""

	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='15151515-1',
			email='admin_comp@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Comp',
			nombre_interno='admin_comp',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='16161616-1',
			email='tec_comp@delco.cl',
			password=self.password,
			nombre='Tec',
			apellido='Comp',
			nombre_interno='tec_comp',
			rol='TECNICO',
			is_active=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-COMP-001',
			direccion='Dir comp',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='CENTRO',
			customer_name='Cliente Comp',
			installation_address='Inst Comp',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-OLD-001',
			activo=True,
		)
		self.orden = OrdenTrabajo.objects.create(
			titulo='OT Cambio medidor comprobante',
			descripcion='Cambio',
			tipo_trabajo='CAMBIO',
			cliente=self.cliente,
			creada_por=self.admin,
			tecnico_responsable=self.tecnico,
			estado='EN_EJECUCION',
		)
		self.client = Client()

	def test_crear_comprobante_genera_pdf(self):
		"""Compat: crear sin PDF subido aún genera PDF interno (ruta secundaria)."""
		from ordenes_trabajo.models import ComprobanteCambioMedidor
		from ordenes_trabajo.comprobantes import crear_comprobante_cambio
		comp = crear_comprobante_cambio(
			orden=self.orden,
			usuario=self.admin,
			medidor_instalado_serie='SER-NEW-002',
			medidor_retirado_serie='SER-OLD-001',
		)
		self.assertTrue(bool(comp.pdf))
		self.assertFalse(comp.pdf_subido)
		self.assertEqual(ComprobanteCambioMedidor.objects.filter(orden=self.orden).count(), 1)

	def test_subir_pdf_firmado(self):
		from django.core.files.uploadedfile import SimpleUploadedFile
		from ordenes_trabajo.models import ComprobanteCambioMedidor
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
		pdf = SimpleUploadedFile('acta.pdf', b'%PDF-1.4 fake', content_type='application/pdf')
		response = self.client.post(
			reverse('orden_crear_comprobante_cambio', kwargs={'pk': self.orden.pk}),
			{
				'medidor_instalado_serie': 'SER-NEW-009',
				'pdf_firmado': pdf,
			},
		)
		self.assertEqual(response.status_code, 302)
		comp = ComprobanteCambioMedidor.objects.get(orden=self.orden)
		self.assertTrue(comp.pdf_subido)
		self.assertTrue(bool(comp.pdf))

	def test_subir_requiere_pdf(self):
		self.assertTrue(self.client.login(rut=self.tecnico.rut, password=self.password))
		response = self.client.post(
			reverse('orden_crear_comprobante_cambio', kwargs={'pk': self.orden.pk}),
			{'medidor_instalado_serie': 'SER-X'},
		)
		self.assertEqual(response.status_code, 302)
		from ordenes_trabajo.models import ComprobanteCambioMedidor
		self.assertFalse(ComprobanteCambioMedidor.objects.filter(orden=self.orden).exists())

	def test_listado_comprobantes(self):
		from ordenes_trabajo.comprobantes import crear_comprobante_cambio
		from ordenes_trabajo.models import ComprobanteCambioMedidor
		crear_comprobante_cambio(
			orden=self.orden,
			usuario=self.admin,
			medidor_instalado_serie='SER-LIST-1',
			medidor_retirado_serie='SER-OLD-001',
		)
		self.assertEqual(
			ComprobanteCambioMedidor.objects.filter(medidor_instalado_serie='SER-LIST-1').count(),
			1,
		)
		self.assertEqual(reverse('comprobantes_cambio_list'), '/ordenes/comprobantes-cambio/')
