"""Sincroniza el estado de tareas enviadas contra la API de MoreApp."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Marca como completadas las tareas MoreApp que la API reporta cerradas"

    def handle(self, *args, **options):
        from integraciones.moreapp_tareas_ciclo import sincronizar_tareas_desde_api

        stats = sincronizar_tareas_desde_api()
        self.stdout.write(
            "Revisadas: %s · Completadas: %s · Errores API: %s"
            % (stats["revisadas"], stats["completadas"], stats["errores"])
        )
