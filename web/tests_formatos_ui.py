"""Tests de filtros/tags de presentación Delco (badges y formatos)."""
from datetime import date, datetime

from django.template import Context, Template
from django.test import SimpleTestCase


class FormatFiltersTests(SimpleTestCase):
	def _render(self, tpl, **ctx):
		return Template('{% load custom_filters %}' + tpl).render(Context(ctx))

	def test_format_fecha_hora(self):
		dt = datetime(2026, 3, 15, 9, 5)
		self.assertEqual(self._render('{{ v|format_fecha_hora }}', v=dt), '15/03/2026 09:05')
		self.assertEqual(self._render('{{ v|format_fecha_hora }}', v=None), '—')

	def test_format_fecha(self):
		self.assertEqual(self._render('{{ v|format_fecha }}', v=date(2026, 8, 3)), '03/08/2026')

	def test_format_rut(self):
		self.assertEqual(self._render('{{ v|format_rut }}', v='12345678-9'), '12.345.678-9')
		self.assertEqual(self._render('{{ v|format_rut }}', v='12.345.678-K'), '12.345.678-K')
		self.assertEqual(self._render('{{ v|format_rut }}', v=''), '—')

	def test_format_numero(self):
		self.assertEqual(self._render('{{ v|format_numero }}', v=1234567), '1.234.567')
		self.assertEqual(self._render('{{ v|format_numero }}', v=0), '0')


class BadgeTagsTests(SimpleTestCase):
	def _render(self, tpl, **ctx):
		return Template('{% load custom_filters %}' + tpl).render(Context(ctx))

	def test_badge_ot_colores_consistentes(self):
		html = self._render('{% badge_ot "VALIDADA" %}')
		self.assertIn('bg-success', html)
		self.assertIn('Validada', html)

		html = self._render('{% badge_ot "OBSERVADA" %}')
		self.assertIn('bg-danger', html)

		html = self._render('{% badge_ot "ASIGNADA" %}')
		self.assertIn('bg-warning', html)
		self.assertIn('text-dark', html)

		html = self._render('{% badge_ot "PENDIENTE_VALIDACION" %}')
		self.assertIn('bg-warning', html)

	def test_badge_moreapp_sync(self):
		html = self._render('{% badge_moreapp_sync "PROCESADO" %}')
		self.assertIn('bg-success', html)
		html = self._render('{% badge_moreapp_sync "ERROR_JSON" %}')
		self.assertIn('bg-danger', html)

	def test_badge_estado_externo(self):
		html = self._render('{% badge_estado_externo "PENDIENTE" sistema="SCi4" %}')
		self.assertIn('bg-warning', html)
		self.assertIn('SCi4', html)

	def test_badge_prioridad(self):
		html = self._render('{% badge_prioridad "CRITICA" %}')
		self.assertIn('bg-danger', html)
		html = self._render('{% badge_prioridad "ALTA" %}')
		self.assertIn('bg-warning', html)

	def test_badge_inventario_por_nombre(self):
		html = self._render('{% badge_inventario "Instalado" %}')
		self.assertIn('bg-success', html)
		html = self._render('{% badge_inventario "En Trayecto" %}')
		self.assertIn('bg-primary', html)
