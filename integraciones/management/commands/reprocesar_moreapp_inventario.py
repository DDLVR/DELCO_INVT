"""
Reprocesa registros MoreApp para aplicar altas/movimientos de inventario.

Uso:
  python manage.py reprocesar_moreapp_inventario
  python manage.py reprocesar_moreapp_inventario --aplicar
  python manage.py reprocesar_moreapp_inventario --aplicar --incluir-descartados
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Reprocesa MoreApp hacia inventario (revive/alta/movimientos MOREAPP)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--aplicar',
            action='store_true',
            default=False,
            help='Ejecuta el reproceso. Sin este flag solo reporta el plan.',
        )
        parser.add_argument(
            '--incluir-descartados',
            action='store_true',
            default=False,
            help='También reprocesa registros DESCARTADO (por defecto se omiten).',
        )
        parser.add_argument(
            '--limite',
            type=int,
            default=0,
            help='Máximo de registros a procesar (0 = todos).',
        )

    def handle(self, *args, **options):
        from ordenes_trabajo.models import IntegracionMoreApp
        from inventario.models import Medidor, Modem, SimCard, MovimientoInventario
        from integraciones.reader import reprocesar_registro_moreapp

        aplicar = options['aplicar']
        incluir_descartados = options['incluir_descartados']
        limite = options['limite'] or 0

        qs = IntegracionMoreApp.objects.filter(eliminado=False).order_by('id')
        if not incluir_descartados:
            qs = qs.exclude(estado_revision='DESCARTADO')

        total = qs.count()
        if limite > 0:
            qs = qs[:limite]

        self.stdout.write(self.style.MIGRATE_HEADING('=== Reproceso MoreApp → inventario ==='))
        self.stdout.write(f'Candidatos: {qs.count()} (universo filtrado: {total})')
        self.stdout.write(
            f'Antes: medidores={Medidor.objects.filter(eliminado=False).count()} '
            f'modems={Modem.objects.filter(eliminado=False).count()} '
            f'sims={SimCard.objects.filter(eliminado=False).count()} '
            f'mov_MOREAPP={MovimientoInventario.objects.filter(origen_sistema="MOREAPP").count()}'
        )

        if not aplicar:
            sin_payload = 0
            for reg in qs:
                data = reg.datos_recibidos if isinstance(reg.datos_recibidos, dict) else {}
                if not data.get('data'):
                    sin_payload += 1
            self.stdout.write(self.style.NOTICE(
                f'Dry-run. Sin payload completo: {sin_payload}. Ejecute con --aplicar.'
            ))
            return

        ok = 0
        fail = 0
        skip = 0
        mov_total = 0
        altas_total = 0
        pendientes_total = 0
        errores = []

        for reg in qs.iterator():
            data = reg.datos_recibidos if isinstance(reg.datos_recibidos, dict) else {}
            if not data.get('data'):
                skip += 1
                continue
            try:
                result = reprocesar_registro_moreapp(reg)
                resumen = result.get('resumen') or {}
                mov = int(resumen.get('movimientos_generados') or 0)
                altas = len(resumen.get('equipos_alta_automatica') or [])
                pend = len(resumen.get('pendientes_revision') or [])
                mov_total += mov
                altas_total += altas
                pendientes_total += pend
                if result.get('success'):
                    ok += 1
                else:
                    fail += 1
                self.stdout.write(
                    f'  #{reg.id} corr={reg.numero_correlativo} '
                    f'success={bool(result.get("success"))} mov={mov} altas={altas} pend={pend}'
                )
            except Exception as exc:
                fail += 1
                errores.append((reg.id, str(exc)))
                self.stdout.write(self.style.ERROR(f'  #{reg.id} ERROR: {exc}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'OK={ok} fail={fail} skip_sin_payload={skip} | '
            f'movimientos_gen={mov_total} altas_auto={altas_total} pendientes={pendientes_total}'
        ))
        self.stdout.write(
            f'Después: medidores={Medidor.objects.filter(eliminado=False).count()} '
            f'modems={Modem.objects.filter(eliminado=False).count()} '
            f'sims={SimCard.objects.filter(eliminado=False).count()} '
            f'mov_MOREAPP={MovimientoInventario.objects.filter(origen_sistema="MOREAPP").count()} '
            f'actualizo_equipos={IntegracionMoreApp.objects.filter(eliminado=False, actualizo_equipos=True).count()}'
        )
        if errores:
            self.stdout.write(self.style.WARNING(f'Errores ({len(errores)}):'))
            for rid, msg in errores[:15]:
                self.stdout.write(f'  #{rid}: {msg}')
