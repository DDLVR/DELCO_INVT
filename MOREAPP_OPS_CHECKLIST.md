# Checklist operativo MoreApp (Puntos PDF 6 y 8)

Bloque post-MVP. Objetivo: MoreApp estable en produccion **sin** API bidireccional nueva.

Estado codigo (2026-07-15): panel ops en `/reportes/moreapp/`, registro de ultima sync, comando
`sincronizar_registros --limite-web`. Cierre host = marcar items abajo en el servidor.

## En el servidor (Hostingplus)

1. `git pull` en `/home50/delcochi/delcochile_inventario` (rama `Principal`).
2. Si cambio `requirements.txt`: `pip install -r requirements.txt` en el venv del host.
3. Restart de la app (Passenger / panel).
4. Confirmar Python **3.8.x** en el entorno de ejecucion.

## Carpetas y sync

5. Existe `MOREAPP_REGISTROS_DIR` (o default `Registros/`) con la estructura MoreApp FTPS.
6. El usuario del proceso web puede **leer** esos JSON (badge **Carpeta OK** en el listado MoreApp).
7. Sync habitual:
   - Boton **Sincronizar ahora** en `/reportes/moreapp/`, y/o
   - Cron recomendado (cada 5–10 min):

```cron
*/10 * * * * cd /home50/delcochi/delcochile_inventario && ./venv/bin/python manage.py sincronizar_registros --limite-web >> logs/moreapp_sync.log 2>&1
```

   (Ajustar ruta del venv si en el host es otra.)

8. **No** depender de autosync en cada GET: `MOREAPP_AUTO_SYNC_ENABLED=false` (default produccion). El panel debe mostrar **Autosync GET off**.

## Variables recomendadas (produccion)

| Variable | Valor tipico |
|---|---|
| `MOREAPP_AUTO_SYNC_ENABLED` | `false` |
| `MOREAPP_WEB_SYNC_MAX_SEGUNDOS` | `30` |
| `MOREAPP_WEB_SYNC_MAX_ARCHIVOS` | `40` |
| `MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS` | `true` |
| `MOREAPP_FIRST_SCAN_TAIL` | `25` |
| `MOREAPP_INCREMENTAL_LOOKBACK` | `1` |
| `MOREAPP_AUTO_REFRESH_SECONDS` | `0` |

## Verificacion funcional

9. Listado MoreApp carga en segundos (paginado) y muestra el panel **Estado ops MoreApp**.
10. Tras sync, aparece **Ultima sync** con origen `manual_web` o `cron`.
11. Cola `/operacional/pendientes/` y badge de aviso reflejan pendientes/advertencias.
12. Alertas `ALERTA_CRITICA` visibles (filtro/KPI).
13. Dashboard no se queda colgado esperando leer carpetas.

## Criterio de cierre

- Codigo/tooling: listo en Principal.
- Host: items 1–13 verificados por el companero (o N/A documentado).
- Punto 6 en matriz: LISTO (terreno = MoreApp; app Delco fuera de alcance).
- Punto 8: PARCIAL solo por Fase 2 (API/multimedia).

## Fuera de este checklist (Fase 2)

API bidireccional, multimedia/georref avanzada, pareja tecnicos UI, denormalizacion MoreApp.
