"""
Management command para sincronizar registros MoreApp desde carpetas locales.

Uso:
    python manage.py sincronizar_registros
    python manage.py sincronizar_registros --dry-run
    python manage.py sincronizar_registros --base-dir /ruta/alternativa

Diseñado para ejecutarse periódicamente (cron, celery beat, etc.).
"""

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

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        base_dir = options.get('base_dir')

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo DRY-RUN — no se guardará nada'))

        self.stdout.write(f'Leyendo registros desde: {base_dir or "settings.MOREAPP_REGISTROS_DIR"}')

        stats = leer_carpetas(base_dir=base_dir, dry_run=dry_run)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'  Nuevos:      {stats["nuevos"]}'))
        self.stdout.write(f'  Duplicados:  {stats["duplicados"]}')
        self.stdout.write(f'  Alertas:     {stats["alertas"]}')
        if stats['errores']:
            self.stdout.write(self.style.ERROR(f'  Errores:     {stats["errores"]}'))
        else:
            self.stdout.write(f'  Errores:     {stats["errores"]}')
        self.stdout.write(f'  Omitidos:    {stats["omitidos"]}')
        self.stdout.write('')
        self.stdout.write(f'  Base dir:    {stats["base_dir"]}')

        # Detalle de errores si los hay
        for item in stats.get('detalle', []):
            if item.get('resultado') == 'error':
                self.stdout.write(
                    self.style.ERROR(f'  ERROR: {item["json_path"]} — {item["mensaje"]}')
                )
