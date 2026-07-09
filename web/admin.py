from django.contrib import admin

from .models import AuditoriaRegistro


@admin.register(AuditoriaRegistro)
class AuditoriaRegistroAdmin(admin.ModelAdmin):
    list_display = ('fecha_hora', 'action', 'entity', 'entity_id', 'actor', 'field_name')
    list_filter = ('action', 'entity', 'fecha_hora')
    search_fields = ('entity_id', 'field_name', 'old_value', 'new_value', 'reason')
    readonly_fields = (
        'actor',
        'fecha_hora',
        'action',
        'entity',
        'entity_id',
        'field_name',
        'old_value',
        'new_value',
        'reason',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
