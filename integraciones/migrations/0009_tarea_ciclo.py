from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_estados(apps, schema_editor):
    Tarea = apps.get_model("integraciones", "MoreAppTareaEnviada")
    Evento = apps.get_model("integraciones", "MoreAppTareaEvento")
    for tarea in Tarea.objects.all().iterator():
        if tarea.error:
            tarea.estado = "ERROR"
            tarea.save(update_fields=["estado"])
            Evento.objects.create(
                tarea=tarea,
                tipo="ERROR_ENVIO",
                origen="intranet",
                detalle={"backfill": True},
            )
            continue
        tarea.estado = "ASIGNADA"
        if not tarea.fecha_asignacion:
            tarea.fecha_asignacion = tarea.fecha_creacion
        tarea.save(update_fields=["estado", "fecha_asignacion"])
        Evento.objects.create(
            tarea=tarea,
            tipo="ASIGNADA",
            origen="intranet",
            detalle={"backfill": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ordenes_trabajo", "0022_alter_tecnico_responsable_roles"),
        ("integraciones", "0008_moreappgrupoalias"),
    ]

    operations = [
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="cuenta",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="estado",
            field=models.CharField(
                choices=[
                    ("ERROR", "Error de envío"),
                    ("PENDIENTE", "Pendiente"),
                    ("ASIGNADA", "Asignada"),
                    ("COMPLETADA", "Completada"),
                ],
                db_index=True,
                default="PENDIENTE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="fecha_asignacion",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="fecha_completado",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="ultima_sync",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="moreapptareaenviada",
            name="integracion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tareas_moreapp",
                to="ordenes_trabajo.integracionmoreapp",
            ),
        ),
        migrations.AddIndex(
            model_name="moreapptareaenviada",
            index=models.Index(fields=["estado", "-fecha_creacion"], name="integracio_estado_c4f1a1_idx"),
        ),
        migrations.AddIndex(
            model_name="moreapptareaenviada",
            index=models.Index(fields=["form_id", "estado"], name="integracio_form_id_8e2b2c_idx"),
        ),
        migrations.CreateModel(
            name="MoreAppTareaEvento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("CREADA", "Creada"), ("ASIGNADA", "Asignada"), ("COMPLETADA", "Completada"), ("ERROR_ENVIO", "Error de envío")], db_index=True, max_length=20)),
                ("en", models.DateTimeField(auto_now_add=True)),
                ("origen", models.CharField(choices=[("intranet", "Intranet"), ("api", "API MoreApp"), ("informe", "Informe MoreApp")], default="intranet", max_length=20)),
                ("detalle", models.JSONField(blank=True, default=dict)),
                (
                    "tarea",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eventos",
                        to="integraciones.moreapptareaenviada",
                    ),
                ),
            ],
            options={
                "verbose_name": "Evento de tarea MoreApp",
                "verbose_name_plural": "Eventos de tareas MoreApp",
                "ordering": ["en", "id"],
            },
        ),
        migrations.CreateModel(
            name="MoreAppTareaAlerta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("CREACION", "Tarea creada"), ("COMPLETADO", "Tarea completada")], db_index=True, max_length=20)),
                ("broadcast", models.BooleanField(db_index=True, default=False)),
                ("leida_en", models.DateTimeField(blank=True, null=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                (
                    "tarea",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alertas",
                        to="integraciones.moreapptareaenviada",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="moreapp_tareas_alertas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Alerta de tarea MoreApp",
                "verbose_name_plural": "Alertas de tareas MoreApp",
                "ordering": ["-fecha_creacion"],
            },
        ),
        migrations.AddIndex(
            model_name="moreapptareaevento",
            index=models.Index(fields=["tarea", "tipo"], name="integracio_tarea_i_a1b2c3_idx"),
        ),
        migrations.AddIndex(
            model_name="moreapptareaalerta",
            index=models.Index(fields=["broadcast", "leida_en"], name="integracio_broadca_d4e5f6_idx"),
        ),
        migrations.AddIndex(
            model_name="moreapptareaalerta",
            index=models.Index(fields=["usuario", "leida_en"], name="integracio_usuario_g7h8i9_idx"),
        ),
        migrations.RunPython(backfill_estados, migrations.RunPython.noop),
    ]
