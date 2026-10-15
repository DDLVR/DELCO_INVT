"""Fechas MoreApp en formato de pantalla DD/MM/YYYY (zona Chile)."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any, Optional

from django.utils import timezone


def parse_moreapp_when(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and str(value).isdigit()):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp = stamp / 1000.0
        try:
            parsed = datetime.fromtimestamp(stamp, tz=dt_timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    else:
        text = str(value).strip()
        if "T" not in text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return timezone.localtime(parsed)


def format_moreapp_when(value: Any) -> str:
    parsed = parse_moreapp_when(value)
    if parsed is None:
        return ""
    if parsed.hour or parsed.minute:
        return parsed.strftime("%d/%m/%Y %H:%M")
    return parsed.strftime("%d/%m/%Y")


def iso_day_moreapp(value: Any) -> str:
    parsed = parse_moreapp_when(value)
    if parsed is None:
        return ""
    return parsed.strftime("%Y-%m-%d")
