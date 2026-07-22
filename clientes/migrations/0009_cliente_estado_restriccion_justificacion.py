from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0008_soft_delete_y_snapshot_eliminaciones'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='estado_restriccion',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Sin restricción'),
                    ('IP_BLOQUEADA', 'IP bloqueada'),
                    ('IP_FUERA_SERVICIO', 'IP fuera de servicio'),
                    ('IP_EN_REVISION', 'IP en revisión'),
                    ('CERRADO', 'Cerrado'),
                    ('DESHABITADO', 'Deshabitado'),
                    ('NO_PERMITE', 'No permite acceso'),
                ],
                default='',
                help_text='Restricción operativa del cliente/IP (PDF punto 4)',
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='cliente',
            name='justificacion_restriccion',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Motivo obligatorio cuando hay restricción (bloqueada, fuera de servicio, deshabitado, etc.)',
            ),
        ),
    ]
