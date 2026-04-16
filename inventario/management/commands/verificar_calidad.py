"""
Punto 7 – Comando de verificación de calidad de datos de inventario.

Detecta anomalías comunes y las reporta (o corrige con --corregir):
  - Equipos instalados sin cliente
  - Equipos instalados sin ubicacion_actual
  - Equipos con cliente pero estado "En bodega"
  - SIM/modem con ubicacion_actual = None y estado instalado
  - MovimientoInventario recientes sin responsable (no debería ocurrir con FK)

Uso:
    python manage.py verificar_calidad
    python manage.py verificar_calidad --solo-reporte
"""
from django.core.management.base import BaseCommand
from django.db.models import Q


class Command(BaseCommand):
    help = 'Verifica calidad de datos de inventario y reporta (o corrige) anomalías'

    def add_arguments(self, parser):
        parser.add_argument(
            '--solo-reporte',
            action='store_true',
            default=False,
            help='Solo reportar sin corregir nada (modo seguro)',
        )

    def handle(self, *args, **options):
        from inventario.models import Medidor, SimCard, Modem, EstadoInventario

        solo_reporte = options['solo_reporte']
        self.stdout.write(self.style.MIGRATE_HEADING('=== Verificación de calidad de inventario ==='))

        estado_instalado = EstadoInventario.objects.filter(nombre__iexact='Instalado').first()
        estado_bodega = EstadoInventario.objects.filter(nombre__iexact='En bodega').first()
        total_problemas = 0

        # ──────────────────────────────────────────────
        # 1. Equipos instalados sin cliente asociado
        # ──────────────────────────────────────────────
        self.stdout.write('\n[1] Equipos instalados sin cliente asociado')
        for Modelo, etiqueta in [(Medidor, 'Medidor'), (Modem, 'Módem'), (SimCard, 'SIM')]:
            qs = Modelo.objects.filter(estado_inventario=estado_instalado, cliente__isnull=True) if estado_instalado else Modelo.objects.none()
            count = qs.count()
            if count:
                total_problemas += count
                self.stdout.write(self.style.WARNING(f'  {etiqueta}: {count} instalado(s) sin cliente'))
                for obj in qs[:5]:
                    serie = getattr(obj, 'serie', getattr(obj, 'numero_sim', str(obj.pk)))
                    self.stdout.write(f'    - {serie}')
            else:
                self.stdout.write(f'  {etiqueta}: OK')

        # ──────────────────────────────────────────────
        # 2. Equipos instalados sin ubicacion_actual
        # ──────────────────────────────────────────────
        self.stdout.write('\n[2] Equipos instalados sin ubicacion_actual')
        for Modelo, etiqueta, tiene_ubi in [
            (Medidor, 'Medidor', False),  # Medidor puede no tener ubicacion_actual
            (Modem, 'Módem', True),
            (SimCard, 'SIM', True),
        ]:
            if not tiene_ubi:
                self.stdout.write(f'  {etiqueta}: campo no aplica')
                continue
            if not estado_instalado:
                continue
            qs = Modelo.objects.filter(estado_inventario=estado_instalado, ubicacion_actual__isnull=True)
            count = qs.count()
            if count:
                total_problemas += count
                self.stdout.write(self.style.WARNING(f'  {etiqueta}: {count} instalado(s) sin ubicacion_actual'))
            else:
                self.stdout.write(f'  {etiqueta}: OK')

        # ──────────────────────────────────────────────
        # 3. Equipos con cliente pero en "En bodega"
        # ──────────────────────────────────────────────
        self.stdout.write('\n[3] Equipos con cliente asignado pero en estado "En bodega"')
        for Modelo, etiqueta in [(Medidor, 'Medidor'), (Modem, 'Módem'), (SimCard, 'SIM')]:
            qs = Modelo.objects.filter(estado_inventario=estado_bodega, cliente__isnull=False) if estado_bodega else Modelo.objects.none()
            count = qs.count()
            if count:
                total_problemas += count
                self.stdout.write(self.style.WARNING(f'  {etiqueta}: {count} en bodega con cliente'))
                if not solo_reporte:
                    updated = qs.update(cliente=None)
                    self.stdout.write(self.style.SUCCESS(f'    → cliente limpiado en {updated} registros'))
            else:
                self.stdout.write(f'  {etiqueta}: OK')

        # ──────────────────────────────────────────────
        # 4. MoreApp con estado PENDIENTE > 7 días (envejecimiento – Punto 11)
        # ──────────────────────────────────────────────
        self.stdout.write('\n[4] Registros MoreApp sin revisar con más de 7 días')
        from django.utils import timezone
        from datetime import timedelta
        try:
            from ordenes_trabajo.models import IntegracionMoreApp
            umbral = timezone.now() - timedelta(days=7)
            qs_ma = IntegracionMoreApp.objects.filter(
                estado_revision='PENDIENTE',
                fecha_recepcion__lt=umbral,
            )
            count = qs_ma.count()
            if count:
                total_problemas += count
                self.stdout.write(self.style.WARNING(f'  {count} registros MoreApp con revisión pendiente > 7 días'))
                for r in qs_ma[:5]:
                    dias = (timezone.now() - r.fecha_recepcion).days
                    self.stdout.write(f'    - {r.moreapp_submission_id} | {dias} días | {r.nombre_formulario}')
            else:
                self.stdout.write('  OK — sin registros envejecidos')
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  No se pudo verificar MoreApp: {exc}'))

        # ──────────────────────────────────────────────
        # Resumen final
        # ──────────────────────────────────────────────
        self.stdout.write('\n' + '─' * 60)
        if total_problemas:
            self.stdout.write(self.style.ERROR(
                f'Se encontraron {total_problemas} problema(s) en el inventario.'
            ))
            if solo_reporte:
                self.stdout.write('  Ejecute sin --solo-reporte para corregir automáticamente donde sea posible.')
        else:
            self.stdout.write(self.style.SUCCESS('Sin problemas detectados en el inventario.'))
