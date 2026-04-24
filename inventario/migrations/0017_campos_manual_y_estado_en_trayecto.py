from django.db import migrations, models


def crear_estado_en_trayecto(apps, schema_editor):
    EstadoInventario = apps.get_model('inventario', 'EstadoInventario')
    EstadoInventario.objects.get_or_create(
        nombre='En Trayecto',
        defaults={'descripcion': 'Equipo entregado a tecnico o tercero y en traslado operativo'},
    )


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0016_movimientoinventario_referencia_ot'),
    ]

    operations = [
        migrations.AddField(
            model_name='medidor',
            name='cliente_otro',
            field=models.CharField(blank=True, default='', help_text='Cliente manual cuando no existe en la base', max_length=255),
        ),
        migrations.AddField(
            model_name='medidor',
            name='entregado_a_otro',
            field=models.CharField(blank=True, default='', help_text='Responsable manual cuando no existe como usuario', max_length=255),
        ),
        migrations.AddField(
            model_name='modem',
            name='cliente_otro',
            field=models.CharField(blank=True, default='', help_text='Cliente manual cuando no existe en la base', max_length=255),
        ),
        migrations.AddField(
            model_name='modem',
            name='entregado_a_otro',
            field=models.CharField(blank=True, default='', help_text='Responsable manual cuando no existe como usuario', max_length=255),
        ),
        migrations.AddField(
            model_name='modem',
            name='medidor_otro',
            field=models.CharField(blank=True, default='', help_text='Número de medidor manual cuando no existe en la base', max_length=100),
        ),
        migrations.AddField(
            model_name='simcard',
            name='cliente_otro',
            field=models.CharField(blank=True, default='', help_text='Cliente manual cuando no existe en la base', max_length=255),
        ),
        migrations.AddField(
            model_name='simcard',
            name='entregado_a_otro',
            field=models.CharField(blank=True, default='', help_text='Responsable manual cuando no existe como usuario', max_length=255),
        ),
        migrations.AddField(
            model_name='simcard',
            name='medidor_otro',
            field=models.CharField(blank=True, default='', help_text='Número de medidor manual cuando no existe en la base', max_length=100),
        ),
        migrations.RunPython(crear_estado_en_trayecto, reverse_noop),
    ]
