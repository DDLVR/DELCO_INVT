# Generated manually for OT proyecto/carga administrativa
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ordenes_trabajo', '0020_reestructura_bd_limpia'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordentrabajo',
            name='proyecto_carga_administrativa',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Proyecto o carga administrativa a la que pertenece este trabajo',
                max_length=255,
            ),
        ),
    ]
