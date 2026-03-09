from rest_framework import serializers
from .models import OrdenTrabajo


class OrdenTrabajoSerializer(serializers.ModelSerializer):
    """
    Serializer principal para OrdenTrabajo.

    ¿Qué hace?
    - Toma una OrdenTrabajo (objeto de Django) y la convierte a JSON.
    - Toma JSON y lo valida para crear/actualizar una OrdenTrabajo.
    """

    class Meta:
        # Modelo que vamos a convertir a JSON
        model = OrdenTrabajo

        # Campos que se incluirán en la respuesta JSON
        # '__all__' significa "todos los campos del modelo"
        fields = '__all__'