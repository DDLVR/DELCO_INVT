"""Tests: catálogo Proyecto asociado al cliente + import OT sin crear clientes."""
from io import BytesIO

import openpyxl
from django.test import TestCase, override_settings
from django.urls import reverse

from catalogos.models import Proyecto
from clientes.models import Cliente, ClienteProyectoHistorial
from clientes.proyecto_historial import asignar_proyecto_al_crear_ot, registrar_cambio_proyecto
from inventario.models import EstadoInventario, Medidor, Ubicacion
from ordenes_trabajo.models import OrdenTrabajo
from ordenes_trabajo.utils import importar_ordenes_excel
from usuarios.models import Usuario


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class ProyectoClienteCatalogoTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='77770001-1',
			email='admin_proy@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Proy',
			nombre_interno='admin_proy',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-PROY-001',
			direccion='Dir A',
			comuna='Santiago',
			customer_name='Empresa ABC',
			installation_address='Ubicacion A',
			activo=True,
		)

	def test_asignar_proyecto_crea_catalogo_y_fk_en_cliente(self):
		cambio = asignar_proyecto_al_crear_ot(
			self.cliente,
			'Proyecto Wally',
			usuario=self.admin,
			motivo='Creación OT',
		)
		self.assertTrue(cambio)
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.proyecto, 'Proyecto Wally')
		self.assertIsNotNone(self.cliente.proyecto_asignado_id)
		self.assertEqual(self.cliente.proyecto_asignado.nombre, 'Proyecto Wally')
		self.assertTrue(
			ClienteProyectoHistorial.objects.filter(
				cliente=self.cliente, proyecto='Proyecto Wally', vigente=True,
			).exists()
		)
		self.assertEqual(Proyecto.objects.filter(nombre__iexact='Proyecto Wally').count(), 1)

	def test_texto_legado_se_conserva_al_cambiar_proyecto(self):
		registrar_cambio_proyecto(self.cliente, 'Proyecto Antiguo', usuario=self.admin)
		registrar_cambio_proyecto(self.cliente, 'Proyecto Nuevo', usuario=self.admin)
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.proyecto, 'Proyecto Nuevo')
		historicos = list(
			ClienteProyectoHistorial.objects.filter(cliente=self.cliente).order_by('fecha_inicio')
		)
		self.assertGreaterEqual(len(historicos), 2)
		self.assertFalse(historicos[0].vigente)
		self.assertEqual(historicos[0].proyecto, 'Proyecto Antiguo')

	def test_historial_muestra_varios_medidores_mismo_cliente(self):
		estado, _ = EstadoInventario.objects.get_or_create(nombre='Instalado')
		ubic_a, _ = Ubicacion.objects.get_or_create(tipo='CLIENTE', nombre='Ubicacion A', defaults={'direccion': 'Calle A 1'})
		ubic_t, _ = Ubicacion.objects.get_or_create(tipo='CLIENTE', nombre='Ubicacion T', defaults={'direccion': 'Calle T 2'})
		Medidor.objects.create(serie='MED-A-001', cliente=self.cliente, estado_inventario=estado, ubicacion_actual=ubic_a, eliminado=False)
		Medidor.objects.create(serie='MED-T-002', cliente=self.cliente, estado_inventario=estado, ubicacion_actual=ubic_t, eliminado=False)

		self.client.login(username=self.admin.rut, password=self.password)
		resp = self.client.get(reverse('cliente_historial', kwargs={'pk': self.cliente.pk}))
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'MED-A-001')
		self.assertContains(resp, 'MED-T-002')
		self.assertContains(resp, 'Equipos asociados')


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class ImportOtSinCrearClienteTests(TestCase):
	def setUp(self):
		self.password = 'admin1234'
		self.admin = Usuario.objects.create_user(
			rut='77770002-2',
			email='admin_imp@delco.cl',
			password=self.password,
			nombre='Admin',
			apellido='Imp',
			nombre_interno='admin_imp',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)
		self.cliente = Cliente.objects.create(
			numero_cliente='CLI-IMP-OK',
			direccion='Dir',
			comuna='Santiago',
			activo=True,
		)

	def _excel(self, filas):
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.append([
			'Numero Cliente', 'Titulo', 'Descripcion', 'Tipo Trabajo',
			'Tecnico', 'Estado', 'Observaciones Tecnicas', 'Proyecto / Carga Administrativa',
		])
		for fila in filas:
			ws.append(fila)
		buf = BytesIO()
		wb.save(buf)
		buf.seek(0)
		buf.name = 'ordenes.xlsx'
		return buf

	def test_cliente_inexistente_bloquea_toda_la_importacion(self):
		antes = OrdenTrabajo.objects.count()
		archivo = self._excel([
			['CLI-IMP-OK', 'OT buena', 'ok', 'INSTALACION', '', 'CREADA', '', 'Wally'],
			['CLI-NO-EXISTE', 'OT mala', 'fail', 'INSTALACION', '', 'CREADA', '', 'Wally'],
		])
		imp = importar_ordenes_excel(archivo, self.admin)
		self.assertEqual(imp.estado, 'ERROR')
		self.assertEqual(imp.exitosas, 0)
		self.assertEqual(OrdenTrabajo.objects.count(), antes)
		self.assertFalse(Cliente.objects.filter(numero_cliente='CLI-NO-EXISTE').exists())
		self.assertIn('Clientes inexistentes', imp.observaciones or '')

	def test_import_ok_asigna_proyecto_al_cliente(self):
		archivo = self._excel([
			['CLI-IMP-OK', 'OT Wally', 'trabajo', 'INSTALACION', '', 'CREADA', '', 'Proyecto Wally'],
		])
		imp = importar_ordenes_excel(archivo, self.admin)
		self.assertEqual(imp.estado, 'COMPLETADO')
		self.assertGreaterEqual(imp.exitosas, 1)
		self.cliente.refresh_from_db()
		self.assertEqual(self.cliente.proyecto, 'Proyecto Wally')
		self.assertIsNotNone(self.cliente.proyecto_asignado_id)
		orden = OrdenTrabajo.objects.get(titulo='OT Wally')
		self.assertEqual(orden.proyecto_carga_administrativa, 'Proyecto Wally')
