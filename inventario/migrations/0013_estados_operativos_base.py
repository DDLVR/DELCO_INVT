from django.db import migrations


ESTADOS_BASE = [
    ('En bodega', 'Equipo disponible en bodega, sin asignar'),
    ('Instalado', 'Equipo instalado en cliente'),
    ('Retirado', 'Equipo retirado de instalación'),
    ('En reparación', 'Equipo en proceso de reparación'),
    ('Dado de baja', 'Equipo fuera de servicio en forma definitiva'),
]


def crear_estados_base(apps, schema_editor):
    EstadoInventario = apps.get_model('inventario', 'EstadoInventario')

    for nombre, descripcion in ESTADOS_BASE:
        EstadoInventario.objects.get_or_create(
            nombre=nombre,
            defaults={'descripcion': descripcion},
        )


def reverse_noop(apps, schema_editor):
    # No eliminamos estados en rollback para no romper referencias históricas.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0012_estado_en_peaje'),
    ]

    operations = [
        migrations.RunPython(crear_estados_base, reverse_noop),
    ]
