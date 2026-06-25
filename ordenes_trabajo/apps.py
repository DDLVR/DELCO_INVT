from django.apps import AppConfig


class OrdenesTrabajoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ordenes_trabajo'

    def ready(self):
        from .models import OrdenTrabajo

        if hasattr(OrdenTrabajo, 'puede_editar_observaciones_tecnicas'):
            return

        def puede_editar_observaciones_tecnicas(self, usuario):
            if usuario.rol in ['ADMIN', 'ADMINISTRATIVO']:
                return True
            if usuario.rol == 'TECNICO' and usuario == self.tecnico_responsable:
                return True
            return False

        OrdenTrabajo.puede_editar_observaciones_tecnicas = puede_editar_observaciones_tecnicas