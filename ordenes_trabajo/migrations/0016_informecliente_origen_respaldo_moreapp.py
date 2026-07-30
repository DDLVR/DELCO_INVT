from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ordenes_trabajo', '0015_adjunto_archivo_opcional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='informecliente',
            name='origen',
            field=models.CharField(
                choices=[
                    ('MANUAL', 'Carga manual'),
                    ('MOREAPP', 'MoreApp (sincronizado)'),
                    ('RESPALDO_MOREAPP', 'Respaldo PDF MoreApp'),
                    ('SISTEMA', 'Sistema'),
                ],
                default='MANUAL',
                max_length=20,
            ),
        ),
    ]
