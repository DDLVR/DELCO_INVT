from django.test import Client, TestCase
from django.urls import reverse

from clientes.models import Cliente
from ordenes_trabajo.models import OrdenTrabajo
from reportes.services import run_report
from usuarios.models import Usuario


class ReportesPunto9Tests(TestCase):
    def setUp(self):
        self.password = 'admin1234'
        self.admin = Usuario.objects.create_user(
            rut='96969696-6',
            email='admin_rep@delco.cl',
            password=self.password,
            nombre='Admin',
            apellido='Rep',
            nombre_interno='admin_rep',
            rol='ADMIN',
            is_active=True,
            is_staff=True,
        )
        self.client = Client()
        self.client.login(rut=self.admin.rut, password=self.password)

    def test_hub_reportes_accesible(self):
        from django.test import RequestFactory
        from reportes.views import reportes_hub_view

        request = RequestFactory().get('/reportes/')
        request.user = self.admin
        response = reportes_hub_view(request)
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Sin reportes operativos por ahora', content)
        self.assertNotIn('Base completa de clientes', content)

    def test_export_clientes_completos_excel(self):
        response = self.client.get(
            reverse('reportes_export', kwargs={'slug': 'clientes_completos'}),
            {'formato': 'excel'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_export_clientes_completos_pdf(self):
        response = self.client.get(
            reverse('reportes_export', kwargs={'slug': 'clientes_completos'}),
            {'formato': 'pdf'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_export_formato_invalido(self):
        response = self.client.get(
            reverse('reportes_export', kwargs={'slug': 'clientes_completos'}),
            {'formato': 'csv'},
        )
        self.assertEqual(response.status_code, 400)

    def test_export_slug_invalido(self):
        response = self.client.get('/reportes/exportar/no-existe/')
        self.assertEqual(response.status_code, 400)


class ReportesSoloActividadOperativaTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            rut='97979797-7',
            email='admin_scope@delco.cl',
            password='admin1234',
            nombre='Admin',
            apellido='Scope',
            nombre_interno='admin_scope',
            rol='ADMIN',
            is_active=True,
            is_staff=True,
        )
        self.cliente = Cliente.objects.create(
            numero_cliente='CLI-IMPORT-001',
            direccion='Dir',
            comuna='Santiago',
            tipo_suministro='ELECTRICO',
            sector='CENTRO',
            customer_name='Importado',
            installation_address='Inst',
            meter_manufacturer_id='TEST',
            meter_serial_n_1='SER-001',
            ip='10.0.0.1',
            activo=True,
        )

    def test_importados_no_aparecen_sin_ot(self):
        _, rows = run_report('clientes_completos', {})
        self.assertEqual(rows, [])
        _, dup_rows = run_report('clientes_ip_duplicada', {})
        self.assertEqual(dup_rows, [])

    def test_cliente_aparece_cuando_tiene_ot(self):
        OrdenTrabajo.objects.create(
            titulo='OT real',
            tipo_trabajo='INSTALACION',
            cliente=self.cliente,
            creada_por=self.admin,
            estado='ASIGNADA',
        )
        _, rows = run_report('clientes_completos', {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 'CLI-IMPORT-001')

    def test_hub_muestra_catalogo_con_actividad(self):
        from django.test import RequestFactory
        from reportes.views import reportes_hub_view

        OrdenTrabajo.objects.create(
            titulo='OT hub',
            tipo_trabajo='INSTALACION',
            cliente=self.cliente,
            creada_por=self.admin,
            estado='ASIGNADA',
        )
        request = RequestFactory().get('/reportes/')
        request.user = self.admin
        response = reportes_hub_view(request)
        self.assertIn('Base completa de clientes', response.content.decode())

    def test_hub_vacio_con_moreapp_sin_cliente(self):
        from django.test import RequestFactory
        from ordenes_trabajo.models import IntegracionMoreApp
        from reportes.views import reportes_hub_view

        IntegracionMoreApp.objects.create(
            moreapp_submission_id='orphan-moreapp-1',
            estado_sincronizacion='PROCESADO',
            datos_procesados={'cliente_codigo': '9999999'},
            datos_recibidos={},
        )
        request = RequestFactory().get('/reportes/')
        request.user = self.admin
        response = reportes_hub_view(request)
        content = response.content.decode()
        self.assertIn('Sin reportes operativos por ahora', content)
        self.assertNotIn('Base completa de clientes', content)
