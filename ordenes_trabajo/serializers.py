from rest_framework import serializers
from .models import OrdenTrabajo


class OrdenTrabajoSerializer(serializers.ModelSerializer):
    """
    Serializer de lectura/actualización segura para OrdenTrabajo.
    No expone campos de auditoría ni soft-delete para mass-assignment.
    """

    class Meta:
        model = OrdenTrabajo
        fields = [
            'id',
            'titulo',
            'descripcion',
            'tipo_trabajo',
            'cliente',
            'medidor',
            'simcard',
            'modem',
            'observaciones_tecnicas',
            'proyecto_carga_administrativa',
            'estado',
            'tecnico_responsable',
            'fecha_creacion',
            'fecha_asignacion',
            'fecha_inicio_ejecucion',
            'fecha_fin_ejecucion',
        ]
        read_only_fields = [
            'id',
            'estado',
            'fecha_creacion',
            'fecha_asignacion',
            'fecha_inicio_ejecucion',
            'fecha_fin_ejecucion',
        ]
