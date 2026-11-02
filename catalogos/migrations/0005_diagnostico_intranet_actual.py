from django.db import migrations, models


def actualizar_catalogo(apps, schema_editor):
    CatalogoDiagnostico = apps.get_model("catalogos", "CatalogoDiagnostico")
    from catalogos.datos_diagnostico import sync_catalogo_diagnostico

    sync_catalogo_diagnostico(model=CatalogoDiagnostico)


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0004_rename_catalogos_p_activo_nombre_idx_catalogos_p_activo_8181a5_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="catalogodiagnostico",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("INTRANET", "Intranet"),
                    ("TAREAS", "Tareas MoreApp"),
                    ("SISTEMA", "Sistema"),
                    ("SIMCARD", "SIMCard"),
                    ("MODEM", "Módem"),
                    ("MEDIDOR", "Medidor"),
                    ("ESTADO_CLIENTE", "Estado cliente"),
                    ("ESTADO_VISITA", "Estado visita"),
                    ("OTRO", "Otro"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(actualizar_catalogo, migrations.RunPython.noop),
    ]
