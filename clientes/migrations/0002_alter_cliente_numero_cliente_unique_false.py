from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0006_alter_cliente_city_alter_cliente_client_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cliente',
            name='numero_cliente',
            field=models.CharField(
                max_length=50,
                help_text='Identificador comercial del cliente en el sistema',
            ),
        ),
    ]
