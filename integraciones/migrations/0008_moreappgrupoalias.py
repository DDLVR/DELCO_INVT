from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("integraciones", "0007_moreapptareaenviada"),
    ]

    operations = [
        migrations.CreateModel(
            name="MoreAppGrupoAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group_id", models.CharField(max_length=80, unique=True)),
                ("nombre", models.CharField(max_length=120)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                (
                    "actualizado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="moreapp_grupos_nombrados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Alias de grupo MoreApp",
                "verbose_name_plural": "Alias de grupos MoreApp",
            },
        ),
    ]
