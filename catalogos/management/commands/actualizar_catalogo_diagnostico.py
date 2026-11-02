from django.core.management.base import BaseCommand

from catalogos.datos_diagnostico import sync_catalogo_diagnostico


class Command(BaseCommand):
    help = "Actualiza el catálogo de diagnóstico al flujo actual (Tareas MoreApp / intranet)."

    def handle(self, *args, **options):
        stats = sync_catalogo_diagnostico()
        self.stdout.write(self.style.SUCCESS(
            "Catálogo diagnóstico: %(creados)s nuevos, %(actualizados)s actualizados, "
            "%(desactivados)s desactivados (%(total)s vigentes)." % stats
        ))
