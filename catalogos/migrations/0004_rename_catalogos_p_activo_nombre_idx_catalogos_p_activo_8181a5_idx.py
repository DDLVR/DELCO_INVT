# El índice de Proyecto ya tiene nombre fijo en 0003 / models.py.
# Esta migración queda como no-op para no aplicar RenameIndex en MySQL/hosting
# (historial: Django inventó un rename al faltar name= en Meta.indexes).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0003_proyecto'),
    ]

    operations = []
