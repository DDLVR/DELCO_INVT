# Generated manually for PDF punto 3

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0002_alter_cliente_numero_cliente_unique_false'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='empresa',
            field=models.CharField(blank=True, help_text='Empresa asociada al cliente, si corresponde', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='estado_sci4',
            field=models.CharField(choices=[('ACTUALIZADO', 'Actualizado'), ('PENDIENTE', 'Pendiente de actualización'), ('SIN_REGISTRO', 'Sin registro')], default='SIN_REGISTRO', help_text='Estado de actualización en SCi4', max_length=20),
        ),
        migrations.AddField(
            model_name='cliente',
            name='estado_stb',
            field=models.CharField(choices=[('ACTUALIZADO', 'Actualizado'), ('PENDIENTE', 'Pendiente de actualización'), ('SIN_REGISTRO', 'Sin registro')], default='SIN_REGISTRO', help_text='Estado de actualización en StarBeat (STB)', max_length=20),
        ),
        migrations.AddField(
            model_name='cliente',
            name='estado_telemetria',
            field=models.CharField(choices=[('OPERATIVO', 'Operativo'), ('SIN_COMUNICACION', 'Sin comunicación'), ('NO_COMUNICA', 'No comunica'), ('SIN_MEDIDOR', 'Sin medidor'), ('OTRO', 'Otro')], default='OPERATIVO', help_text='Estado actual de la telemetría del cliente', max_length=30),
        ),
        migrations.AddField(
            model_name='cliente',
            name='sim_abonado',
            field=models.CharField(blank=True, help_text='Número de abonado de la SIM', max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='sim_estado',
            field=models.CharField(blank=True, choices=[('OPERATIVA', 'Operativa'), ('SIN_DATOS', 'Sin datos'), ('DANADA', 'Dañada'), ('SIN_COBERTURA', 'Sin cobertura'), ('SIN_IP', 'Sin IP'), ('OTRO', 'Otro')], help_text='Estado operativo de la SIM', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='sim_iccid',
            field=models.CharField(blank=True, help_text='ICCID o identificador de la SIM', max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='sim_operador',
            field=models.CharField(blank=True, help_text='Operador de la SIM instalada', max_length=100, null=True),
        ),
    ]
