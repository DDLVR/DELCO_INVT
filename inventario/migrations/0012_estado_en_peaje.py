from django.db import migrations


def crear_estado_en_peaje(apps, schema_editor):
    EstadoInventario = apps.get_model('inventario', 'EstadoInventario')
    EstadoInventario.objects.get_or_create(
        nombre='En peaje',
        defaults={'descripcion': 'Equipo en peaje para gestion operativa'},
    )


def eliminar_estado_en_peaje(apps, schema_editor):
    EstadoInventario = apps.get_model('inventario', 'EstadoInventario')
    EstadoInventario.objects.filter(nombre='En peaje').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0011_medidor_proyecto_simcard_proyecto'),
    ]

    operations = [
        migrations.RunPython(crear_estado_en_peaje, eliminar_estado_en_peaje),
    ]
