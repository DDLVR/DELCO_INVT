# Generated manually for PDF punto 10

from django.db import migrations, models


CATALOGO_INICIAL = [
    ('SISTEMA', 'IP errónea del módem', 'Actualizar IP en StarBeat'),
    ('SISTEMA', 'Base de datos no actualizada', 'Actualizar medidor en StarBeat'),
    ('SISTEMA', 'Caída masiva', 'Generar incidencia a TI'),
    ('SIMCARD', 'Sin plan de datos', 'Cambio de SIMCard'),
    ('SIMCARD', 'SIM sucia o mal instalada', 'Limpieza y reinstalación'),
    ('SIMCARD', 'SIM dañada', 'Cambio de SIMCard'),
    ('SIMCARD', 'Sin cobertura', 'Traslado de equipo, cambio de antena o uso de doble SIM'),
    ('MODEM', 'Obsoleto o con falla sin repuesto', 'Cambio de módem'),
    ('MODEM', 'Desprogramado', 'Cambio de módem y reprogramación del equipo retirado'),
    ('MODEM', 'Falla franca', 'Cambio de módem y baja del equipo retirado'),
    ('MODEM', 'No existe módem en terreno', 'Instalación de módem y habilitación de telemedida'),
    ('MEDIDOR', 'Hurto o intervención', 'Informar a Pérdidas'),
    ('MEDIDOR', 'No compatible con telemedida', 'Cambio de medidor'),
    ('MEDIDOR', 'Sin medidor, conectado directo', 'Instalar medidor, habilitar telemedida e informar a Pérdidas'),
    ('MEDIDOR', 'No comunica, pero registra', 'Cambio de medidor'),
    ('MEDIDOR', 'Falla franca, no comunica ni registra', 'Cambio de medidor e informar a Pérdidas'),
    ('MEDIDOR', 'Sin medidor', 'Reponer medidor si corresponde'),
    ('MEDIDOR', 'Medidor en terreno distinto al sistema', 'Actualizar sistema con medidor real en terreno'),
    ('ESTADO_CLIENTE', 'Sin suministro', 'Monitorear estado'),
    ('ESTADO_CLIENTE', 'Retirado', 'Retirar cliente con apoyo de Morosidad'),
    ('ESTADO_VISITA', 'Cerrado', 'Reprogramar visita para lograr acceso y diagnóstico'),
    ('ESTADO_VISITA', 'Deshabitado', 'Realizar seguimiento con lectura pedestre'),
    ('ESTADO_VISITA', 'No permite acceso', 'Reportar a Pérdidas o área correspondiente'),
]


def cargar_catalogo_inicial(apps, schema_editor):
    CatalogoDiagnostico = apps.get_model('catalogos', 'CatalogoDiagnostico')
    for orden, (categoria, origen, solucion) in enumerate(CATALOGO_INICIAL, start=1):
        CatalogoDiagnostico.objects.get_or_create(
            categoria=categoria,
            origen=origen,
            defaults={'solucion': solucion, 'orden': orden, 'activo': True},
        )


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='CatalogoDiagnostico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('categoria', models.CharField(choices=[('SISTEMA', 'Sistema'), ('SIMCARD', 'SIMCard'), ('MODEM', 'Módem'), ('MEDIDOR', 'Medidor'), ('ESTADO_CLIENTE', 'Estado cliente'), ('ESTADO_VISITA', 'Estado visita'), ('OTRO', 'Otro')], max_length=30)),
                ('origen', models.CharField(help_text='Causa u origen del diagnóstico', max_length=255)),
                ('solucion', models.TextField(help_text='Acción o solución recomendada')),
                ('activo', models.BooleanField(default=True)),
                ('orden', models.PositiveIntegerField(default=0)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Diagnóstico',
                'verbose_name_plural': 'Catálogo de diagnósticos',
                'ordering': ['categoria', 'orden', 'origen'],
            },
        ),
        migrations.AddIndex(
            model_name='catalogodiagnostico',
            index=models.Index(fields=['categoria', 'activo'], name='catalogos_c_categor_0f0f0f_idx'),
        ),
        migrations.RunPython(cargar_catalogo_inicial, migrations.RunPython.noop),
    ]
