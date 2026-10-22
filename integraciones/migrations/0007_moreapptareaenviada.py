from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('integraciones', '0006_moreappformularioasignado'),
    ]

    operations = [
        migrations.CreateModel(
            name='MoreAppTareaEnviada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('form_id', models.CharField(max_length=80)),
                ('form_name', models.CharField(blank=True, max_length=255)),
                ('task_id', models.CharField(blank=True, max_length=80)),
                ('mensaje', models.CharField(max_length=500)),
                ('destinatarios', models.JSONField(blank=True, default=list)),
                ('grupos', models.JSONField(blank=True, default=list)),
                ('envio', models.CharField(default='IMMEDIATE', max_length=20)),
                ('programada_para', models.DateTimeField(blank=True, null=True)),
                ('fecha_limite', models.DateTimeField(blank=True, null=True)),
                ('ubicacion', models.CharField(blank=True, max_length=255)),
                ('latitud', models.CharField(blank=True, max_length=40)),
                ('longitud', models.CharField(blank=True, max_length=40)),
                ('datos_precarga', models.JSONField(blank=True, default=dict)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('error', models.TextField(blank=True)),
                ('creado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='moreapp_tareas_enviadas',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Tarea MoreApp enviada',
                'verbose_name_plural': 'Tareas MoreApp enviadas',
                'ordering': ['-fecha_creacion'],
            },
        ),
    ]
