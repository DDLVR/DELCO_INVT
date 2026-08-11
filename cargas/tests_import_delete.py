from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from clientes.models import Cliente
from importaciones.models import ImportacionExcel
from usuarios.models import Usuario

from .import_excel import importar_cargas_excel, resumen_importacion
from .models import AdjuntoCarga, CargaAdministrativa
from .services import crear_carga, eliminar_carga


def _xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class CargasImportDeleteTests(TestCase):
    def setUp(self):
        self.password = 'admin1234'
        self.admin = Usuario.objects.create_user(
            rut='15151515-1',
            email='admin_imp@delco.cl',
            password=self.password,
            nombre='Admin',
            apellido='Imp',
            nombre_interno='admin_imp',
            rol='ADMIN',
            is_active=True,
            is_staff=True,
        )
        self.admin_op = Usuario.objects.create_user(
            rut='16161616-1',
            email='admvo_imp@delco.cl',
            password=self.password,
            nombre='Admvo',
            apellido='Imp',
            nombre_interno='admvo_imp',
            rol='ADMINISTRATIVO',
            is_active=True,
        )
        self.tecnico = Usuario.objects.create_user(
            rut='17171717-1',
            email='tec_imp@delco.cl',
            password=self.password,
            nombre='Tec',
            apellido='Imp',
            nombre_interno='tec_imp',
            rol='TECNICO',
            is_active=True,
        )
        self.cliente = Cliente.objects.create(
            numero_cliente='CLI-IMP-001',
            direccion='Dir',
            comuna='Santiago',
            tipo_suministro='ELECTRICO',
            sector='CENTRO',
            customer_name='Cliente Imp',
            installation_address='Inst',
            meter_manufacturer_id='TEST',
            meter_serial_n_1='SER-IMP-001',
            activo=True,
        )
        self.client = Client()

    def test_importar_excel_crea_y_reporta_errores_duplicados(self):
        crear_carga(
            self.admin,
            titulo='Ya existe',
            tipo='VERIFICACION',
            cliente=self.cliente,
        )
        buf = _xlsx_bytes([
            ['Titulo', 'Tipo', 'Prioridad', 'Cliente', 'Asignado', 'Descripcion'],
            ['Nueva carga A', 'VERIFICACION', 'ALTA', 'CLI-IMP-001', 'admvo_imp', 'ok'],
            ['', 'VERIFICACION', 'MEDIA', 'CLI-IMP-001', '', 'sin titulo'],
            ['Ya existe', 'VERIFICACION', 'MEDIA', 'CLI-IMP-001', '', 'dup db'],
            ['Nueva carga A', 'VERIFICACION', 'ALTA', 'CLI-IMP-001', '', 'dup file'],
            ['Otra ok', 'OTRO', 'BAJA', '', 'admvo_imp@delco.cl', 'segunda'],
        ])
        archivo = SimpleUploadedFile(
            'cargas.xlsx',
            buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        importacion = importar_cargas_excel(archivo, self.admin)
        conteos = resumen_importacion(importacion)

        self.assertEqual(importacion.total_filas, 5)
        self.assertEqual(importacion.exitosas, 2)
        self.assertEqual(conteos['errores'], 1)
        self.assertEqual(conteos['duplicados'], 2)
        self.assertIn('Registros cargados correctamente: 2', importacion.observaciones)
        self.assertTrue(
            CargaAdministrativa.objects.filter(
                eliminado=False, titulo='Nueva carga A', tipo='VERIFICACION'
            ).exists()
        )
        self.assertTrue(
            CargaAdministrativa.objects.filter(eliminado=False, titulo='Otra ok').exists()
        )
        # No se creó una segunda "Ya existe"
        self.assertEqual(
            CargaAdministrativa.objects.filter(
                eliminado=False, titulo__iexact='Ya existe', tipo='VERIFICACION'
            ).count(),
            1,
        )

    def test_importar_via_vista_json(self):
        self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
        buf = _xlsx_bytes([
            ['Titulo', 'Tipo'],
            ['Desde vista', 'COMUNICACION'],
        ])
        response = self.client.post(
            reverse('cargas_importar'),
            {
                'archivo': SimpleUploadedFile(
                    'c.xlsx',
                    buf.getvalue(),
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                ),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['exitosas'], 1)
        self.assertEqual(data['duplicados'], 0)
        self.assertTrue(ImportacionExcel.objects.filter(tipo='CARGAS_ADMINISTRATIVAS').exists())

    def test_tecnico_no_puede_importar_ni_eliminar(self):
        carga = crear_carga(self.admin, titulo='Protegida', tipo='OTRO')
        self.assertTrue(self.client.login(rut=self.tecnico.rut, password=self.password))
        r1 = self.client.post(reverse('cargas_importar'), {})
        self.assertEqual(r1.status_code, 403)
        r2 = self.client.post(reverse('cargas_eliminar', kwargs={'pk': carga.pk}))
        self.assertEqual(r2.status_code, 403)
        carga.refresh_from_db()
        self.assertFalse(carga.eliminado)

    def test_eliminar_individual_conserva_adjuntos(self):
        carga = crear_carga(self.admin, titulo='Con evidencia', tipo='OTRO')
        adj = AdjuntoCarga.objects.create(
            carga=carga,
            tipo='FOTO',
            nombre_archivo='ev.png',
            subido_por=self.admin,
        )
        self.assertTrue(self.client.login(rut=self.admin_op.rut, password=self.password))
        response = self.client.post(reverse('cargas_eliminar', kwargs={'pk': carga.pk}))
        self.assertEqual(response.status_code, 302)
        carga.refresh_from_db()
        self.assertTrue(carga.eliminado)
        self.assertEqual(carga.eliminado_por_id, self.admin_op.pk)
        adj.refresh_from_db()
        self.assertFalse(adj.eliminado)
        # No aparece en listado ni detalle
        self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
        lista = self.client.get(reverse('cargas_list'))
        self.assertEqual(lista.status_code, 200)
        ids_listado = [c.pk for c in lista.context['cargas']]
        self.assertNotIn(carga.pk, ids_listado)
        detalle = self.client.get(reverse('cargas_detalle', kwargs={'pk': carga.pk}))
        self.assertEqual(detalle.status_code, 404)

    def test_eliminar_masivo(self):
        c1 = crear_carga(self.admin, titulo='Masiva 1', tipo='OTRO')
        c2 = crear_carga(self.admin, titulo='Masiva 2', tipo='OTRO')
        self.assertTrue(self.client.login(rut=self.admin.rut, password=self.password))
        response = self.client.post(
            reverse('cargas_eliminar_masivo'),
            {'ids': [str(c1.pk), str(c2.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        c1.refresh_from_db()
        c2.refresh_from_db()
        self.assertTrue(c1.eliminado)
        self.assertTrue(c2.eliminado)

    def test_soft_delete_service_idempotente(self):
        carga = crear_carga(self.admin, titulo='Idem', tipo='OTRO')
        self.assertTrue(eliminar_carga(carga, self.admin, motivo='prueba'))
        self.assertFalse(eliminar_carga(carga, self.admin, motivo='otra'))
