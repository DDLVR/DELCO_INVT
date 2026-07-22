from django.db import migrations, models
import django.db.models.deletion


def seed_historial_proyectos(apps, schema_editor):
    Cliente = apps.get_model('clientes', 'Cliente')
    ClienteProyectoHistorial = apps.get_model('clientes', 'ClienteProyectoHistorial')
    sin = {'', 'sin proyecto', 'sin_proyecto', 'null', 'nulo', 'none', '-'}

    for cliente in Cliente.objects.exclude(proyecto__isnull=True).exclude(proyecto='').iterator():
        texto = (cliente.proyecto or '').strip()
        if not texto or texto.casefold().replace('_', ' ') in sin:
            continue
        if ClienteProyectoHistorial.objects.filter(cliente_id=cliente.pk).exists():
            continue
        ClienteProyectoHistorial.objects.create(
            cliente_id=cliente.pk,
            proyecto=texto,
            fecha_inicio=cliente.fecha_creacion or cliente.fecha_actualizacion,
            fecha_fin=None,
            vigente=True,
            motivo='Registro inicial (migración)',
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0009_cliente_estado_restriccion_justificacion'),
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClienteProyectoHistorial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('proyecto', models.CharField(max_length=255)),
                ('fecha_inicio', models.DateTimeField()),
                ('fecha_fin', models.DateTimeField(blank=True, help_text='Vacío mientras el proyecto sigue vigente', null=True)),
                ('vigente', models.BooleanField(default=True, help_text='True = proyecto actual del cliente')),
                ('motivo', models.CharField(blank=True, default='', max_length=255)),
                ('fecha_registro', models.DateTimeField(auto_now_add=True)),
                ('cambiado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='cambios_proyecto_cliente',
                    to='usuarios.usuario',
                )),
                ('cliente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='proyectos_historial',
                    to='clientes.cliente',
                )),
            ],
            options={
                'verbose_name': 'Historial de proyecto del cliente',
                'verbose_name_plural': 'Historial de proyectos de clientes',
                'ordering': ['-fecha_inicio', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='clienteproyectohistorial',
            index=models.Index(fields=['cliente', 'vigente'], name='clientes_cl_cliente_6a0f0f_idx'),
        ),
        migrations.AddIndex(
            model_name='clienteproyectohistorial',
            index=models.Index(fields=['proyecto'], name='clientes_cl_proyect_7b1c2d_idx'),
        ),
        migrations.RunPython(seed_historial_proyectos, noop_reverse),
    ]
