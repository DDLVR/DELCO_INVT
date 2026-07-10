"""
Carga registros MoreApp de referencia desde el ZIP de ejemplo (MoreApp).

Pensado para Fase 1: subconjunto pequeño hoy, ampliar después sin rehacer el flujo.
Alineado al PDF puntos 5, 6, 8, 9, 12 y 15 (OT, terreno, integración, reportes, auditoría).

Uso:
    python manage.py cargar_demo_moreapp --limpiar
    python manage.py cargar_demo_moreapp --perfil subconjunto
    python manage.py cargar_demo_moreapp --correlativos 212,208,1184
    python manage.py cargar_demo_moreapp --por-formulario 3 --ampliar
    python manage.py cargar_demo_moreapp --dry-run --perfil subconjunto
"""

from __future__ import annotations

import copy
import json
import os
import uuid
import zipfile
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from integraciones.reader import procesar_payload_moreapp

DEMO_SUBMISSION_PREFIX = 'demo-ref-'
DEFAULT_ZIP = r'c:\Users\DELCOCHILE\Downloads\Mantenimiento_Telemetria_V3.zip'

# Perfil mínimo original (4 escenarios didácticos)
PERFIL_MINIMO = [
    {
        'correlativo': '212',
        'etiqueta': 'Mantenimiento ejecutado (completo + OT)',
        'preparar_maestros': 'mantenimiento_completo',
        'crear_ot': True,
        'pdf': '5,6,8,12,15',
    },
    {
        'correlativo': '208',
        'etiqueta': 'Mantenimiento — cliente sin inventario',
        'preparar_maestros': 'solo_cliente_proverde',
        'crear_ot': False,
        'pdf': '4,6,15',
    },
    {
        'correlativo': '220',
        'etiqueta': 'Mantenimiento — incidencia terreno',
        'preparar_maestros': 'solo_cliente_incidencia',
        'crear_ot': False,
        'pdf': '6,7',
    },
    {
        'correlativo': '1184',
        'etiqueta': 'Registro medidores — instalación',
        'preparar_maestros': 'registro_medidores',
        'crear_ot': False,
        'pdf': '6,8,9',
    },
]

# Subconjunto de referencia (~10): cubre éxito, advertencias, incidencias y ambos formularios
PERFIL_SUBCONJUNTO = PERFIL_MINIMO + [
    {
        'correlativo': '235',
        'etiqueta': 'Mantenimiento ejecutado adicional',
        'preparar_maestros': 'auto_json',
        'crear_ot': False,
        'pdf': '6,9',
    },
    {
        'correlativo': '216',
        'etiqueta': 'Mantenimiento — incidencia coordinar ingreso',
        'preparar_maestros': 'auto_json',
        'crear_ot': False,
        'pdf': '6,7',
    },
    {
        'correlativo': '1154',
        'etiqueta': 'Registro medidores — referencia 2',
        'preparar_maestros': 'auto_json',
        'crear_ot': False,
        'pdf': '6,9',
    },
    {
        'correlativo': '1172',
        'etiqueta': 'Registro medidores — referencia 3',
        'preparar_maestros': 'auto_json',
        'crear_ot': False,
        'pdf': '6,9',
    },
    {
        'correlativo': '1195',
        'etiqueta': 'Registro medidores — referencia 4',
        'preparar_maestros': 'auto_json',
        'crear_ot': False,
        'pdf': '6,9',
    },
]

PERFILES = {
    'minimo': PERFIL_MINIMO,
    'subconjunto': PERFIL_SUBCONJUNTO,
}


