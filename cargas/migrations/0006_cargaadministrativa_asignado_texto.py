import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cargas', '0005_cargaadministrativa_proyecto'),
    ]

    operations = [
        migrations.AddField(
            model_name='cargaadministrativa',
            name='asignado_texto',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Nombre libre del responsable (p. ej. desde Excel); no requiere usuario del sistema',
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name='cargaadministrativa',
            name='asignado_a',
            field=models.ForeignKey(
                blank=True,
                help_text='Administrativo responsable de la carga (usuario del sistema)',
                limit_choices_to={'is_active': True, 'rol__in': ['ADMIN', 'ADMINISTRATIVO']},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cargas_asignadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
