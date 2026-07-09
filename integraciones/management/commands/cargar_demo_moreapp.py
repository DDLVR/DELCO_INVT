"""
Carga registros MoreApp de demostración para revisar la UI antes de producción.

Usa JSON reales del export ZIP de MoreApp y prepara datos maestros mínimos
para mostrar escenarios: éxito, advertencias, incidencias e instalación.

Uso:
    python manage.py cargar_demo_moreapp
    python manage.py cargar_demo_moreapp --limpiar
    python manage.py cargar_demo_moreapp --zip "C:\\ruta\\Mantenimiento_Telemetria_V3.zip"
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import uuid
import zipfile
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from integraciones.reader import procesar_payload_moreapp

DEMO_SUBMISSION_PREFIX = 'demo-prueba-'
DEFAULT_ZIP = r'c:\Users\DELCOCHILE\Downloads\Mantenimiento_Telemetria_V3.zip'

# correlativo en ZIP -> escenario de demo
DEMO_CASOS = [
    {
        'zip_folder': 'Mantenimiento_Telemetria_V3',
        'correlativo': '212',
        'etiqueta': 'Mantenimiento ejecutado (completo)',
        'preparar_maestros': 'mantenimiento_completo',
        'crear_ot': True,
    },
    {
        'zip_folder': 'Mantenimiento_Telemetria_V3',
        'correlativo': '208',
        'etiqueta': 'Mantenimiento con equipos faltantes',
        'preparar_maestros': 'solo_cliente_proverde',
        'crear_ot': False,
    },
    {
        'zip_folder': 'Mantenimiento_Telemetria_V3',
        'correlativo': '220',
        'etiqueta': 'Incidencia en terreno',
        'preparar_maestros': 'solo_cliente_incidencia',
        'crear_ot': False,
    },
    {
        'zip_folder': None,  # carpeta con tilde en el ZIP
        'correlativo': '1184',
        'etiqueta': 'Registro medidores — instalación',
        'preparar_maestros': 'registro_medidores',
        'crear_ot': False,
    },
]


class Command(BaseCommand):
    help = 'Carga registros MoreApp de demostración con datos maestros para revisar la UI'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zip',
            type=str,
            default=DEFAULT_ZIP,
            help='Ruta al ZIP exportado desde MoreApp',
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Elimina demos anteriores (MoreApp, OT prueba, inventario DEMO) antes de cargar',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra qué se cargaría, sin escribir en BD',
        )

    def handle(self, *args, **options):
        zip_path = options['zip']
        dry_run = options['dry_run']

        if not os.path.isfile(zip_path):
            self.stdout.write(self.style.ERROR(f'ZIP no encontrado: {zip_path}'))
            return

        if options['limpiar'] and not dry_run:
            self._limpiar_demo_anterior()

        payloads = self._extraer_payloads_desde_zip(zip_path)
        if not payloads:
            self.stdout.write(self.style.ERROR('No se encontraron JSON de demo en el ZIP.'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run — no se guardará nada'))
            for item in payloads:
                self.stdout.write(f"  - {item['etiqueta']} (correlativo {item['correlativo']})")
            return

        resultados = []
        with transaction.atomic():
            for item in payloads:
                self._preparar_maestros(item)
                if item.get('crear_ot'):
                    self._crear_ot_demo(item)
                ruta = self._guardar_en_registros(item['payload'], item)
                resultado = procesar_payload_moreapp(
                    item['payload'],
                    ruta_context=ruta,
                )
                from ordenes_trabajo.models import IntegracionMoreApp

                reg = IntegracionMoreApp.objects.filter(
                    moreapp_submission_id=item['payload']['id'],
                ).first()
                if reg and item.get('correlativo', '').isdigit():
                    reg.numero_correlativo = int(item['correlativo'])
                    reg.save(update_fields=['numero_correlativo'])
                resultados.append({**item, **resultado, 'submission_id': item['payload']['id']})

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Demo MoreApp cargada. Revisar en:'))
        self.stdout.write('  • /reportes/moreapp/')
        self.stdout.write('  • /operacional/pendientes/')
        self.stdout.write('  • /reportes/  (hub operativo)')
        self.stdout.write('')
        for r in resultados:
            from ordenes_trabajo.models import IntegracionMoreApp

            reg = IntegracionMoreApp.objects.filter(
                moreapp_submission_id=r['submission_id']
            ).first()
            revision = reg.estado_revision if reg else '?'
            orden = f'OT #{reg.orden_id}' if reg and reg.orden_id else 'sin OT'
            estilo = self.style.SUCCESS if revision == 'REVISADO' else self.style.WARNING
            self.stdout.write(estilo(
                f"  [{r['correlativo']}] {r['etiqueta']}: {r['resultado']} | revisión={revision} | {orden}"
            ))
            if reg and reg.datos_procesados.get('resultado_operativo', {}).get('pendientes_revision'):
                for p in reg.datos_procesados['resultado_operativo']['pendientes_revision'][:3]:
                    self.stdout.write(f"      pendiente: {p['tipo_equipo']} {p['identificador']} — {p['motivo']}")

    def _limpiar_demo_anterior(self):
        from inventario.models import Medidor, Modem, SimCard
        from ordenes_trabajo.models import IntegracionMoreApp, OrdenTrabajo

        deleted_ma, _ = IntegracionMoreApp.objects.all().delete()
        self.stdout.write(f'  Registros MoreApp eliminados: {deleted_ma}')

        ot_qs = OrdenTrabajo.objects.filter(titulo__icontains='prueba — MoreApp')
        if ot_qs.exists():
            IntegracionMoreApp.objects.filter(orden_id__in=ot_qs.values_list('pk', flat=True)).update(orden=None)
            deleted_ot, _ = ot_qs.delete()
            self.stdout.write(f'  OT demo eliminadas: {deleted_ot}')

        med_qs = Medidor.objects.filter(observaciones__icontains='DEMO MoreApp')
        if med_qs.exists():
            n, _ = med_qs.delete()
            self.stdout.write(f'  Medidor demo eliminados: {n}')

        mod_qs = Modem.objects.filter(observaciones__icontains='DEMO MoreApp')
        if mod_qs.exists():
            n, _ = mod_qs.delete()
            self.stdout.write(f'  Modem demo eliminados: {n}')

        sim_qs = SimCard.objects.filter(imei__startswith='DEMO-MORE-')
        if sim_qs.exists():
            n, _ = sim_qs.delete()
            self.stdout.write(f'  SimCard demo eliminadas: {n}')

        from clientes.models import Cliente

        cli_demo = Cliente.objects.filter(note__icontains='DEMO MoreApp')
        if cli_demo.exists():
            n, _ = cli_demo.delete()
            self.stdout.write(f'  Clientes demo eliminados: {n}')

    def _extraer_payloads_desde_zip(self, zip_path: str) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        with zipfile.ZipFile(zip_path) as zf:
            index = {}
            for name in zf.namelist():
                if not name.endswith('registration.json'):
                    continue
                parts = name.replace('\\', '/').split('/')
                if len(parts) < 3:
                    continue
                corr = parts[-2]
                index[corr] = name

            for caso in DEMO_CASOS:
                corr = caso['correlativo']
                path = index.get(corr)
                if not path:
                    continue
                raw = json.loads(zf.read(path))
                payload = copy.deepcopy(raw)
                payload['id'] = f"{DEMO_SUBMISSION_PREFIX}{corr}-{uuid.uuid4().hex[:8]}"
                payloads.append({
                    **caso,
                    'payload': payload,
                    'zip_path': path,
                    'form_name': payload.get('info', {}).get('formName', ''),
                    'customer_id': str(payload.get('info', {}).get('customerId', '177930')),
                })
        return payloads

    def _estados_inventario(self):
        from inventario.models import EstadoInventario

        nombres = ['En bodega', 'Instalado', 'Retirado']
        return {n: EstadoInventario.objects.get_or_create(nombre=n)[0] for n in nombres}

    def _preparar_maestros(self, item: Dict[str, Any]):
        from clientes.models import Cliente
        from inventario.models import Medidor, Modem, SimCard

        payload = item['payload']
        data = payload.get('data', {})
        modo = item['preparar_maestros']
        estados = self._estados_inventario()
        hoy = timezone.now().date()

        if modo == 'mantenimiento_completo':
            cli_man = data.get('clienteParaMantenimiento', {})
            codigo = str(cli_man.get('NROCLIENTE') or data.get('cliente') or '')
            cliente = Cliente.objects.filter(numero_cliente=codigo).first()
            if not cliente:
                self.stdout.write(self.style.WARNING(f'  Cliente {codigo} no encontrado; omitiendo maestros completos'))
                return

            serie_med = str(cli_man.get('NROAPARATO') or '')
            serie_modem = str(data.get('numeroModemDejado') or data.get('numeroDeModemEncontrado') or '')
            ip_sim = str(data.get('iPDejada') or '').replace(' ', '')

            if serie_med and cliente.meter_serial_n_1 != serie_med:
                cliente.meter_serial_n_1 = serie_med
                cliente.save(update_fields=['meter_serial_n_1'])

            Medidor.objects.get_or_create(
                serie=serie_med,
                defaults={
                    'marca': cli_man.get('MARCAAPARATO', ''),
                    'tipo_medidor': 'DIRECTO',
                    'estado_inventario': estados['Instalado'],
                    'cliente': cliente,
                    'fecha_recepcion': hoy,
                    'observaciones': 'DEMO MoreApp — medidor CENCOSUD',
                },
            )
            Modem.objects.get_or_create(
                serie=serie_modem,
                defaults={
                    'marca': data.get('marcaDeModemDejado', 'Teltonika'),
                    'modelo': 'TRB140',
                    'imei': f'DEMO-MORE-MOD-{serie_modem}',
                    'estado_inventario': estados['Instalado'],
                    'cliente': cliente,
                    'ip': ip_sim,
                    'puerto': str(data.get('puertoDejado') or ''),
                    'fecha_recepcion': hoy,
                    'observaciones': 'DEMO MoreApp — módem CENCOSUD',
                },
            )
            SimCard.objects.get_or_create(
                imei=f'DEMO-MORE-SIM-{ip_sim.replace(".", "")}',
                defaults={
                    'operador': 'ENTEL',
                    'direccion_ip': ip_sim,
                    'estado_inventario': estados['Instalado'],
                    'cliente': cliente,
                    'fecha_recepcion': hoy,
                },
            )
            self.stdout.write(f'  Maestros listos para cliente {codigo} (medidor/módem/SIM)')

        elif modo == 'solo_cliente_proverde':
            cli_man = data.get('clienteParaMantenimiento', {})
            codigo = str(data.get('cliente') or cli_man.get('NROCLIENTE') or '')
            Cliente.objects.get_or_create(
                numero_cliente=codigo,
                defaults={
                    'customer_name': cli_man.get('NOMBRE', 'PROVERDE S.A.'),
                    'direccion': cli_man.get('DIRECCION', ''),
                    'comuna': cli_man.get('COMUNA', ''),
                    'installation_address': cli_man.get('DIRECCION', ''),
                    'note': 'DEMO MoreApp — cliente sin inventario cargado',
                    'activo': True,
                },
            )
            self.stdout.write(f'  Cliente demo {codigo} creado (sin equipos en inventario)')

        elif modo == 'solo_cliente_incidencia':
            codigo = str(data.get('cliente') or '')
            Cliente.objects.get_or_create(
                numero_cliente=codigo,
                defaults={
                    'customer_name': f'Cliente demo incidencia {codigo}',
                    'note': 'DEMO MoreApp — incidencia terreno',
                    'activo': True,
                },
            )
            self.stdout.write(f'  Cliente demo {codigo} para incidencia')

        elif modo == 'registro_medidores':
            buscar = data.get('buscarCliente', {})
            codigo = str(data.get('cliente') or buscar.get('CLIENTE1') or '')
            cliente, _ = Cliente.objects.get_or_create(
                numero_cliente=codigo,
                defaults={
                    'customer_name': buscar.get('NOMBRE', 'CONDOMINO DEMO'),
                    'direccion': buscar.get('DIRECCION', ''),
                    'comuna': buscar.get('COMUNA', ''),
                    'installation_address': buscar.get('DIRECCION', ''),
                    'note': 'DEMO MoreApp — registro medidores',
                    'activo': True,
                },
            )
            serie_med = str(data.get('numeroDeMedidorDejado') or '')
            serie_modem = str(data.get('numeroDeModem1') or '')
            if serie_med:
                Medidor.objects.get_or_create(
                    serie=serie_med,
                    defaults={
                        'marca': (data.get('marcaDeMedidorDejado') or 'EMH').strip(),
                        'tipo_medidor': 'DIRECTO',
                        'estado_inventario': estados['En bodega'],
                        'fecha_recepcion': hoy,
                        'observaciones': 'DEMO MoreApp — medidor instalación',
                    },
                )
            if serie_modem:
                Modem.objects.get_or_create(
                    serie=serie_modem,
                    defaults={
                        'marca': 'Teltonika',
                        'imei': f'DEMO-MORE-MOD-{serie_modem}',
                        'estado_inventario': estados['En bodega'],
                        'fecha_recepcion': hoy,
                        'observaciones': 'DEMO MoreApp — módem instalación',
                    },
                )
            if serie_med:
                cliente.meter_serial_n_1 = serie_med
                cliente.save(update_fields=['meter_serial_n_1'])
            self.stdout.write(f'  Maestros registro medidores para cliente {codigo}')

    def _crear_ot_demo(self, item: Dict[str, Any]):
        from clientes.models import Cliente
        from ordenes_trabajo.models import OrdenTrabajo
        from usuarios.models import Usuario

        data = item['payload'].get('data', {})
        cli_man = data.get('clienteParaMantenimiento', {})
        codigo = str(cli_man.get('NROCLIENTE') or data.get('cliente') or '')
        cliente = Cliente.objects.filter(numero_cliente=codigo).first()
        if not cliente:
            return

        tecnico = Usuario.objects.filter(rol='TECNICO').first()
        creador = (
            Usuario.objects.filter(rol='ADMIN').first()
            or Usuario.objects.filter(is_superuser=True).first()
            or Usuario.objects.first()
        )
        if not creador:
            self.stdout.write(self.style.WARNING('  Sin usuarios en BD; OT demo omitida'))
            return
        titulo = f'OT prueba — MoreApp {cliente.customer_name or codigo}'
        if OrdenTrabajo.objects.filter(titulo=titulo, cliente=cliente).exists():
            return

        OrdenTrabajo.objects.create(
            titulo=titulo,
            descripcion='Orden de demostración para vincular informe MoreApp desde terreno.',
            tipo_trabajo='MANTENCION',
            cliente=cliente,
            estado='EN_EJECUCION',
            tecnico_responsable=tecnico,
            creada_por=creador,
            fecha_creacion=timezone.now(),
        )
        self.stdout.write(f'  OT demo creada para {codigo}')

    def _guardar_en_registros(self, payload: Dict[str, Any], item: Dict[str, Any]) -> str:
        base = getattr(settings, 'MOREAPP_REGISTROS_DIR', os.path.join(settings.BASE_DIR, 'Registros'))
        customer_id = item['customer_id']
        form_name = item['form_name']
        correlativo = item['correlativo']
        dest_dir = os.path.join(base, customer_id, form_name, correlativo)
        os.makedirs(dest_dir, exist_ok=True)
        json_path = os.path.join(dest_dir, 'registration.json')
        with open(json_path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return dest_dir
