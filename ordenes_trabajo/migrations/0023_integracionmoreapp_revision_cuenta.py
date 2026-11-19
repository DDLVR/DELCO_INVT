from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ordenes_trabajo', '0022_alter_tecnico_responsable_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='integracionmoreapp',
            name='revisado_por',
            field=models.ForeignKey(
                blank=True,
                help_text='Cuenta que validó o descartó el informe',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='informes_moreapp_revisados',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='integracionmoreapp',
            name='revisado_nombre',
            field=models.CharField(
                blank=True,
                help_text='Nombre de la cuenta al momento de validar o descartar',
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name='integracionmoreapp',
            name='fecha_revision',
            field=models.DateTimeField(
                blank=True,
                help_text='Cuándo se validó o descartó el informe',
                null=True,
            ),
        ),
    ]
