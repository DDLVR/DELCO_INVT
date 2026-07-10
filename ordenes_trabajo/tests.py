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
