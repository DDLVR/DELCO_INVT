from io import BytesIO

import openpyxl
from django.test import TestCase

from clientes.models import Cliente
from importaciones.utils import importar_clientes_excel
from usuarios.models import Usuario


class ImportacionClientesModoTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create_user(
			rut='22222222-2',
			email='import_test@delco.cl',
			password='admin1234',
			nombre='Import',
			apellido='Tester',
			nombre_interno='import_tester',
			rol='ADMIN',
			is_active=True,
			is_staff=True,
		)

	def _build_excel(self, rows):
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.title = 'CLIENTES'
		ws.append([
			'Sector',
			'Tipo Suministro',
			'Numero Cliente',
			'Comuna',
			'Nombre Cliente',
			'Direccion de Instalacion',
			'Marca Medidor',
			'Proyecto',
			'Serie Medidor',
			'IP',
		])
		for row in rows:
			ws.append(row)

		buffer = BytesIO()
		wb.save(buffer)
		buffer.seek(0)
		buffer.name = 'clientes_test.xlsx'
		return buffer

	def test_importacion_incremental_conserva_clientes_no_presentes(self):
		Cliente.objects.create(
			numero_cliente='CLI-OLD-1',
			direccion='Dir old 1',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Cliente Old',
			installation_address='Inst old',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-OLD-1',
			activo=True,
		)

		archivo = self._build_excel([
			['CENTRO', 'ELECTRICO', 'CLI-NEW-1', 'Santiago', 'Cliente Nuevo', 'Inst New', 'SCHNEIDER', 'PROY A', 'SER-NEW-1', '10.0.0.10'],
		])
		importacion = importar_clientes_excel(archivo, self.usuario, sincronizar_completo=False)

		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-NEW-1', activo=True).exists())
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-OLD-1', activo=True).exists())

	def test_importacion_sync_desactiva_clientes_no_presentes(self):
		Cliente.objects.create(
			numero_cliente='CLI-KEEP-1',
			direccion='Dir keep',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Cliente Keep',
			installation_address='Inst keep',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-KEEP-1',
			activo=True,
		)
		Cliente.objects.create(
			numero_cliente='CLI-DROP-1',
			direccion='Dir drop',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='SUR',
			customer_name='Cliente Drop',
			installation_address='Inst drop',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-DROP-1',
			activo=True,
		)

		archivo = self._build_excel([
			['NORTE', 'ELECTRICO', 'CLI-KEEP-1', 'Santiago', 'Cliente Keep Updated', 'Inst keep 2', 'TEST', 'PROY B', 'SER-KEEP-1', '10.0.0.20'],
		])
		importacion = importar_clientes_excel(archivo, self.usuario, sincronizar_completo=True)

		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-KEEP-1', activo=True).exists())
		self.assertFalse(Cliente.objects.filter(numero_cliente='CLI-DROP-1', activo=True).exists())

	def test_importacion_normaliza_ip_excel_sin_puntos(self):
		from web.services.validators import normalize_ip_value

		self.assertEqual(normalize_ip_value(10117122165), '10.117.122.165')
		self.assertEqual(normalize_ip_value('10.117.22.31'), '10.117.22.31')

		archivo = self._build_excel([
			['CENTRO', 'ELECTRICO', 'CLI-IP-1', 'Santiago', 'Cliente IP', 'Inst IP', 'SCHNEIDER', 'PROY A', 'SER-IP-1', 10117122165],
		])
		importacion = importar_clientes_excel(archivo, self.usuario, sincronizar_completo=False)
		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertEqual(importacion.exitosas, 1)
		self.assertEqual(importacion.fallidas, 0)
		cliente = Cliente.objects.get(numero_cliente='CLI-IP-1', activo=True)
		self.assertEqual(cliente.ip, '10.117.122.165')

	def test_reactiva_cliente_inactivo_en_import(self):
		Cliente.objects.create(
			numero_cliente='CLI-REV-1',
			direccion='Dir old',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Inactivo',
			installation_address='Inst',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-REV-1',
			activo=False,
		)
		archivo = self._build_excel([
			['NORTE', 'ELECTRICO', 'CLI-REV-1', 'Santiago', 'Reactivado', 'Inst 2', 'TEST', 'PROY', 'SER-REV-1', '10.0.0.9'],
		])
		importacion = importar_clientes_excel(archivo, self.usuario, sincronizar_completo=False)
		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertEqual(importacion.exitosas, 1)
		cliente = Cliente.objects.get(numero_cliente='CLI-REV-1', meter_serial_n_1='SER-REV-1')
		self.assertTrue(cliente.activo)
		self.assertTrue(any('reactivado' in w.lower() for w in getattr(importacion, 'warnings', [])))

	def test_actualiza_unica_ficha_sin_crear_duplicado_por_serie(self):
		"""Si la ficha no tiene serie, el Excel la completa sin crear otra."""
		Cliente.objects.create(
			numero_cliente='CLI-UPD-1',
			direccion='Dir 1',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Viejo',
			installation_address='Inst 1',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='',
			activo=True,
		)
		archivo = self._build_excel([
			['CENTRO', 'ELECTRICO', 'CLI-UPD-1', 'Santiago', 'Nuevo Nombre', 'Inst 2', 'TEST', 'PROY', 'SER-NEW', '10.0.0.55'],
		])
		importacion = importar_clientes_excel(archivo, self.usuario, sincronizar_completo=False)
		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertEqual(Cliente.objects.filter(numero_cliente='CLI-UPD-1').count(), 1)
		cliente = Cliente.objects.get(numero_cliente='CLI-UPD-1', activo=True)
		self.assertEqual(cliente.meter_serial_n_1, 'SER-NEW')
		self.assertEqual(cliente.customer_name, 'Nuevo Nombre')
		self.assertEqual(cliente.ip, '10.0.0.55')

	def test_reimport_mismo_numero_serie_actualiza_no_duplica(self):
		Cliente.objects.create(
			numero_cliente='CLI-SAME',
			direccion='Dir 1',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Viejo',
			installation_address='Inst 1',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-1',
			ip='10.0.0.1',
			activo=True,
		)
		archivo = self._build_excel([
			['CENTRO', 'ELECTRICO', 'CLI-SAME', 'Maipú', 'Actualizado', 'Inst 2', 'TEST', 'PROY', 'SER-1', '10.0.0.2'],
		])
		importacion = importar_clientes_excel(archivo, self.usuario, sincronizar_completo=False)
		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertEqual(Cliente.objects.filter(numero_cliente='CLI-SAME').count(), 1)
		cliente = Cliente.objects.get(numero_cliente='CLI-SAME', activo=True)
		self.assertEqual(cliente.comuna, 'Maipú')
		self.assertEqual(cliente.customer_name, 'Actualizado')
		self.assertEqual(cliente.ip, '10.0.0.2')

	def test_crea_segunda_ficha_si_ya_hay_otra_serie_activa(self):
		Cliente.objects.create(
			numero_cliente='CLI-MULTI',
			direccion='Dir 1',
			comuna='Santiago',
			tipo_suministro='ELECTRICO',
			sector='NORTE',
			customer_name='Ficha A',
			installation_address='Inst 1',
			meter_manufacturer_id='TEST',
			meter_serial_n_1='SER-A',
			activo=True,
		)
		archivo = self._build_excel([
			['CENTRO', 'ELECTRICO', 'CLI-MULTI', 'Santiago', 'Ficha B', 'Inst 2', 'TEST', 'PROY', 'SER-B', '10.0.0.66'],
		])
		importacion = importar_clientes_excel(archivo, self.usuario, sincronizar_completo=False)
		self.assertEqual(importacion.estado, 'COMPLETADO')
		self.assertEqual(Cliente.objects.filter(numero_cliente='CLI-MULTI', activo=True).count(), 2)
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-MULTI', meter_serial_n_1='SER-A', activo=True).exists())
		self.assertTrue(Cliente.objects.filter(numero_cliente='CLI-MULTI', meter_serial_n_1='SER-B', activo=True).exists())
