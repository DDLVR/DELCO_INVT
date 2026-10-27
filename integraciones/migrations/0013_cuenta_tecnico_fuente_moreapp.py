from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integraciones", "0012_moreappcuentatecnico"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="moreappcuentatecnico",
            name="tecnico",
        ),
        migrations.AddField(
            model_name="moreappcuentatecnico",
            name="tecnico_entry_id",
            field=models.CharField(default="", max_length=80, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="moreappcuentatecnico",
            name="tecnico_nombre",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
    ]
