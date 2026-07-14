"""Smoke test integral bajo Python 3.8 + SQLite local."""
import os
import traceback
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from django.db import connection
from django.test import Client
from django.utils import timezone

settings.DEBUG = False

errors = []
ok = []


def note(ok_flag, label, detail=""):
    if ok_flag:
        ok.append(label)
        print(f"OK  {label}" + (f" — {detail}" if detail else ""))
    else:
        errors.append((label, detail))
        print(f"FAIL {label} — {detail}")


# 1) JSON functions
try:
    with connection.cursor() as c:
        payload = '{"a": 1, "b": {"c": "x"}, "d": [1,2], "e": true, "f": null}'
        assert c.execute("SELECT JSON_VALID(?)", [payload]).fetchone()[0] == 1
        assert c.execute("SELECT JSON_TYPE(?)", [payload]).fetchone()[0] == "object"
        assert c.execute("SELECT JSON_TYPE(?, ?)", [payload, "$.a"]).fetchone()[0] == "integer"
        assert c.execute("SELECT JSON_EXTRACT(?, ?)", [payload, "$.a"]).fetchone()[0] == 1
        assert c.execute("SELECT JSON_EXTRACT(?, ?)", [payload, '$."b"']).fetchone()[0]
        assert c.execute("SELECT JSON_TYPE(?, ?)", [payload, "$.f"]).fetchone()[0] == "null"
        assert c.execute("SELECT JSON_TYPE(?, ?)", [payload, "$.e"]).fetchone()[0] == "true"
        assert c.execute("SELECT JSON_EXTRACT(?, ?)", [payload, "$.d[0]"]).fetchone()[0] == 1
    note(True, "sqlite_json_functions")
except Exception as e:
    note(False, "sqlite_json_functions", traceback.format_exc())


# 2) JSONField lookups ORM
try:
    from ordenes_trabajo.models import IntegracionMoreApp
    list(
        IntegracionMoreApp.objects.filter(
            datos_procesados__cliente_codigo__isnull=False
        ).values_list("datos_procesados__cliente_codigo", flat=True)[:3]
    )
    list(
        IntegracionMoreApp.objects.filter(
            datos_procesados__cliente_nombre__icontains="a"
        )[:3]
    )
    note(True, "jsonfield_orm_lookups")
except Exception:
    note(False, "jsonfield_orm_lookups", traceback.format_exc())


# 3) All report runners
try:
    from reportes.services import REPORT_CATALOG, run_report
    for slug in REPORT_CATALOG:
        try:
            headers, rows = run_report(slug, {})
            note(True, f"report:{slug}", f"rows={len(rows)} cols={len(headers)}")
        except Exception:
            note(False, f"report:{slug}", traceback.format_exc())
except Exception:
    note(False, "report_catalog_import", traceback.format_exc())


# 4) Core model queries (páginas de listado típicas)
try:
    from clientes.models import Cliente
    from inventario.models import Medidor, SimCard, Modem, MovimientoInventario
    from ordenes_trabajo.models import OrdenTrabajo, IntegracionMoreApp
    from importaciones.models import ImportacionExcel
    Cliente.objects.filter(activo=True).count()
    Medidor.objects.select_related("estado_inventario", "cliente").count()
    SimCard.objects.select_related("estado_inventario", "cliente").count()
    Modem.objects.select_related("estado_inventario", "cliente").count()
    MovimientoInventario.objects.select_related("origen", "destino", "responsable").count()
    OrdenTrabajo.objects.select_related("cliente", "tecnico_responsable").count()
    IntegracionMoreApp.objects.count()
    ImportacionExcel.objects.count()
    note(True, "core_model_queries")
except Exception:
    note(False, "core_model_queries", traceback.format_exc())


# 5) HTTP smoke (rutas GET autenticadas)
try:
    from usuarios.models import Usuario
    user = (
        Usuario.objects.filter(is_active=True, is_superuser=True).first()
        or Usuario.objects.filter(is_active=True, rol="ADMIN").first()
        or Usuario.objects.filter(is_active=True).first()
    )
    if not user:
        note(False, "http_smoke", "no hay usuario activo")
    else:
        client = Client(HTTP_HOST="127.0.0.1")
        client.force_login(user)
        paths = [
            "/dashboard/",
            "/profile/",
            "/inventario/",
            "/inventario/?tipo=medidor",
            "/inventario/?tipo=sim",
            "/inventario/?tipo=modem",
            "/inventario/crear/",
            "/clientes/",
            "/clientes/crear/",
            "/ordenes/",
            "/ordenes/crear/",
            "/movimientos/",
            "/movimientos/historial/",
            "/usuarios/",
            "/usuarios/crear/",
            "/registro-errores/",
            "/reportes/",
            "/reportes/moreapp/",
            "/operacional/pendientes/",
            "/auditoria/",
            "/catalogos/diagnostico/",
            "/api/buscar-medidores/?q=1",
        ]
        for slug in REPORT_CATALOG:
            paths.append(f"/reportes/exportar/{slug}/")

        for path in paths:
            try:
                resp = client.get(path)
                # redirects de login no deberían pasar (force_login)
                if resp.status_code >= 500:
                    note(False, f"GET {path}", f"status={resp.status_code}")
                else:
                    note(True, f"GET {path}", f"status={resp.status_code}")
            except Exception:
                note(False, f"GET {path}", traceback.format_exc())
except Exception:
    note(False, "http_smoke_setup", traceback.format_exc())


# 6) Autosync MoreApp dry path (leer_carpetas)
try:
    from integraciones.reader import leer_carpetas
    # dry-run si existe; si no, llamar y capturar
    try:
        stats = leer_carpetas(dry_run=True)
    except TypeError:
        # sin dry_run: no ejecutar escritura pesada; solo import + helpers
        from integraciones import reader as r
        assert callable(r.leer_carpetas)
        stats = {"skipped": True}
    note(True, "moreapp_reader_import", str(stats)[:120])
except Exception:
    note(False, "moreapp_reader_import", traceback.format_exc())


# 7) timezone-aware dashboard filter replica
try:
    from inventario.models import MovimientoInventario
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ahora = timezone.now()
        MovimientoInventario.objects.filter(fecha_hora__gte=ahora - timedelta(days=7)).count()
        MovimientoInventario.objects.filter(fecha_hora__date=timezone.localdate()).count()
        naive_warns = [w for w in caught if "naive datetime" in str(w.message)]
    note(len(naive_warns) == 0, "timezone_filters", f"naive_warns={len(naive_warns)}")
except Exception:
    note(False, "timezone_filters", traceback.format_exc())


print("\n======== SUMMARY ========")
print(f"OK: {len(ok)}  FAIL: {len(errors)}")
for label, detail in errors:
    print(f"\n--- {label} ---")
    print(detail[:2000])

raise SystemExit(1 if errors else 0)
