from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('importaciones', '0003_ordenes_trabajo_import_tipo'),
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
                    ('CARGAS_ADMINISTRATIVAS', 'Importar Órdenes de Trabajo Administrativas'),
                ],
                max_length=30,
            ),
        ),
    ]
