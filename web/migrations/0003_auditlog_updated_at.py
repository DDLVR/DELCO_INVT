from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0002_rename_web_auditlo_action_7c61bb_idx_web_auditlo_action_e4df12_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="updated_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["updated_at"], name="web_auditlo_updated_idx"),
        ),
        migrations.AlterModelOptions(
            name="auditlog",
            options={
                "ordering": ["-updated_at", "-created_at"],
                "verbose_name": "Auditoría",
                "verbose_name_plural": "Auditoría",
            },
        ),
    ]
