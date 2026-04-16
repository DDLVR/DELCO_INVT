from django.db import migrations, models


def copy_referencia_ot(apps, schema_editor):
    MovimientoInventario = apps.get_model('inventario', 'MovimientoInventario')
    OrdenTrabajo = apps.get_model('ordenes_trabajo', 'OrdenTrabajo')

    ordenes = {
        o.id: (getattr(o, 'titulo', '') or f'OT #{o.id}')
        for o in OrdenTrabajo.objects.all().only('id', 'titulo')
    }

    qs = MovimientoInventario.objects.exclude(orden_trabajo_id__isnull=True).only('id', 'orden_trabajo_id')
    for mov in qs.iterator(chunk_size=500):
        ref = ordenes.get(mov.orden_trabajo_id) or str(mov.orden_trabajo_id)
        MovimientoInventario.objects.filter(id=mov.id).update(referencia_ot=ref)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ordenes_trabajo', '0006_integracionmoreapp_estado_revision'),
        ('inventario', '0015_movimientoinventario_origen_sistema'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientoinventario',
            name='referencia_ot',
            field=models.CharField(blank=True, db_index=True, default='', help_text='Referencia textual de orden histórica (sin FK activa)', max_length=80),
        ),
        migrations.RunPython(copy_referencia_ot, noop_reverse),
        migrations.RemoveField(
            model_name='movimientoinventario',
            name='orden_trabajo',
        ),
    ]
