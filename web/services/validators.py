"""Business validators aligned to the functional requirements PDF.

The goal is to have one source of truth for create/edit/import rules.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import List


@dataclass
class ValidationIssue:
    """Represents a validation issue with severity and message."""

    code: str
    message: str
    severity: str  # "error" or "warning"


def normalize_ip_value(ip_value) -> str | None:
    """Normaliza IP desde Excel (a veces llega como entero sin puntos: 10117122165 -> 10.117.122.165)."""
    if ip_value is None:
        return None

    if isinstance(ip_value, bool):
        return None

    if isinstance(ip_value, float):
        if ip_value.is_integer():
            ip_value = int(ip_value)
        else:
            ip_value = str(ip_value).strip()

    if isinstance(ip_value, int):
        texto = str(ip_value)
    else:
        texto = str(ip_value).strip()
        if texto.endswith('.0') and texto[:-2].isdigit():
            texto = texto[:-2]

    if not texto:
        return None

    try:
        return str(ipaddress.ip_address(texto))
    except ValueError:
        pass

    digitos = ''.join(ch for ch in texto if ch.isdigit())
    candidatos = []
    # Patrón frecuente en bases Delco: 10.xxx.xxx.xxx comprimido a 11 dígitos
    if len(digitos) == 11 and digitos.startswith('10'):
        candidatos.append(f'{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}.{digitos[8:11]}')
    if len(digitos) == 12:
        candidatos.append(f'{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}.{digitos[9:12]}')
    if len(digitos) == 10 and digitos.startswith('10'):
        candidatos.append(f'{digitos[0:2]}.{digitos[2:4]}.{digitos[4:7]}.{digitos[7:10]}')

    for candidato in candidatos:
        try:
            return str(ipaddress.ip_address(candidato))
        except ValueError:
            continue

    return texto


def validate_ip_format(ip_value: str | None) -> List[ValidationIssue]:
    """Validate IPv4/IPv6 format when an IP is provided."""
    issues: List[ValidationIssue] = []
    if not ip_value:
        return issues

    try:
        ipaddress.ip_address(ip_value.strip())
    except ValueError:
        issues.append(
            ValidationIssue(
                code="IP_INVALID_FORMAT",
                message=f"IP invalida: {ip_value}",
                severity="error",
            )
        )
    return issues


def validate_ip_port_coherence(ip_value: str | None, port_value: str | None) -> List[ValidationIssue]:
    """Require port when IP exists, as requested in the functional doc."""
    issues: List[ValidationIssue] = []
    if ip_value and not (port_value or "").strip():
        issues.append(
            ValidationIssue(
                code="IP_WITHOUT_PORT",
                message="Si hay IP, debe existir puerto asociado.",
                severity="warning",
            )
        )
    return issues


def validate_meter_uniqueness(series: str | None, exists_on_other_active_client: bool) -> List[ValidationIssue]:
    """Validate meter series uniqueness for active clients."""
    issues: List[ValidationIssue] = []
    if series and exists_on_other_active_client:
        issues.append(
            ValidationIssue(
                code="METER_DUPLICATED",
                message=f"Serie medidor duplicada: {series}",
                severity="error",
            )
        )
    return issues


def validate_modem_assignment(modem_identifier: str | None, assigned_on_other_active_client: bool) -> List[ValidationIssue]:
    """Validate modem assignment consistency."""
    issues: List[ValidationIssue] = []
    if modem_identifier and assigned_on_other_active_client:
        issues.append(
            ValidationIssue(
                code="MODEM_ASSIGNED",
                message=f"Modem ya asignado a otro cliente: {modem_identifier}",
                severity="warning",
            )
        )
    return issues


def validate_modem_inventory_status(estado_nombre: str | None) -> List[ValidationIssue]:
    """Warn when modem inventory status is out of service (PDF point 4)."""
    issues: List[ValidationIssue] = []
    if not estado_nombre:
        return issues

    estado = estado_nombre.strip().lower()
    if estado == 'dado de baja':
        issues.append(
            ValidationIssue(
                code='MODEM_BAJA',
                message='El módem está dado de baja en inventario.',
                severity='error',
            )
        )
    elif estado in {'en reparación', 'en reparacion'}:
        issues.append(
            ValidationIssue(
                code='MODEM_FALLADO',
                message='El módem figura como fallado/en reparación en inventario.',
                severity='warning',
            )
        )
    return issues


def validate_meter_terreno_vs_sistema(
    serie_terreno: str | None,
    serie_sistema: str | None,
) -> List[ValidationIssue]:
    """Alert when field meter differs from registered system meter (PDF point 4)."""
    issues: List[ValidationIssue] = []
    terreno = (serie_terreno or '').strip()
    sistema = (serie_sistema or '').strip()
    if terreno and sistema and terreno.lower() != sistema.lower():
        issues.append(
            ValidationIssue(
                code='METER_MISMATCH',
                message=(
                    f'Medidor en terreno ({terreno}) distinto al registrado en sistema ({sistema}).'
                ),
                severity='warning',
            )
        )
    return issues


def validate_ip_duplicate_on_active_clients(
    ip_value: str | None,
    exists_on_other_active_client: bool,
) -> List[ValidationIssue]:
    """Alert when IP is already assigned to another active client."""
    issues: List[ValidationIssue] = []
    if ip_value and exists_on_other_active_client:
        issues.append(
            ValidationIssue(
                code='IP_DUPLICATED',
                message=f'IP ya asignada a otro cliente activo: {ip_value}',
                severity='error',
            )
        )
    return issues


def validate_meter_required_fields(
    series: str | None,
    manufacturer: str | None,
) -> List[ValidationIssue]:
    """Validate minimum meter data (PDF point 4)."""
    issues: List[ValidationIssue] = []
    if series and not (manufacturer or '').strip():
        issues.append(
            ValidationIssue(
                code='METER_WITHOUT_BRAND',
                message='El medidor requiere marca o fabricante asociado.',
                severity='warning',
            )
        )
    return issues


def merge_issues(*issues_groups: List[ValidationIssue]) -> List[ValidationIssue]:
    """Flatten groups preserving order."""
    merged: List[ValidationIssue] = []
    for group in issues_groups:
        merged.extend(group)
    return merged
