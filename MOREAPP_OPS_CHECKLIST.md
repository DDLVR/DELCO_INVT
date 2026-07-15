# Checklist operativo MoreApp (Puntos PDF 6 y 8)

Siguiente bloque post-MVP (congelado 2026-07-15 en `MATRIZ_TRAZABILIDAD_PDF.md`).
Objetivo: dejar MoreApp estable en produccion **sin** API bidireccional nueva.

## En el servidor (Hostingplus)

1. `git pull` en `/home50/delcochi/delcochile_inventario` (rama `Principal`).
2. Si cambio `requirements.txt` (p. ej. reportlab): `pip install -r requirements.txt` en el venv del host.
3. Restart de la app (Passenger / panel).
4. Confirmar Python **3.8.x** en el entorno de ejecucion.

## Carpetas y sync

5. Existe `MOREAPP_REGISTROS_DIR` (o default `Registros/`) con la estructura MoreApp FTPS.
6. El usuario del proceso web puede **leer** esos JSON.
7. Sync habitual:
   - Boton manual en la UI MoreApp, y/o
   - Cron: `python manage.py sincronizar_registros` (si aplica en el host).
8. **No** depender de autosync en cada GET: `MOREAPP_AUTO_SYNC_ENABLED=false` (default produccion).

## Variables recomendadas (produccion)

| Variable | Valor tipico |
|---|---|
| `MOREAPP_AUTO_SYNC_ENABLED` | `false` |
| `MOREAPP_WEB_SYNC_MAX_SEGUNDOS` | `30` |
| `MOREAPP_WEB_SYNC_MAX_ARCHIVOS` | `40` |
| `MOREAPP_WEB_SKIP_DUPLICATE_REPROCESS` | `true` |
| `MOREAPP_FIRST_SCAN_TAIL` | `25` |
| `MOREAPP_INCREMENTAL_LOOKBACK` | `1` |
| `MOREAPP_AUTO_REFRESH_SECONDS` | `0` (sin reload auto de pagina) |

## Verificacion funcional

9. Entrar como ADMIN/ADMINISTRATIVO: listado MoreApp carga en segundos (paginado).
10. Un registro nuevo en carpeta aparece tras sync manual/cron.
11. Cola `/operacional/pendientes/` y badge de aviso reflejan pendientes/advertencias.
12. Alertas `ALERTA_CRITICA` visibles (filtro/KPI).
13. Dashboard no se queda colgado esperando leer carpetas.

## Criterio de cierre de este bloque

- [ ] Items 1–13 verificados en produccion (o N/A documentado).
- [ ] Acta Punto 6 actualizada a LISTO MVP+ops **o** se deja PARCIAL solo por decision de negocio (app propia sigue fuera).
- [ ] Punto 8 sigue PARCIAL unicamente por Fase 2 (API/multimedia), no por sync basico.

## Fuera de este checklist (Fase 2)

API bidireccional, multimedia/georref avanzada, pareja tecnicos UI, denormalizacion MoreApp.
