# Generated manually for ordenes masivas e informes

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0003_cliente_fecha_registro_cliente_ip_cliente_modem_and_more'),
        ('usuarios', '0001_initial'),
        ('ordenes_trabajo', '0006_integracionmoreapp_estado_revision'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ordentrabajo',
            name='estado',
            field=models.CharField(
                choices=[
                    ('CREADA', 'Creada'),
                    ('ASIGNADA', 'Asignada'),
                    ('EN_EJECUCION', 'En ejecución'),
                    ('REASIGNADA', 'Reasignada'),
                    ('MANTENIMIENTO', 'Mantenimiento'),
                    ('REALIZADA', 'Realizada'),
                    ('REALIZADA_PENDIENTE_COMPROBACION', 'Realizada - Pendiente comprobación'),
                    ('PENDIENTE_VALIDACION', 'Pendiente validación'),
                    ('VALIDADA', 'Validada'),
                    ('OBSERVADA', 'Observada'),
                    ('FINALIZADA', 'Finalizada'),
                    ('CANCELADA', 'Cancelada'),
                ],
                default='CREADA',
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name='ordentrabajo',
            name='tecnico_responsable',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'rol': 'TECNICO'},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='ordenes_responsable',
                to='usuarios.usuario',
            ),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='alerta_duplicado',
            field=models.BooleanField(
                default=False,
                help_text='Posible trabajo duplicado para el mismo cliente en los últimos 14 días',
            ),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='descripcion_alerta_duplicado',
            field=models.TextField(
                blank=True,
                help_text='Detalle de la alerta de posible duplicidad',
            ),
        ),
        migrations.CreateModel(
            name='InformeCliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre_archivo', models.CharField(max_length=255)),
                ('archivo', models.FileField(help_text='PDF del informe del cliente', upload_to='Informe Clientes/%Y/%m/')),
                ('origen', models.CharField(choices=[('MANUAL', 'Carga manual'), ('MOREAPP', 'MoreApp'), ('SISTEMA', 'Sistema')], default='MANUAL', max_length=20)),
                ('fecha_subida', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='informes', to='clientes.cliente')),
                ('orden', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='informes', to='ordenes_trabajo.ordentrabajo')),
                ('registro_moreapp', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='informes_generados', to='ordenes_trabajo.integracionmoreapp')),
                ('subido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='informes_subidos', to='usuarios.usuario')),
            ],
            options={
                'verbose_name': 'Informe de Cliente',
                'verbose_name_plural': 'Informes de Clientes',
                'ordering': ['-fecha_subida'],
            },
        ),
    ]
