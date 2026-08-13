# Cliente.proyecto_asignado FK + seed desde textos existentes

from django.db import migrations, models
import django.db.models.deletion


SIN_PROYECTO = {
    '',
    'sin proyecto',
    'sinproyectos',
    'sin proyectos',
    'sin_proyecto',
    '__vacio__',
    'null',
    'nulo',
    'none',
    '-',
}


def _es_sin(valor: str) -> bool:
    texto = (valor or '').strip()
    if not texto:
        return True
    normalizado = ' '.join(texto.casefold().replace('_', ' ').split())
    return normalizado in SIN_PROYECTO


def seed_proyectos_y_asignar(apps, schema_editor):
    Proyecto = apps.get_model('catalogos', 'Proyecto')
    Cliente = apps.get_model('clientes', 'Cliente')
    OrdenTrabajo = apps.get_model('ordenes_trabajo', 'OrdenTrabajo')
    CargaAdministrativa = apps.get_model('cargas', 'CargaAdministrativa')
    ClienteProyectoHistorial = apps.get_model('clientes', 'ClienteProyectoHistorial')

    nombres = set()
    for campo_qs in (
        Cliente.objects.exclude(proyecto__isnull=True).exclude(proyecto='').values_list('proyecto', flat=True),
        ClienteProyectoHistorial.objects.exclude(proyecto='').values_list('proyecto', flat=True),
        OrdenTrabajo.objects.exclude(proyecto_carga_administrativa='')
        .values_list('proyecto_carga_administrativa', flat=True),
        CargaAdministrativa.objects.exclude(proyecto='').values_list('proyecto', flat=True),
    ):
        for raw in campo_qs.iterator():
            texto = (raw or '').strip()
            if texto and not _es_sin(texto):
                nombres.add(texto)

    for nombre in sorted(nombres, key=lambda s: s.casefold()):
        if not Proyecto.objects.filter(nombre__iexact=nombre).exists():
            Proyecto.objects.create(nombre=nombre[:255], activo=True)

    for cliente in Cliente.objects.exclude(proyecto__isnull=True).exclude(proyecto='').iterator():
        texto = (cliente.proyecto or '').strip()
        if not texto or _es_sin(texto):
            continue
        proyecto = Proyecto.objects.filter(nombre__iexact=texto).first()
        if proyecto and cliente.proyecto_asignado_id != proyecto.pk:
            cliente.proyecto_asignado_id = proyecto.pk
            cliente.save(update_fields=['proyecto_asignado'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0012_reestructura_bd_limpia'),
        ('catalogos', '0003_proyecto'),
        ('ordenes_trabajo', '0021_ordentrabajo_proyecto_carga_administrativa'),
        ('cargas', '0006_cargaadministrativa_asignado_texto'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='proyecto_asignado',
            field=models.ForeignKey(
                blank=True,
                help_text='Proyecto del catálogo. El cliente no tiene proyecto hasta que se crea una OT/carga.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='clientes',
                to='catalogos.proyecto',
            ),
        ),
        migrations.AlterField(
            model_name='cliente',
            name='proyecto',
            field=models.CharField(
                blank=True,
                help_text='Proyecto asociado al cliente (texto legado; se sincroniza con proyecto_asignado)',
                max_length=255,
                null=True,
            ),
        ),
        migrations.RunPython(seed_proyectos_y_asignar, noop_reverse),
    ]
