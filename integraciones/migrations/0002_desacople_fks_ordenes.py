from django.db import migrations, models


def copy_ref_fields(apps, schema_editor):
    IntegracionMoreAppLog = apps.get_model('integraciones', 'IntegracionMoreAppLog')

    qs = IntegracionMoreAppLog.objects.all().only('id', 'orden_asociada_id', 'adjunto_creado_id')
    for log in qs.iterator(chunk_size=500):
        IntegracionMoreAppLog.objects.filter(id=log.id).update(
            orden_asociada_ref=log.orden_asociada_id,
            adjunto_creado_ref=log.adjunto_creado_id,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ordenes_trabajo', '0006_integracionmoreapp_estado_revision'),
        ('integraciones', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='integracionmoreapplog',
            name='adjunto_creado_ref',
            field=models.PositiveBigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='integracionmoreapplog',
            name='orden_asociada_ref',
            field=models.PositiveBigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(copy_ref_fields, noop_reverse),
        migrations.RemoveField(
            model_name='integracionmoreapplog',
            name='adjunto_creado',
        ),
        migrations.RemoveField(
            model_name='integracionmoreapplog',
            name='orden_asociada',
        ),
    ]
