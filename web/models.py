from django.conf import settings
from django.db import models


class AuditLog(models.Model):
	"""Registro persistente de eventos de auditoría (Punto 12)."""

	actor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='audit_logs',
	)
	action = models.CharField(max_length=80)
	entity = models.CharField(max_length=120)
	entity_id = models.CharField(max_length=120)
	field_name = models.CharField(max_length=120, null=True, blank=True)
	old_value = models.TextField(null=True, blank=True)
	new_value = models.TextField(null=True, blank=True)
	reason = models.TextField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = 'Auditoría'
		verbose_name_plural = 'Auditoría'
		ordering = ['-created_at']
		indexes = [
			models.Index(fields=['action']),
			models.Index(fields=['entity']),
			models.Index(fields=['entity_id']),
			models.Index(fields=['created_at']),
		]

	def __str__(self):
		return f'{self.action} {self.entity}#{self.entity_id}'