class Command(BaseCommand):
    help = 'Carga subconjunto del ZIP MoreApp de referencia (ampliable después)'

    def add_arguments(self, parser):
        parser.add_argument('--zip', type=str, default=DEFAULT_ZIP, help='Ruta al ZIP MoreApp')
        parser.add_argument(
            '--perfil',
            type=str,
            default='subconjunto',
            choices=sorted(PERFILES.keys()),
            help='minimo=4 casos | subconjunto=~9 casos (default)',
        )
        parser.add_argument(
            '--correlativos',
            type=str,
            default='',
            help='Lista explícita: 212,208,1184 (sobreescribe --perfil)',
        )
        parser.add_argument(
            '--por-formulario',
            type=int,
            default=0,
            help='Tomar N registros por formulario del ZIP (ordenados por correlativo)',
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Borra solo datos demo-ref antes de cargar',
        )
        parser.add_argument(
            '--ampliar',
            action='store_true',
            help='No limpia; solo carga correlativos que aún no están en BD',
        )
        parser.add_argument('--dry-run', action='store_true', help='Solo lista qué se cargaría')

    def handle(self, *args, **options):
        zip_path = options['zip']
        dry_run = options['dry_run']
        ampliar = options['ampliar']

        if not os.path.isfile(zip_path):
            self.stdout.write(self.style.ERROR(f'ZIP no encontrado: {zip_path}'))
            return

        if options['limpiar'] and not dry_run and not ampliar:
            self._limpiar_demo_anterior()

        casos = self._resolver_casos(options)
        payloads = self._extraer_payloads_desde_zip(zip_path, casos, solo_nuevos=ampliar)

        if not payloads:
            self.stdout.write(self.style.WARNING('Nada que cargar (¿ya están todos o correlativos inválidos?).'))
            return

        self.stdout.write(f'ZIP: {zip_path}')
        self.stdout.write(f'Registros a procesar: {len(payloads)}')

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run — no se guardará nada'))
            for item in payloads:
                self.stdout.write(
                    f"  [{item['correlativo']}] {item['etiqueta']} | PDF {item.get('pdf', '—')}"
                )
            return

        resultados = []
        with transaction.atomic():
            for item in payloads:
                self._preparar_maestros(item)
                if item.get('crear_ot'):
                    self._crear_ot_demo(item)
                ruta = self._guardar_en_registros(item['payload'], item)
                resultado = procesar_payload_moreapp(item['payload'], ruta_context=ruta)
                from ordenes_trabajo.models import IntegracionMoreApp

                reg = IntegracionMoreApp.objects.filter(
                    moreapp_submission_id=item['payload']['id'],
                ).first()
                if reg and str(item.get('correlativo', '')).isdigit():
                    reg.numero_correlativo = int(item['correlativo'])
                    reg.save(update_fields=['numero_correlativo'])
                merged = {**item, **resultado, 'submission_id': item['payload']['id']}
                merged['correlativo'] = item['correlativo']
                resultados.append(merged)

        self._imprimir_resumen(resultados)

    def _resolver_casos(self, options) -> List[Dict[str, Any]]:
        if options.get('correlativos'):
            corrs = [c.strip() for c in options['correlativos'].split(',') if c.strip()]
            return [
                {
                    'correlativo': c,
                    'etiqueta': f'Registro referencia {c}',
                    'preparar_maestros': 'auto_json',
                    'crear_ot': c == '212',
                }
                for c in corrs
            ]

        casos = list(PERFILES[options['perfil']])

        n_por_form = int(options.get('por_formulario') or 0)
        if n_por_form > 0:
            casos.extend(self._casos_extra_por_formulario(options['zip'], n_por_form, casos))

        return casos

    def _casos_extra_por_formulario(
        self, zip_path: str, n: int, ya_definidos: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Añade correlativos del ZIP no incluidos ya en el perfil."""
        existentes = {str(c['correlativo']) for c in ya_definidos}
        extra: List[Dict[str, Any]] = []
        por_form: Dict[str, List[str]] = {}

        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.endswith('registration.json'):
                    continue
                parts = name.replace('\\', '/').split('/')
                if len(parts) < 3:
                    continue
                form_folder, corr = parts[0], parts[-2]
                if not corr.isdigit() or corr in existentes:
                    continue
                por_form.setdefault(form_folder, []).append(corr)

        for form_folder, corrs in por_form.items():
            for corr in sorted(corrs, key=int)[:n]:
                if corr in existentes:
                    continue
                existentes.add(corr)
                extra.append({
                    'correlativo': corr,
                    'etiqueta': f'Extra {form_folder[:24]}… #{corr}',
                    'preparar_maestros': 'auto_json',
                    'crear_ot': False,
                    'pdf': '6,9',
                })
        return extra

    def _limpiar_demo_anterior(self):
        from inventario.models import Medidor, Modem, SimCard
        from ordenes_trabajo.models import IntegracionMoreApp, OrdenTrabajo

        demo_qs = IntegracionMoreApp.objects.filter(
            moreapp_submission_id__startswith=DEMO_SUBMISSION_PREFIX,
        ) | IntegracionMoreApp.objects.filter(
            moreapp_submission_id__startswith='demo-prueba-',
        )
        n_ma, _ = demo_qs.delete()
        self.stdout.write(f'  Registros MoreApp demo eliminados: {n_ma}')

        ot_qs = OrdenTrabajo.objects.filter(titulo__icontains='prueba — MoreApp')
        if ot_qs.exists():
            IntegracionMoreApp.objects.filter(orden_id__in=ot_qs.values_list('pk', flat=True)).update(orden=None)
            n_ot, _ = ot_qs.delete()
            self.stdout.write(f'  OT demo eliminadas: {n_ot}')

        for qs, label in (
            (Medidor.objects.filter(observaciones__icontains='DEMO MoreApp'), 'Medidores'),
            (Modem.objects.filter(observaciones__icontains='DEMO MoreApp'), 'Módems'),
            (SimCard.objects.filter(imei__startswith='DEMO-MORE-'), 'SIM'),
        ):
            if qs.exists():
                n, _ = qs.delete()
                self.stdout.write(f'  {label} demo eliminados: {n}')

        from clientes.models import Cliente

        cli = Cliente.objects.filter(note__icontains='DEMO MoreApp')
        if cli.exists():
            n, _ = cli.delete()
            self.stdout.write(f'  Clientes demo eliminados: {n}')

    def _extraer_payloads_desde_zip(
        self,
        zip_path: str,
        casos: List[Dict[str, Any]],
        solo_nuevos: bool = False,
    ) -> List[Dict[str, Any]]:
        from ordenes_trabajo.models import IntegracionMoreApp

        payloads: List[Dict[str, Any]] = []
        index: Dict[str, str] = {}

        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.endswith('registration.json'):
                    continue
                parts = name.replace('\\', '/').split('/')
                if len(parts) < 3:
                    continue
                index[parts[-2]] = name

            for caso in casos:
                corr = str(caso['correlativo'])
                stable_id = f'{DEMO_SUBMISSION_PREFIX}{corr}'

                if solo_nuevos and IntegracionMoreApp.objects.filter(
                    moreapp_submission_id=stable_id,
                ).exists():
                    continue

                path = index.get(corr)
                if not path:
                    self.stdout.write(self.style.WARNING(f'  Correlativo {corr} no encontrado en ZIP'))
                    continue

                raw = json.loads(zf.read(path))
                payload = copy.deepcopy(raw)
                payload['id'] = stable_id
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

    def _codigo_cliente_desde_payload(self, data: dict) -> str:
        buscar = data.get('buscarCliente') or {}
        cli_man = data.get('clienteParaMantenimiento') or {}
        return str(
            data.get('cliente')
            or cli_man.get('NROCLIENTE')
            or buscar.get('CLIENTE1')
            or buscar.get('NROCLIENTE')
            or ''
        ).strip()

    def _preparar_maestros(self, item: Dict[str, Any]):
        from clientes.models import Cliente
        from inventario.models import Medidor, Modem, SimCard

        payload = item['payload']
        data = payload.get('data', {})
        modo = item.get('preparar_maestros', 'auto_json')
        estados = self._estados_inventario()
        hoy = timezone.now().date()

        if modo == 'auto_json':
            self._preparar_auto_json(data, estados, hoy)
            return

        if modo == 'mantenimiento_completo':
            cli_man = data.get('clienteParaMantenimiento', {})
            codigo = self._codigo_cliente_desde_payload(data)
            cliente = Cliente.objects.filter(numero_cliente=codigo).first()
            if not cliente:
                self.stdout.write(self.style.WARNING(f'  Cliente {codigo} no en BD; omitiendo maestros completos'))
                return

            serie_med = str(cli_man.get('NROAPARATO') or '')
            serie_modem = str(data.get('numeroModemDejado') or data.get('numeroDeModemEncontrado') or '')
            ip_sim = str(data.get('iPDejada') or '').replace(' ', '')

            if serie_med and cliente.meter_serial_n_1 != serie_med:
                cliente.meter_serial_n_1 = serie_med
                cliente.save(update_fields=['meter_serial_n_1'])

            if serie_med:
                Medidor.objects.get_or_create(
                    serie=serie_med,
                    defaults={
                        'marca': cli_man.get('MARCAAPARATO', ''),
                        'tipo_medidor': 'DIRECTO',
                        'estado_inventario': estados['Instalado'],
                        'cliente': cliente,
                        'fecha_recepcion': hoy,
                        'observaciones': 'DEMO MoreApp — medidor referencia',
                    },
                )
            if serie_modem:
                Modem.objects.get_or_create(
                    serie=serie_modem,
                    defaults={
                        'marca': data.get('marcaDeModemDejado', 'Teltonika'),
                        'imei': f'DEMO-MORE-MOD-{serie_modem}',
                        'estado_inventario': estados['Instalado'],
                        'cliente': cliente,
                        'ip': ip_sim,
                        'puerto': str(data.get('puertoDejado') or ''),
                        'fecha_recepcion': hoy,
                        'observaciones': 'DEMO MoreApp — módem referencia',
                    },
                )
            if ip_sim and ip_sim.count('.') >= 3:
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
            self.stdout.write(f'  Maestros completos: cliente {codigo}')

        elif modo == 'solo_cliente_proverde':
            cli_man = data.get('clienteParaMantenimiento', {})
            codigo = self._codigo_cliente_desde_payload(data)
            Cliente.objects.get_or_create(
                numero_cliente=codigo,
                defaults={
                    'customer_name': cli_man.get('NOMBRE', 'PROVERDE S.A.'),
                    'direccion': cli_man.get('DIRECCION', ''),
                    'comuna': cli_man.get('COMUNA', ''),
                    'installation_address': cli_man.get('DIRECCION', ''),
                    'note': 'DEMO MoreApp — cliente sin inventario',
                    'activo': True,
                },
            )
            self.stdout.write(f'  Cliente demo {codigo} (sin equipos)')

        elif modo == 'solo_cliente_incidencia':
            codigo = self._codigo_cliente_desde_payload(data)
            Cliente.objects.get_or_create(
                numero_cliente=codigo,
                defaults={
                    'customer_name': f'Cliente demo incidencia {codigo}',
                    'note': 'DEMO MoreApp — incidencia terreno',
                    'activo': True,
                },
            )
            self.stdout.write(f'  Cliente demo {codigo}')

        elif modo == 'registro_medidores':
            buscar = data.get('buscarCliente', {})
            codigo = self._codigo_cliente_desde_payload(data)
            cliente, _ = Cliente.objects.get_or_create(
                numero_cliente=codigo,
                defaults={
                    'customer_name': buscar.get('NOMBRE', 'CONDOMINO DEMO'),
                    'direccion': buscar.get('DIRECCION', ''),
                    'comuna': buscar.get('COMUNA', ''),
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
                cliente.meter_serial_n_1 = serie_med
                cliente.save(update_fields=['meter_serial_n_1'])
            if serie_modem:
                Modem.objects.get_or_create(
                    serie=serie_modem,
                    defaults={
                        'imei': f'DEMO-MORE-MOD-{serie_modem}',
                        'estado_inventario': estados['En bodega'],
                        'fecha_recepcion': hoy,
                        'observaciones': 'DEMO MoreApp — módem instalación',
                    },
                )
            self.stdout.write(f'  Registro medidores: cliente {codigo}')

    def _preparar_auto_json(self, data: dict, estados, hoy):
        """Cliente desde JSON; equipos solo si vienen en el formulario (puede quedar CON_ADVERTENCIA)."""
        from clientes.models import Cliente
        from inventario.models import Medidor, Modem

        buscar = data.get('buscarCliente') or {}
        cli_man = data.get('clienteParaMantenimiento') or {}
        codigo = self._codigo_cliente_desde_payload(data)
        if not codigo:
            return

        nombre = (
            cli_man.get('NOMBRE')
            or buscar.get('NOMBRE')
            or f'Cliente referencia {codigo}'
        )
        Cliente.objects.get_or_create(
            numero_cliente=codigo,
            defaults={
                'customer_name': nombre,
                'direccion': cli_man.get('DIRECCION') or buscar.get('DIRECCION', ''),
                'comuna': cli_man.get('COMUNA') or buscar.get('COMUNA', ''),
                'note': 'DEMO MoreApp — referencia ZIP',
                'activo': True,
            },
        )

        serie_med = str(
            cli_man.get('NROAPARATO')
            or data.get('numeroDeMedidorDejado')
            or ''
        )
        serie_modem = str(
            data.get('numeroModemDejado')
            or data.get('numeroDeModem1')
            or ''
        )
        if serie_med and serie_med.isdigit():
            Medidor.objects.get_or_create(
                serie=serie_med,
                defaults={
                    'tipo_medidor': 'DIRECTO',
                    'estado_inventario': estados['En bodega'],
                    'fecha_recepcion': hoy,
                    'observaciones': 'DEMO MoreApp — auto ZIP',
                },
            )
        if serie_modem and serie_modem.isdigit():
            Modem.objects.get_or_create(
                serie=serie_modem,
                defaults={
                    'imei': f'DEMO-MORE-MOD-{serie_modem}',
                    'estado_inventario': estados['En bodega'],
                    'fecha_recepcion': hoy,
                    'observaciones': 'DEMO MoreApp — auto ZIP',
                },
            )

    def _crear_ot_demo(self, item: Dict[str, Any]):
        from clientes.models import Cliente
        from ordenes_trabajo.models import OrdenTrabajo
        from usuarios.models import Usuario

        codigo = self._codigo_cliente_desde_payload(item['payload'].get('data', {}))
        cliente = Cliente.objects.filter(numero_cliente=codigo).first()
        if not cliente:
            return

        titulo = f'OT prueba — MoreApp {cliente.customer_name or codigo}'
        if OrdenTrabajo.objects.filter(titulo=titulo, cliente=cliente).exists():
            return

        creador = (
            Usuario.objects.filter(rol='ADMIN').first()
            or Usuario.objects.filter(is_superuser=True).first()
            or Usuario.objects.first()
        )
        if not creador:
            return

        OrdenTrabajo.objects.create(
            titulo=titulo,
            descripcion='OT de referencia — flujo Delco → técnico → MoreApp → validación.',
            tipo_trabajo='MANTENCION',
            cliente=cliente,
            estado='EN_EJECUCION',
            tecnico_responsable=Usuario.objects.filter(rol='TECNICO').first(),
            creada_por=creador,
        )
        self.stdout.write(f'  OT referencia para {codigo}')

    def _guardar_en_registros(self, payload: Dict[str, Any], item: Dict[str, Any]) -> str:
        base = getattr(settings, 'MOREAPP_REGISTROS_DIR', os.path.join(settings.BASE_DIR, 'Registros'))
        dest_dir = os.path.join(
            base,
            item['customer_id'],
            item['form_name'],
            str(item['correlativo']),
        )
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, 'registration.json'), 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return dest_dir

    def _imprimir_resumen(self, resultados: List[Dict[str, Any]]):
        from ordenes_trabajo.models import IntegracionMoreApp

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Referencia MoreApp cargada. Revisar:'))
        self.stdout.write('  • /ordenes/  (colas operativas)')
        self.stdout.write('  • /reportes/moreapp/')
        self.stdout.write('  • /operacional/pendientes/')
        self.stdout.write('  • /reportes/')
        self.stdout.write('')
        revisados = advertencias = 0
        for r in resultados:
            reg = IntegracionMoreApp.objects.filter(moreapp_submission_id=r['submission_id']).first()
            revision = reg.estado_revision if reg else '?'
            if revision == 'REVISADO':
                revisados += 1
            elif revision == 'CON_ADVERTENCIA':
                advertencias += 1
            orden = f'OT #{reg.orden_id}' if reg and reg.orden_id else 'sin OT'
            estilo = self.style.SUCCESS if revision == 'REVISADO' else self.style.WARNING
            self.stdout.write(estilo(
                f"  [{r['correlativo']}] {r['etiqueta']}: {revision} | {orden} | PDF {r.get('pdf', '—')}"
            ))
        self.stdout.write('')
        self.stdout.write(f'  Revisados: {revisados} | Con advertencia: {advertencias}')
        self.stdout.write('  Para ampliar: python manage.py cargar_demo_moreapp --por-formulario 5 --ampliar')
