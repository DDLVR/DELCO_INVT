from django.core.management.base import BaseCommand
from inventario.models import EstadoInventario

ESTADOS_ESTANDAR = [
    ('En bodega',     'Equipo disponible en bodega, sin asignar'),
    ('Instalado',     'Equipo instalado en cliente'),
    ('Retirado',      'Equipo retirado de instalación'),
    ('En reparación', 'Equipo en proceso de reparación'),
    ('Dado de baja',  'Equipo dado de baja, fuera de servicio'),
]

# Mapeo de nombres obsoletos → nombre estándar nuevo
MIGRACION_NOMBRES = {
    'BODEGA':     'En bodega',
    'Disponible': 'En bodega',
    'Entregado':  'Instalado',
}


class Command(BaseCommand):
    help = 'Crea los 5 estados estándar y migra registros con nombres obsoletos (BODEGA→En bodega, Disponible→En bodega, Entregado→Instalado)'

    def handle(self, *args, **options):
        from inventario.models import Medidor, SimCard, Modem

        self.stdout.write(self.style.MIGRATE_HEADING('=== Inicializando estados de inventario ==='))

        # 1. Crear los 5 estados estándar si no existen
        for nombre, descripcion in ESTADOS_ESTANDAR:
            obj, created = EstadoInventario.objects.get_or_create(
                nombre=nombre,
                defaults={'descripcion': descripcion}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  [CREADO]  {nombre}'))
            else:
                self.stdout.write(f'  [OK]      {nombre}')

        # 2. Migrar equipos que usan estados obsoletos
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Migrando estados obsoletos ==='))
        for nombre_viejo, nombre_nuevo in MIGRACION_NOMBRES.items():
            estado_viejo = EstadoInventario.objects.filter(nombre=nombre_viejo).first()
            if not estado_viejo:
                self.stdout.write(f'  [SKIP]    "{nombre_viejo}" no existe en la base de datos')
                continue

            estado_nuevo = EstadoInventario.objects.get(nombre=nombre_nuevo)

            n_med = Medidor.objects.filter(estado_inventario=estado_viejo).update(estado_inventario=estado_nuevo)
            n_sim = SimCard.objects.filter(estado_inventario=estado_viejo).update(estado_inventario=estado_nuevo)
            n_mod = Modem.objects.filter(estado_inventario=estado_viejo).update(estado_inventario=estado_nuevo)
            total = n_med + n_sim + n_mod

            if total > 0:
                self.stdout.write(self.style.WARNING(
                    f'  [MIGRADO] "{nombre_viejo}" → "{nombre_nuevo}" ({total} equipos: {n_med} medidores, {n_sim} SIMs, {n_mod} módems)'
                ))
            else:
                self.stdout.write(f'  [VACIO]   "{nombre_viejo}" existe pero sin equipos asignados')

            # Eliminar estado obsoleto si ya no tiene equipos referenciados
            aun_en_uso = (
                Medidor.objects.filter(estado_inventario=estado_viejo).exists() or
                SimCard.objects.filter(estado_inventario=estado_viejo).exists() or
                Modem.objects.filter(estado_inventario=estado_viejo).exists()
            )
            if not aun_en_uso:
                estado_viejo.delete()
                self.stdout.write(self.style.WARNING(f'  [BORRADO] Estado obsoleto eliminado: "{nombre_viejo}"'))

        self.stdout.write(self.style.SUCCESS('\n¡Estados inicializados correctamente!'))
