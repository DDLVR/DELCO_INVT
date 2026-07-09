"""Generación de archivos Excel para reportes del PDF punto 9."""

from __future__ import annotations

from io import BytesIO
from typing import Iterable, Sequence

import openpyxl
from django.http import HttpResponse


def build_excel_response(filename: str, headers: Sequence[str], rows: Iterable[Sequence]) -> HttpResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Reporte'
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
