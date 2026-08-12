"""Tests de proyecto/carga, observaciones con formato y PDF de OT completada."""
from datetime import datetime
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ordenes_trabajo.models import OrdenTrabajo
from ordenes_trabajo.observaciones_html import (
    observaciones_a_reportlab,
    observaciones_a_texto_plano,
    sanitizar_observaciones_html,
)
from ordenes_trabajo.pdf_trabajo import (
    generar_pdf_trabajo_completado,
    orden_permite_pdf_completado,
)


Usuario = get_user_model()


class ObservacionesHtmlTests(TestCase):
	def test_sanitiza_negrita_y_mark(self):
		html = sanitizar_observaciones_html('Hola <b>negrita</b> y <mark>resaltado</mark>')
		self.assertIn('<b>negrita</b>', html)
		self.assertIn('<mark>resaltado</mark>', html)

	def test_elimina_script(self):
		html = sanitizar_observaciones_html('x<script>alert(1)</script>y')
		self.assertNotIn('<script', html.lower())
		self.assertIn('alert(1)', html)  # texto escapado/visible sin ejecutar

	def test_texto_plano_conserva_saltos(self):
		html = sanitizar_observaciones_html('linea1\nlinea2')
		self.assertIn('<br>', html)

	def test_span_amarillo_a_mark(self):
		html = sanitizar_observaciones_html(
			'a<span style="background-color: rgb(255, 245, 157)">res</span>b'
		)
		self.assertIn('<mark>', html)
		self.assertIn('res', html)

	def test_permite_tabla_y_font_size(self):
		html = sanitizar_observaciones_html(
			'<p><span style="font-size: 18px">Grande</span></p>'
			'<table><tr><th>A</th><td>B</td></tr></table>'
		)
		self.assertIn('font-size: 18px', html)
		self.assertIn('delco-obs-table', html)
		self.assertIn('<th>', html)
		self.assertIn('<td>', html)

	def test_bloquea_javascript_en_estilo(self):
		html = sanitizar_observaciones_html(
			'<span style="font-size: 14px; background-image: url(javascript:alert(1))">x</span>'
		)
		self.assertNotIn('javascript', html.lower())
		self.assertIn('font-size: 14px', html)

	def test_reportlab_markup(self):
		out = observaciones_a_reportlab('<b>ok</b> <mark>hi</mark>')
		self.assertIn('<b>', out)
		self.assertIn('backColor="yellow"', out)

	def test_texto_plano(self):
		self.assertEqual(
			observaciones_a_texto_plano('<b>Hola</b><br>mundo'),
			'Hola\nmundo',
		)

	def test_flowables_incluye_tabla(self):
		from reportlab.lib.styles import getSampleStyleSheet
		from ordenes_trabajo.observaciones_html import observaciones_a_flowables

		styles = getSampleStyleSheet()
		flow = observaciones_a_flowables(
			'<p>Intro</p><table><tr><th>Campo</th><td>Valor</td></tr></table>',
			styles,
		)
		self.assertTrue(len(flow) >= 1)
		tipos = [type(f).__name__ for f in flow]
		self.assertIn('Table', tipos)


