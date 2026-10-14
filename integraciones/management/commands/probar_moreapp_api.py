"""Prueba conectividad con MoreApp API usando X-Api-Key."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from integraciones.moreapp_api import (
    MoreAppApiConfigError,
    MoreAppApiError,
    list_forms,
    test_connection,
)


class Command(BaseCommand):
    help = "Valida conexión MoreApp API y opcionalmente lista formularios"

    def add_arguments(self, parser):
        parser.add_argument(
            "--listar-formularios",
            action="store_true",
            help="Llama al endpoint de formularios y muestra la respuesta",
        )
        parser.add_argument(
            "--page",
            type=int,
            default=0,
            help="Página para listado de formularios (default: 0)",
        )
        parser.add_argument(
            "--query",
            type=str,
            default="",
            help="Filtro de búsqueda para formularios",
        )

    def _print_json(self, payload: Any) -> None:
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

    def handle(self, *args, **options):
        try:
            status = test_connection()
            self.stdout.write(self.style.SUCCESS("Conexión MoreApp OK"))
            self._print_json(status)

            if options["listar_formularios"]:
                data = list_forms(page=int(options["page"]), query_text=str(options["query"] or ""))
                self.stdout.write("")
                self.stdout.write(self.style.SUCCESS("Respuesta de formularios"))
                self._print_json(data)

        except MoreAppApiConfigError as exc:
            self.stderr.write(self.style.ERROR(f"Configuración inválida: {exc}"))
            raise SystemExit(2)
        except MoreAppApiError as exc:
            self.stderr.write(self.style.ERROR(f"Error de conexión/API: {exc}"))
            raise SystemExit(1)
