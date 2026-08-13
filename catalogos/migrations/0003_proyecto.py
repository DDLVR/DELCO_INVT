# Generated manually for Proyecto catalog

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0002_rename_catalogos_c_categor_0f0f0f_idx_catalogos_c_categor_9f5476_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='Proyecto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=255, unique=True)),
                ('activo', models.BooleanField(db_index=True, default=True)),
                ('descripcion', models.TextField(blank=True, default='')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Proyecto',
                'verbose_name_plural': 'Proyectos',
                'ordering': ['nombre'],
                'indexes': [
                    models.Index(fields=['activo', 'nombre'], name='catalogos_p_activo_nombre_idx'),
                ],
            },
        ),
    ]