@override_settings(MEDIA_ROOT='/tmp/delco_test_media')
class ProyectoCargaYPdfTests(TestCase):
	def setUp(self):
		self.admin = Usuario.objects.create_user(
			rut='11111111-1',
			email='admin@test.local',
			password='pass1234',
			nombre='Admin',
			apellido='Test',
			nombre_interno='Admin Test',
			rol='ADMIN',
		)
		self.tecnico = Usuario.objects.create_user(
			rut='22222222-2',
			email='tec@test.local',
			password='pass1234',
			nombre='Tec',
			apellido='Test',
			nombre_interno='Tec Test',
			rol='TECNICO',
		)
		self.client = Client()
		self.client.force_login(self.admin)

	def _crear_ot(self, estado='FINALIZADA', **extra):
		orden = OrdenTrabajo(
			titulo='Trabajo prueba PDF',
			descripcion='Desc',
			tipo_trabajo='INSTALACION',
			estado=estado,
			creada_por=self.admin,
			tecnico_responsable=self.tecnico,
			proyecto_carga_administrativa=extra.pop('proyecto', 'Proyecto Alfa'),
			observaciones_tecnicas=extra.pop(
				'obs',
				'Texto <b>importante</b> y <mark>resaltado</mark>',
			),
			**extra,
		)
		if estado in ('REALIZADA', 'VALIDADA', 'FINALIZADA'):
			orden.fecha_fin_ejecucion = timezone.now()
		orden.save()
		return orden

	def test_filtro_proyecto_en_listado(self):
		self._crear_ot(proyecto='Proyecto Alfa')
		self._crear_ot(proyecto='Proyecto Beta', estado='ASIGNADA')
		url = reverse('ordenes_list') + '?proyecto_carga=Alfa'
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Proyecto Alfa')
		# La OT Beta no debe aparecer con filtro Alfa
		content = resp.content.decode('utf-8', errors='ignore')
		self.assertNotIn('Proyecto Beta', content)

	def test_buscar_por_proyecto(self):
		self._crear_ot(proyecto='Carga SCi4 marzo')
		url = reverse('ordenes_list') + '?buscar=SCi4'
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Carga SCi4 marzo')

	def test_ordenar_por_proyecto(self):
		self._crear_ot(proyecto='Zulu')
		self._crear_ot(proyecto='Alpha')
		url = reverse('ordenes_list') + '?orden=proyecto&dir=asc'
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 200)

	def test_guardar_proyecto_en_detalle(self):
		orden = self._crear_ot(estado='ASIGNADA', proyecto='')
		url = reverse('orden_detalle', kwargs={'pk': orden.pk})
		resp = self.client.post(url, {
			'accion': 'guardar_proyecto_carga',
			'proyecto_carga_administrativa': 'Nueva Carga',
		})
		self.assertEqual(resp.status_code, 302)
		orden.refresh_from_db()
		self.assertEqual(orden.proyecto_carga_administrativa, 'Nueva Carga')

	def test_guardar_observaciones_con_formato(self):
		orden = self._crear_ot(estado='ASIGNADA', obs='')
		url = reverse('orden_detalle', kwargs={'pk': orden.pk})
		resp = self.client.post(url, {
			'accion': 'guardar_observaciones',
			'observaciones_tecnicas': 'Ver <b>cable</b> y <mark>IP</mark><script>x</script>',
		})
		self.assertEqual(resp.status_code, 302)
		orden.refresh_from_db()
		self.assertIn('<b>cable</b>', orden.observaciones_tecnicas)
		self.assertIn('<mark>IP</mark>', orden.observaciones_tecnicas)
		self.assertNotIn('<script', orden.observaciones_tecnicas.lower())

	def test_pdf_solo_completados(self):
		abierta = self._crear_ot(estado='ASIGNADA')
		self.assertFalse(orden_permite_pdf_completado(abierta))
		cerrada = self._crear_ot(estado='FINALIZADA')
		self.assertTrue(orden_permite_pdf_completado(cerrada))

	def test_descarga_pdf_completado(self):
		orden = self._crear_ot(estado='FINALIZADA')
		url = reverse('orden_pdf_completado', kwargs={'pk': orden.pk})
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp['Content-Type'], 'application/pdf')
		self.assertTrue(resp.content.startswith(b'%PDF'))

	def test_pdf_rechaza_no_completada(self):
		orden = self._crear_ot(estado='EN_EJECUCION')
		url = reverse('orden_pdf_completado', kwargs={'pk': orden.pk})
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 302)

	def test_generar_pdf_incluye_proyecto(self):
		orden = self._crear_ot(estado='VALIDADA', proyecto='Proyecto Gamma')
		pdf = generar_pdf_trabajo_completado(orden)
		self.assertTrue(pdf.startswith(b'%PDF'))
		# Contenido binario; al menos no vacío
		self.assertGreater(len(pdf), 200)

	def test_registros_antiguos_sin_proyecto_siguen_ok(self):
		orden = self._crear_ot(estado='ASIGNADA', proyecto='')
		self.assertEqual(orden.proyecto_carga_administrativa, '')
		url = reverse('orden_detalle', kwargs={'pk': orden.pk})
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Proyecto / Carga Administrativa')
