"""
Desactiva clientes cuyo numero_cliente parece una fecha (basura de Excel).

Uso:
    python manage.py limpiar_numeros_cliente_invalidos
    python manage.py limpiar_numeros_cliente_invalidos --aplicar
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from web.services.validators import parece_fecha_numero_cliente


class Command(BaseCommand):
    help = 'Detecta (y opcionalmente desactiva) clientes con numero_cliente tipo fecha'

    def add_arguments(self, parser):
        parser.add_argument(
            '--aplicar',
            action='store_true',
            default=False,
            help='Desactiva (activo=False) los clientes inválidos. Sin este flag solo reporta.',
        )

    def handle(self, *args, **options):
        from clientes.models import Cliente

        aplicar = options['aplicar']
        self.stdout.write(self.style.MIGRATE_HEADING('=== Números de cliente tipo fecha ==='))

        sospechosos = []
        for cliente in Cliente.objects.filter(activo=True).only(
            'id', 'numero_cliente', 'direccion', 'activo', 'fecha_eliminacion', 'eliminado_por_id'
        ):
            if parece_fecha_numero_cliente(cliente.numero_cliente):
                sospechosos.append(cliente)

        if not sospechosos:
            self.stdout.write(self.style.SUCCESS('No hay clientes activos con número tipo fecha.'))
            return

        self.stdout.write(self.style.WARNING(f'Encontrados: {len(sospechosos)}'))
        for cliente in sospechosos[:30]:
            self.stdout.write(
                f'  id={cliente.id} numero={cliente.numero_cliente!r} '
                f'dir={(cliente.direccion or "")[:40]}'
            )
        if len(sospechosos) > 30:
            self.stdout.write(f'  ... y {len(sospechosos) - 30} más')

        if not aplicar:
            self.stdout.write(
                self.style.NOTICE('Modo reporte. Ejecute con --aplicar para desactivarlos.')
            )
            return

        ahora = timezone.now()
        for cliente in sospechosos:
            cliente.activo = False
            cliente.fecha_eliminacion = ahora
            cliente.save(update_fields=['activo', 'fecha_eliminacion'])

        self.stdout.write(
            self.style.SUCCESS(f'Desactivados {len(sospechosos)} cliente(s) con número inválido.')
        )
