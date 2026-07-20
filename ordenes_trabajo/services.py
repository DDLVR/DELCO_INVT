"""Work-order business validations aligned to PDF point 4 and 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from .models import OrdenTrabajo


@dataclass
class OTValidationResult:
    """Validation result for OT checks."""

    has_blocking_error: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def validate_ot_duplicate(open_ot_exists: bool, same_requirement_exists: bool) -> OTValidationResult:
    """Validate duplicate OT conditions."""
    errors: List[str] = []
    warnings: List[str] = []

    if open_ot_exists:
        errors.append('Ya existe una OT abierta para este cliente.')
    if same_requirement_exists:
        warnings.append('Ya existe una OT abierta con el mismo tipo de trabajo para este cliente.')

    return OTValidationResult(has_blocking_error=bool(errors), warnings=warnings, errors=errors)


def should_flag_reincidence(visits_last_6_months: int, today: date | None = None) -> bool:
    """Return true when client has more than two visits in the last 6 months."""
    _ = today or date.today()
    return visits_last_6_months > 2


def six_month_window_start(today: date | None = None) -> date:
    """Helper to compute a practical 6-month lookback window."""
    base = today or date.today()
    return base - timedelta(days=183)


def _estados_abiertos() -> set:
    return set(OrdenTrabajo.ESTADOS_ABIERTOS)


def has_open_ot_for_cliente(cliente_id: int, exclude_orden_id: Optional[int] = None) -> bool:
    qs = OrdenTrabajo.objects.filter(
        cliente_id=cliente_id,
        estado__in=_estados_abiertos(),
        eliminado=False,
    )
    if exclude_orden_id:
        qs = qs.exclude(pk=exclude_orden_id)
    return qs.exists()


def has_same_requirement_ot(
    cliente_id: int,
    tipo_trabajo: str,
    exclude_orden_id: Optional[int] = None,
) -> bool:
    qs = OrdenTrabajo.objects.filter(
        cliente_id=cliente_id,
        tipo_trabajo=tipo_trabajo,
        estado__in=_estados_abiertos(),
        eliminado=False,
    )
    if exclude_orden_id:
        qs = qs.exclude(pk=exclude_orden_id)
    return qs.exists()


def count_visits_last_6_months(cliente_id: int, exclude_orden_id: Optional[int] = None) -> int:
    desde = six_month_window_start()
    qs = OrdenTrabajo.objects.filter(
        cliente_id=cliente_id,
        fecha_creacion__date__gte=desde,
        eliminado=False,
    ).exclude(estado='CANCELADA')
    if exclude_orden_id:
        qs = qs.exclude(pk=exclude_orden_id)
    return qs.count()


def validate_ot_for_creation(
    cliente,
    tipo_trabajo: str,
    exclude_orden_id: Optional[int] = None,
) -> OTValidationResult:
    """Run PDF point 4 OT validations before creating or importing an order."""
    if not cliente:
        return OTValidationResult(has_blocking_error=False)

    open_ot = has_open_ot_for_cliente(cliente.pk, exclude_orden_id)
    same_req = has_same_requirement_ot(cliente.pk, tipo_trabajo, exclude_orden_id)
    result = validate_ot_duplicate(open_ot, same_req)

    visits = count_visits_last_6_months(cliente.pk, exclude_orden_id)
    if should_flag_reincidence(visits):
        result.warnings.append(
            f'Cliente con más de dos visitas en los últimos 6 meses ({visits} registros).'
        )

    pending_validation = OrdenTrabajo.objects.filter(
        cliente_id=cliente.pk,
        estado='PENDIENTE_VALIDACION',
        eliminado=False,
    )
    if exclude_orden_id:
        pending_validation = pending_validation.exclude(pk=exclude_orden_id)
    if pending_validation.exists():
        result.warnings.append('Existe una OT pendiente de validación para este cliente.')

    closed_without_execution = OrdenTrabajo.objects.filter(
        cliente_id=cliente.pk,
        estado='CANCELADA',
        fecha_inicio_ejecucion__isnull=True,
        eliminado=False,
    )
    if exclude_orden_id:
        closed_without_execution = closed_without_execution.exclude(pk=exclude_orden_id)
    if closed_without_execution.exists():
        result.warnings.append('El cliente tiene OT cerradas/anuladas sin ejecución efectiva registrada.')

    return result
