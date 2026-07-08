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


def merge_issues(*issues_groups: List[ValidationIssue]) -> List[ValidationIssue]:
    """Flatten groups preserving order."""
    merged: List[ValidationIssue] = []
    for group in issues_groups:
        merged.extend(group)
    return merged
