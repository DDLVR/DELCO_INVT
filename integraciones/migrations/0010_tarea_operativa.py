from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0014_cliente_adjunto"),
        ("integraciones", "0009_tarea_ciclo"),
    ]

    operations = [
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="titulo",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
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
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="cliente",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tareas_moreapp",
                to="clientes.cliente",
            ),
        ),
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="proyecto_carga_administrativa",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="observaciones",
            field=models.TextField(blank=True),
        ),
    ]
