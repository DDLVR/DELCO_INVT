from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("integraciones", "0011_alter_tarea_tipo_trabajo"),
    ]

    operations = [
        migrations.CreateModel(
            name="MoreAppCuentaTecnico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("moreapp_user_id", models.CharField(blank=True, max_length=80)),
                ("moreapp_nombre", models.CharField(blank=True, max_length=255)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                (
                    "actualizado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="moreapp_cuentas_enlazadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tecnico",
                    models.OneToOneField(
                        limit_choices_to={"rol": "TECNICO"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cuenta_moreapp",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Cuenta MoreApp de técnico",
                "verbose_name_plural": "Cuentas MoreApp de técnicos",
                "ordering": ["email"],
            },
        ),
    ]
