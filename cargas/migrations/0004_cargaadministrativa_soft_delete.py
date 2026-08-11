from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cargas', '0003_adjunto_papelera'),
    ]

    operations = [
        migrations.AddField(
            model_name='cargaadministrativa',
            name='eliminado',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='cargaadministrativa',
            name='fecha_eliminacion',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cargaadministrativa',
            name='eliminado_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cargas_eliminadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='cargaadministrativa',
            index=models.Index(fields=['eliminado', 'estado'], name='cargas_carg_elimin_4f9a2c_idx'),
        ),
    ]
