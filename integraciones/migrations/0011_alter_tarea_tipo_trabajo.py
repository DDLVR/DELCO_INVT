from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integraciones", "0010_tarea_operativa"),
    ]

    operations = [
        migrations.AlterField(
            model_name="moreapptareaenviada",
            name="tipo_trabajo",
            field=models.CharField(
                blank=True,
                choices=[
                    ("INSTALACION", "Instalación"),
                    ("CAMBIO", "Cambio de equipo"),
                    ("RETIRO", "Retiro"),
                    ("MANTENCION", "Mantención"),
                    ("REPARACION", "Reparación"),
                    ("INSPECCION", "Inspección"),
                    ("CONFIGURACION", "Configuración"),
                    ("OTRO", "Otro"),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
