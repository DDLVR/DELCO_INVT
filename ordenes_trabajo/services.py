"""Reglas de negocio y validaciones de OT (PDF puntos 4 y 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from django.utils import timezone


@dataclass
class OTValidationResult:
    """Resultado de validaciones de OT."""

    has_blocking_error: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def validate_ot_duplicate(open_ot_exists: bool, same_requirement_exists: bool) -> OTValidationResult:
    """Valida duplicidad de OT (reglas puras, sin acceso a BD)."""
    result = OTValidationResult()
    if open_ot_exists:
        result.warnings.append('Ya existe una OT abierta para este cliente.')
    if same_requirement_exists:
        result.warnings.append('Ya existe una OT con requerimiento similar.')
    return result


def should_flag_reincidence(visits_last_6_months: int, today: date | None = None) -> bool:
    """True si el cliente supera 2 visitas en los últimos 6 meses."""
    _ = today or date.today()
    return visits_last_6_months > 2


def six_month_window_start(today: date | None = None) -> date:
    """Ventana práctica de 6 meses hacia atrás."""
    base = today or date.today()
    return base - timedelta(days=183)


def _merge_results(*results: OTValidationResult) -> OTValidationResult:
    merged = OTValidationResult()
    for item in results:
        merged.errors.extend(item.errors)
        merged.warnings.extend(item.warnings)
        merged.has_blocking_error = merged.has_blocking_error or item.has_blocking_error
    return merged


def _cliente_tiene_antecedentes_problematicos(cliente) -> List[str]:
    """Detecta antecedentes operativos en notas del cliente (PDF punto 4)."""
    if not cliente:
        return []

    texto = ' '.join(
        filter(
            None,
            [
                getattr(cliente, 'note', '') or '',
                getattr(cliente, 'trabajo', '') or '',
                getattr(cliente, 'referencia', '') or '',
            ],
        )
    ).lower()

    alertas: List[str] = []
    for palabra, etiqueta in (
        ('cerrado', 'cerrado'),
        ('no permite', 'no permite acceso'),
        ('deshabitado', 'deshabitado'),
    ):
        if palabra in texto:
            alertas.append(f'Cliente con antecedente de "{etiqueta}".')
    return alertas


def evaluar_alertas_ot(
    cliente,
    titulo: str = '',
    tipo_trabajo: str = '',
    exclude_orden_id: Optional[int] = None,
) -> OTValidationResult:
    """
    Evalúa alertas operativas de OT contra la base de datos.
    El PDF pide avisar (no bloquear) en la mayoría de casos de OT.
    """
    from ordenes_trabajo.models import OrdenTrabajo

    result = OTValidationResult()
    if not cliente:
        return result

    qs_base = OrdenTrabajo.objects.filter(cliente=cliente)
    if exclude_orden_id:
        qs_base = qs_base.exclude(pk=exclude_orden_id)

    open_ot_exists = qs_base.filter(estado__in=OrdenTrabajo.ESTADOS_ABIERTOS).exists()

    same_requirement_exists = False
    titulo_norm = (titulo or '').strip()
    if titulo_norm:
        same_requirement_exists = qs_base.filter(titulo__iexact=titulo_norm).exists()
    elif tipo_trabajo:
        same_requirement_exists = qs_base.filter(
            tipo_trabajo=tipo_trabajo,
            estado__in=OrdenTrabajo.ESTADOS_ABIERTOS,
        ).exists()

    result = _merge_results(result, validate_ot_duplicate(open_ot_exists, same_requirement_exists))

    desde = six_month_window_start()
    visitas = qs_base.filter(
        fecha_creacion__date__gte=desde,
        estado__in=[
            'REALIZADA',
            'REALIZADA_PENDIENTE_COMPROBACION',
            'PENDIENTE_VALIDACION',
            'VALIDADA',
            'FINALIZADA',
        ],
    ).count()
    if should_flag_reincidence(visitas):
        result.warnings.append(
            f'Cliente visitado más de 2 veces en los últimos 6 meses ({visitas} visitas).'
        )

    cerrada_sin_ejecutar = qs_base.filter(
        estado='CANCELADA',
        fecha_inicio_ejecucion__isnull=True,
    ).exists()
    if cerrada_sin_ejecutar:
        result.warnings.append('Existe una OT cerrada sin ejecución efectiva para este cliente.')

    umbral_pendiente = timezone.now() - timedelta(days=7)
    pendiente_sin_respuesta = qs_base.filter(
        estado__in=['CREADA', 'ASIGNADA', 'PENDIENTE_VALIDACION'],
        fecha_creacion__lt=umbral_pendiente,
    ).exists()
    if pendiente_sin_respuesta:
        result.warnings.append('Existe una OT pendiente sin respuesta (> 7 días).')

    for alerta in _cliente_tiene_antecedentes_problematicos(cliente):
        result.warnings.append(alerta)

    return result


def aplicar_alertas_operativas(orden) -> OTValidationResult:
    """Calcula y persiste alertas operativas en la OT."""
    result = evaluar_alertas_ot(
        cliente=orden.cliente,
        titulo=orden.titulo,
        tipo_trabajo=orden.tipo_trabajo,
        exclude_orden_id=orden.pk,
    )

    from ordenes_trabajo.utils import detectar_duplicado_orden

    tiene_dup, desc_dup = detectar_duplicado_orden(orden.cliente, exclude_orden_id=orden.pk)
    if tiene_dup and desc_dup:
        result.warnings.append(desc_dup)

    mensajes = list(dict.fromkeys(result.warnings + result.errors))
    orden.alerta_duplicado = bool(mensajes)
    orden.descripcion_alerta_duplicado = ' | '.join(mensajes)
    orden.save(update_fields=['alerta_duplicado', 'descripcion_alerta_duplicado'])
    return result
