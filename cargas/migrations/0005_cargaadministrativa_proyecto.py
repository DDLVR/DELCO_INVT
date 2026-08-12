from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cargas', '0004_cargaadministrativa_soft_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='cargaadministrativa',
            name='proyecto',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Proyecto / listado asociado a esta carga administrativa',
                max_length=255,
            ),
        ),
        migrations.AddIndex(
            model_name='cargaadministrativa',
            index=models.Index(fields=['proyecto'], name='cargas_carg_proyec_7a1b2c_idx'),
        ),
    ]
