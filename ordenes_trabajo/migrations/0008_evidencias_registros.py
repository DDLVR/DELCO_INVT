# Generated manually — evidencias en Registros/Evidencias

import config.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ordenes_trabajo', '0007_ordenes_masivas_informes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adjuntoorden',
            name='archivo',
            field=models.FileField(
                help_text='Archivo subido en Registros/Evidencias',
                storage=config.storage.evidencias_storage,
                upload_to=config.storage.evidencia_upload_to,
            ),
        ),
        migrations.AlterField(
            model_name='informecliente',
            name='archivo',
            field=models.FileField(
                help_text='PDF del informe en Registros/Evidencias',
                storage=config.storage.evidencias_storage,
                upload_to=config.storage.evidencia_upload_to,
            ),
        ),
    ]
