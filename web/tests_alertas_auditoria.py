from django.test import TestCase

from clientes.models import Cliente
from usuarios.models import Usuario
from web.models import AuditoriaRegistro
from web.services.alertas import contar_ips_duplicadas, obtener_panel_alarmas
from web.services.audit import AuditEvent, register_audit_event


class AlertasOperativasTests(TestCase):
    def test_contar_ips_duplicadas(self):
        Cliente.objects.create(
            numero_cliente='C1',
            direccion='A',
            comuna='X',
            ip='10.0.0.1',
            meter_serial_n_1='S1',
        )
        Cliente.objects.create(
            numero_cliente='C2',
            direccion='B',
            comuna='X',
            ip='10.0.0.1',
            meter_serial_n_1='S2',
        )
        self.assertEqual(contar_ips_duplicadas(), 1)

    def test_panel_alarmas_incluye_ip_duplicada(self):
        Cliente.objects.create(
            numero_cliente='C3',
            direccion='C',
            comuna='X',
            ip='10.0.0.9',
            meter_serial_n_1='S3',
        )
        Cliente.objects.create(
            numero_cliente='C4',
            direccion='D',
            comuna='X',
            ip='10.0.0.9',
            meter_serial_n_1='S4',
        )
        codigos = {item['codigo'] for item in obtener_panel_alarmas()}
        self.assertIn('ip_duplicada', codigos)


class AuditoriaPersistenteTests(TestCase):
    def test_register_audit_event_guarda_en_bd(self):
        user = Usuario.objects.create_user(
            rut='80808080-8',
            email='audit@delco.cl',
            password='admin1234',
            nombre='Audit',
            apellido='Test',
            nombre_interno='audit_test',
            rol='ADMIN',
            is_active=True,
            is_staff=True,
        )
        register_audit_event(
            AuditEvent(
                actor_id=user.id,
                action='UPDATE',
                entity='Cliente',
                entity_id='99',
                field_name='ip',
                old_value='10.0.0.1',
                new_value='10.0.0.2',
                reason='Prueba',
            )
        )
        registro = AuditoriaRegistro.objects.get(entity_id='99')
        self.assertEqual(registro.old_value, '10.0.0.1')
        self.assertEqual(registro.new_value, '10.0.0.2')
