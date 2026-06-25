# Generated manually for ORDENES_TRABAJO import type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('importaciones', '0002_importacionexcel_usuario_nombre_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='importacionexcel',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('EQUIPOS', 'Importar Equipos (Medidores/SIM/Módems)'),
                    ('CLIENTES', 'Importar Clientes'),
                    ('MOVIMIENTOS', 'Importar Movimientos de Inventario'),
                    ('ORDENES_TRABAJO', 'Importar Órdenes de Trabajo'),
                ],
                max_length=30,
            ),
        ),
    ]
