from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from inventario.models import SimCard, Modem, Medidor, EstadoInventario
from clientes.models import Cliente
from usuarios.models import Usuario
from random import choice, randint

class Command(BaseCommand):
    help = 'Genera datos de prueba: 5 SIM Cards y 5 Modems'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Generando datos de prueba...'))
        
        # Obtener o crear estados
        estado_bodega,     _ = EstadoInventario.objects.get_or_create(nombre='En bodega')
        estado_instalado,  _ = EstadoInventario.objects.get_or_create(nombre='Instalado')
        estado_retirado,   _ = EstadoInventario.objects.get_or_create(nombre='Retirado')
        estado_reparacion, _ = EstadoInventario.objects.get_or_create(nombre='En reparación')
        estado_baja,       _ = EstadoInventario.objects.get_or_create(nombre='Dado de baja')
        
        # Obtener clientes
        clientes = list(Cliente.objects.all())
        if not clientes:
            self.stdout.write(self.style.WARNING('⚠️ No hay clientes. Asegúrate de tener clientes registrados.'))
            return
        
        # Obtener técnicos
        tecnicos = list(Usuario.objects.filter(rol='TECNICO'))
        if not tecnicos:
            self.stdout.write(self.style.WARNING('⚠️ No hay técnicos. Asegúrate de tener técnicos registrados.'))
            return

        # ============= GENERAR SIM CARDS =============
        self.stdout.write('\n📱 Generando SIM Cards...')
        
        simcards_creadas = 0
        for i in range(1, 6):
            try:
                imei = f'35{randint(1000000000, 9999999999)}'
                
                sim, created = SimCard.objects.get_or_create(
                    imei=imei,
                    defaults={
                        'operador': choice(['ENTEL', 'CLARO', 'MOVISTAR', 'WOM']),
                        'abonado': f'+5691234{5678 + i}',
                        'direccion_ip': f'192.168.{randint(1, 254)}.{randint(1, 254)}',
                        'apn': choice(['movistar.cl', 'claro.cl', 'entel.cl', 'wom.cl']),
                        'fecha_recepcion': timezone.now() - timedelta(days=randint(1, 30)),
                        'entregado_a_nombre': choice(tecnicos).nombre_interno,
                        'fecha_entrega': timezone.now() - timedelta(days=randint(0, 10)),
                        'estado_inventario': choice([estado_bodega, estado_instalado, estado_retirado]),
                        'cliente': choice(clientes),
                        'en_custodia_de': choice(tecnicos) if randint(0, 1) else None,
                    }
                )
                
                if created:
                    simcards_creadas += 1
                    self.stdout.write(f'  ✓ SIM Card {i}: {imei}')
                else:
                    self.stdout.write(f'  ℹ️  SIM Card {imei} ya existía')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error en SIM Card {i}: {str(e)}'))

        # ============= GENERAR MODEMS =============
        self.stdout.write('\n📡 Generando Modems...')
        
        modems_creados = 0
        for i in range(1, 6):
            try:
                serie = f'MOD-{randint(100000, 999999)}'
                imei = f'35{randint(1000000000, 9999999999)}'
                
                modem, created = Modem.objects.get_or_create(
                    serie=serie,
                    defaults={
                        'marca': choice(['Huawei', 'ZTE', 'D-Link', 'TP-Link']),
                        'modelo': choice(['E8372', 'E5573', 'DIR-506L', 'M7350']),
                        'imei': imei,
                        'fecha_recepcion': timezone.now() - timedelta(days=randint(1, 30)),
                        'fecha_entrega': timezone.now() - timedelta(days=randint(0, 10)),
                        'caja': f'CAJA-{randint(1000, 9999)}',
                        'tecnico_responsable': choice(tecnicos).nombre_interno,
                        'cliente': choice(clientes),
                        'observaciones': f'Modem de prueba #{i}',
                        'ip': f'192.168.{randint(1, 254)}.{randint(1, 254)}',
                        'puerto': str(choice([8080, 8081, 8082, 9000])),
                        'estado_inventario': choice([estado_bodega, estado_instalado, estado_retirado]),
                        'entregado_a': choice(tecnicos) if randint(0, 1) else None,
                    }
                )
                
                if created:
                    modems_creados += 1
                    self.stdout.write(f'  ✓ Modem {i}: {serie}')
                else:
                    self.stdout.write(f'  ℹ️  Modem {serie} ya existía')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error en Modem {i}: {str(e)}'))

        # RESUMEN
        self.stdout.write(self.style.SUCCESS(f'\n✅ Datos de prueba generados:'))
        self.stdout.write(f'   • SIM Cards creadas: {simcards_creadas}')
        self.stdout.write(f'   • Modems creados: {modems_creados}')
