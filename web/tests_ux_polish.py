import json
from types import SimpleNamespace

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from inventario.models import EstadoInventario, Medidor, MovimientoInventario, MovimientoItem, Ubicacion
from ordenes_trabajo.models import OrdenTrabajo
from usuarios.models import Usuario

from importaciones.utils import exportar_clientes_excel_completo
from web.services.filtros_export import queryset_clientes_filtrado
from web.services.movimientos_display import (
	enriquecer_movimiento_ubicaciones,
	etiqueta_ubicacion_movimiento,
)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UxPolishTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='90909090-9',
			email='admin_ux@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='UX',
			nombre_interno='admin_ux',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.tecnico = Usuario.objects.create_user(
			rut='91919191-1',
			email='tec_ux@delco.cl',
			password=self.password,
			nombre='Pedro',
			apellido='Tecnico',
			nombre_interno='tec_ux_polish',
			rol='TECNICO',
			is_active=True,
		)
		self.estado, _ = EstadoInventario.objects.get_or_create(nombre='En bodega')
		self.ubicacion_bodega, _ = Ubicacion.objects.get_or_create(
			tipo='BODEGA_DELCO',
			nombre='Bodega UX',
		)
		self.ubicacion_cliente, _ = Ubicacion.objects.get_or_create(
			tipo='CLIENTE',
			nombre='Ubicacion Cliente Generica',
		)
		self.cliente_a = Cliente.objects.create(
			numero_cliente='UX-CLI-001',
			direccion='Dir A',
			comuna='Santiago',
			sector='NORTE',
			customer_name='Cliente A UX',
			installation_address='Inst A',
			activo=True,
		)
		self.cliente_b = Cliente.objects.create(
			numero_cliente='UX-CLI-002',
			direccion='Dir B',
			comuna='Maipu',
			sector='SUR',
			customer_name='Cliente B UX',
			installation_address='Inst B',
			activo=True,
		)
		self.cliente_otro = Cliente.objects.create(
			numero_cliente='OTRO-999',
			direccion='Dir Otro',
			comuna='Providencia',
			sector='ESTE',
			customer_name='Cliente Otro',
			installation_address='Inst Otro',
			activo=True,
		)
		self.medidor = Medidor.objects.create(
			serie='UX-MED-001',
			marca='TEST',
			tipo_medidor='DIRECTO',
			estado_inventario=self.estado,
			ubicacion_actual=self.ubicacion_cliente,
			cliente=self.cliente_a,
		)
		self.factory = RequestFactory()
		self.client = Client()
		self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))

	def test_queryset_clientes_filtrado_respeta_numero_cliente(self):
		request = self.factory.get('/clientes/', {'numero_cliente': 'UX-CLI-001'})
		qs = queryset_clientes_filtrado(request, aplicar_filtros=True)
		numeros = set(qs.values_list('numero_cliente', flat=True))
		self.assertIn('UX-CLI-001', numeros)
		self.assertNotIn('UX-CLI-002', numeros)
		self.assertNotIn('OTRO-999', numeros)

	def test_exportar_clientes_excel_completo_una_hoja_sin_pod(self):
		wb = exportar_clientes_excel_completo(
			Cliente.objects.filter(pk__in=[self.cliente_a.pk, self.cliente_b.pk])
		)
		self.assertEqual(wb.sheetnames, ['CLIENTES COMPLETOS'])

		# CLIENTES COMPLETOS debe incluir los campos vigentes del modelo,
		# como la exportación completa de inventario.
		ws = wb['CLIENTES COMPLETOS']
		headers = [c.value for c in ws[1]]
		self.assertGreaterEqual(len(headers), 35)
		for esperado in ('Número cliente', 'Nombre cliente', 'SIM ICCID', 'Referencia', 'Medidor actual (serie)'):
			self.assertIn(esperado, headers)
		self.assertNotIn('ID', headers)
		self.assertNotIn('Pod', headers)
		self.assertNotIn('ID medidor actual', headers)
		self.assertFalse(any(h and str(h).startswith('ID ') for h in headers))
		# Sin encabezados en inglés
		for no_esperado in ('Customer name', 'Installation address', 'City', 'Client type', 'Note'):
			self.assertNotIn(no_esperado, headers)

	def test_etiqueta_ubicacion_movimiento_cliente_muestra_numero(self):
		item = SimpleNamespace(medidor=self.medidor, simcard=None, modem=None)
		label = etiqueta_ubicacion_movimiento(
			self.ubicacion_cliente, items=[item], rol='destino'
		)
		self.assertIn(self.cliente_a.numero_cliente, label)

		mov = MovimientoInventario.objects.create(
			tipo='INSTALACION',
			origen=self.ubicacion_bodega,
			destino=self.ubicacion_cliente,
			responsable=self.admin,
		)
		MovimientoItem.objects.create(
			movimiento=mov,
			tipo_equipo='MEDIDOR',
			medidor=self.medidor,
		)
		enriquecer_movimiento_ubicaciones(mov)
		self.assertIn(self.cliente_a.numero_cliente, mov.destino_display)

	def test_api_buscar_tecnicos_retorna_resultados(self):
		response = self.client.get(reverse('api_buscar_tecnicos'), {'q': 'tec_ux'})
		self.assertEqual(response.status_code, 200)
		payload = json.loads(response.content)
		self.assertIn('results', payload)
		self.assertGreaterEqual(len(payload['results']), 1)
		ids = {r['id'] for r in payload['results']}
		self.assertIn(self.tecnico.pk, ids)

	def test_clientes_modificar_masivo_actualiza_sector(self):
		response = self.client.post(reverse('clientes_modificar_masivo'), {
			'ids': f'{self.cliente_a.pk},{self.cliente_b.pk}',
			'sector': 'SECTOR-UX-NUEVO',
		})
		self.assertEqual(response.status_code, 200)
		payload = json.loads(response.content)
		self.assertTrue(payload['success'])
		self.assertEqual(payload['actualizados'], 2)
		self.cliente_a.refresh_from_db()
		self.cliente_b.refresh_from_db()
		self.assertEqual(self.cliente_a.sector, 'SECTOR-UX-NUEVO')
		self.assertEqual(self.cliente_b.sector, 'SECTOR-UX-NUEVO')

	def test_clientes_list_marca_duplicados(self):
		# Ficha repetida con el mismo numero_cliente que cliente_a
		Cliente.objects.create(
			numero_cliente='UX-CLI-001',
			direccion='Dir A bis',
			comuna='Santiago',
			sector='NORTE',
			customer_name='Cliente A duplicado',
			installation_address='Inst A bis',
			activo=True,
		)
		response = self.client.get(reverse('clientes_list'))
		self.assertEqual(response.status_code, 200)
		self.assertIn('UX-CLI-001', response.context['numeros_duplicados'])
		self.assertEqual(response.context['total_numeros_duplicados'], 1)
		self.assertContains(response, 'cliente-numero-duplicado')

		# El filtro "solo duplicados" muestra ambas fichas
		response = self.client.get(reverse('clientes_list'), {'solo_duplicados': '1'})
		self.assertEqual(response.context['total_fichas'], 2)

	def test_ordenes_modificar_masivo_cambia_estado(self):
		ot_1 = OrdenTrabajo.objects.create(
			titulo='OT UX 1',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente_a,
			creada_por=self.admin,
			estado='CREADA',
		)
		ot_2 = OrdenTrabajo.objects.create(
			titulo='OT UX 2',
			tipo_trabajo='INSTALACION',
			cliente=self.cliente_b,
			creada_por=self.admin,
			estado='CREADA',
		)
		response = self.client.post(reverse('ordenes_modificar_masivo'), {
			'ids': f'{ot_1.pk},{ot_2.pk}',
			'tecnico_responsable': str(self.tecnico.pk),
		})
		self.assertEqual(response.status_code, 200)
		payload = json.loads(response.content)
		self.assertTrue(payload['success'])
		ot_1.refresh_from_db()
		ot_2.refresh_from_db()
		self.assertEqual(ot_1.tecnico_responsable_id, self.tecnico.pk)
		self.assertEqual(ot_2.tecnico_responsable_id, self.tecnico.pk)
