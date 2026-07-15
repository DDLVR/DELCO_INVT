"""
Management command para sincronizar registros MoreApp desde carpetas locales.

Uso:
    python manage.py sincronizar_registros
    python manage.py sincronizar_registros --dry-run
    python manage.py sincronizar_registros --base-dir /ruta/alternativa
    python manage.py sincronizar_registros --limite-web

Diseñado para ejecutarse periódicamente (cron). En producción preferir --limite-web
para no saturar el host en una corrida larga.
"""

from typing import Optional, cast

from django.conf import settings
from django.core.management.base import BaseCommand

from integraciones.reader import leer_carpetas


class Command(BaseCommand):
    help = 'Escanea las carpetas de MoreApp y registra submissions nuevos en la BD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Detecta carpetas pero NO guarda nada en la base de datos',
        )
        parser.add_argument(
            '--base-dir',
            type=str,
            default=None,
            help='Ruta raíz de los registros (sobreescribe MOREAPP_REGISTROS_DIR de settings)',
        )
        parser.add_argument(
            '--limite-web',
            action='store_true',
            help=(
                'Aplica MOREAPP_WEB_SYNC_MAX_SEGUNDOS / MAX_ARCHIVOS y omite '
                'reproceso de duplicados (recomendado en cron de producción).'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        base_dir = cast(Optional[str], options.get('base_dir'))
        limite_web = bool(options.get('limite_web'))

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo DRY-RUN — no se guardará nada'))

        self.stdout.write(f'Leyendo registros desde: {base_dir or "settings.MOREAPP_REGISTROS_DIR"}')

        kwargs = {'base_dir': base_dir, 'dry_run': dry_run}
        if limite_web:
            kwargs['max_segundos'] = getattr(settings, 'MOREAPP_WEB_SYNC_MAX_SEGUNDOS', 30)
            kwargs['max_archivos'] = getattr(settings, 'MOREAPP_WEB_SYNC_MAX_ARCHIVOS', 40)
            kwargs['reprocesar_duplicados'] = not getattr(
                settings, 'MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS', True
            )
            self.stdout.write(
                f'Límites web: max_segundos={kwargs["max_segundos"]} '
                f'max_archivos={kwargs["max_archivos"]}'
            )

        stats = leer_carpetas(**kwargs)

        if not dry_run and isinstance(stats, dict):
            try:
                from web.moreapp_ops import registrar_resultado_sync
                registrar_resultado_sync(stats, origen='cron' if limite_web else 'comando')
            except Exception:
                pass

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'  Nuevos:      {stats["nuevos"]}'))
        self.stdout.write(f'  Duplicados:  {stats["duplicados"]}')
        self.stdout.write(f'  Alertas:     {stats["alertas"]}')
        if stats['errores']:
            self.stdout.write(self.style.ERROR(f'  Errores:     {stats["errores"]}'))
        else:
            self.stdout.write(f'  Errores:     {stats["errores"]}')
        self.stdout.write(f'  Omitidos:    {stats["omitidos"]}')
        if stats.get('incompleto'):
            self.stdout.write(self.style.WARNING(
                f'  Incompleto:  sí ({stats.get("motivo_corte") or "límite"})'
            ))
        self.stdout.write('')
        self.stdout.write(f'  Base dir:    {stats["base_dir"]}')

        for item in stats.get('detalle', []):
            if item.get('resultado') == 'error':
                self.stdout.write(
                    self.style.ERROR(f'  ERROR: {item["json_path"]} — {item["mensaje"]}')
                )
            elif item.get('error'):
                self.stdout.write(self.style.ERROR(f'  ERROR: {item["error"]}'))

        if int(stats.get('errores') or 0) > 0:
            raise SystemExit(1)
