from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q


class Command(BaseCommand):
    help = 'Elimina datos de ejemplo de OT/inventario sin tocar clientes importados ni auditoría.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se eliminaría sin borrar nada.',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Confirmar eliminación sin preguntar.',
        )
        parser.add_argument(
            '--incluir-moreapp',
            action='store_true',
            help='Elimina registros IntegracionMoreApp de prueba.',
        )

    def _conteo_reportes(self):
        from reportes.services import REPORT_CATALOG, run_report

        return {slug: len(run_report(slug, {})[1]) for slug in REPORT_CATALOG}

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        incluir_moreapp = options['incluir_moreapp']
        auto_confirm = options['yes']

        from ordenes_trabajo.models import (
            AdjuntoOrden,
            InformeCliente,
            IntegracionMoreApp,
            OrdenTrabajo,
        )
        from inventario.models import Medidor, Modem, SimCard
        from clientes.models import Cliente

        resumen = []

        ot_qs = OrdenTrabajo.objects.filter(
            Q(titulo__icontains='MoreApp')
            | Q(titulo__icontains='ejemplo')
            | Q(titulo__icontains='prueba')
            | Q(titulo__icontains='demo')
            | Q(titulo__istartswith='OT ')
            | Q(titulo__istartswith='Trabajo —')
        )
        resumen.append(('Órdenes de trabajo de ejemplo', ot_qs.count()))

        clientes_qs = Cliente.objects.filter(
            Q(numero_cliente__icontains='CLI-OT')
            | Q(numero_cliente__icontains='CLI-VAL')
            | Q(numero_cliente__icontains='CLI-SYNC')
            | Q(numero_cliente__icontains='EJEMPLO')
        )
        resumen.append(('Clientes de prueba', clientes_qs.count()))

        modems_qs = Modem.objects.filter(
            Q(observaciones__icontains='prueba')
            | Q(serie__istartswith='MOD-')
        )
        resumen.append(('Módems generados de prueba', modems_qs.count()))

        sims_qs = SimCard.objects.filter(imei__regex=r'^35\d{10}$')
        resumen.append(('SIM con IMEI aleatorio (35...)', sims_qs.count()))

        medidores_test_qs = Medidor.objects.filter(
            Q(serie__icontains='TEST')
            | Q(serie__istartswith='MED-TEST')
            | Q(serie='NONE_TEST')
        )
        resumen.append(('Medidores de prueba', medidores_test_qs.count()))

        if incluir_moreapp:
            resumen.append(('Registros MoreApp', IntegracionMoreApp.objects.count()))

        self.stdout.write('Resumen de limpieza (no afecta clientes importados ni auditoría):')
        for etiqueta, cantidad in resumen:
            self.stdout.write(f'  - {etiqueta}: {cantidad}')

        reportes = self._conteo_reportes()
        con_datos = {slug: n for slug, n in reportes.items() if n > 0}
        self.stdout.write('\nReportes operativos con filas:')
        if con_datos:
            for slug, n in con_datos.items():
                self.stdout.write(f'  - {slug}: {n}')
        else:
            self.stdout.write('  (todos vacíos — correcto si no hay OT ni MoreApp procesado)')

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run: no se eliminó nada.'))
            return

        if not any(c for _, c in resumen if c > 0):
            self.stdout.write(self.style.SUCCESS(
                'No hay datos de ejemplo que borrar. '
                'Los reportes operativos ya no usan fichas importadas.'
            ))
            return

        confirmar = auto_confirm
        if not confirmar:
            confirmar = input('¿Confirmar eliminación? [s/N]: ').strip().lower() in ('s', 'si', 'sí', 'y', 'yes')
        if not confirmar:
            self.stdout.write(self.style.WARNING('Operación cancelada.'))
            return

        with transaction.atomic():
            ot_ids = list(ot_qs.values_list('pk', flat=True))
            if ot_ids:
                AdjuntoOrden.objects.filter(orden_id__in=ot_ids).delete()
                InformeCliente.objects.filter(orden_id__in=ot_ids).delete()
                IntegracionMoreApp.objects.filter(orden_id__in=ot_ids).update(orden=None)
                deleted_ot, _ = ot_qs.delete()
                self.stdout.write(self.style.SUCCESS(f'Órdenes eliminadas: {deleted_ot}'))

            if incluir_moreapp:
                deleted_ma, _ = IntegracionMoreApp.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f'Registros MoreApp eliminados: {deleted_ma}'))

            if modems_qs.exists():
                deleted_mod, _ = modems_qs.delete()
                self.stdout.write(self.style.SUCCESS(f'Módems de prueba eliminados: {deleted_mod}'))

            if sims_qs.exists():
                deleted_sim, _ = sims_qs.delete()
                self.stdout.write(self.style.SUCCESS(f'SIM de prueba eliminadas: {deleted_sim}'))

            if medidores_test_qs.exists():
                Cliente.objects.filter(
                    medidor_actual_id__in=medidores_test_qs.values_list('pk', flat=True)
                ).update(medidor_actual=None)
                deleted_med, _ = medidores_test_qs.delete()
                self.stdout.write(self.style.SUCCESS(f'Medidores de prueba eliminados: {deleted_med}'))

            if clientes_qs.exists():
                seguros = [
                    cliente.pk for cliente in clientes_qs
                    if not cliente.ordenes.exists()
                ]
                if seguros:
                    deleted_cli, _ = Cliente.objects.filter(pk__in=seguros).delete()
                    self.stdout.write(self.style.SUCCESS(f'Clientes de prueba eliminados: {deleted_cli}'))

        self.stdout.write(self.style.SUCCESS('Limpieza finalizada.'))
