# Auditoría de seguridad — DELCO_INVT

**Fecha:** 2026-08-03  
**Rama auditada:** `cursor/auditoria-seguridad-7588` (HEAD = `origin/Principal` @ `f2d908b`)  
**Alcance:** código actual post-hardening (#20 / #21). Excluido `.venv`.

---

## Resumen ejecutivo

Tras el endurecimiento reciente, la app **ya no embebe credenciales de producción**, exige secretos por entorno, protege webhooks MoreApp en modo fail-closed y sirve `/media` y evidencias solo con sesión. Persisten riesgos relevantes: un **PDF operativo versionado en Git**, **acceso a media/evidencias por cualquier usuario autenticado** (sin RBAC ni ownership), **subidas de adjuntos sin validación de tipo/tamaño**, y **contraseñas/secretos antiguos aún presentes en el historial de Git** que deben rotarse.

---

## Hallazgos priorizados

| Severidad | Issue | Archivo(s) | Recomendación |
|-----------|--------|------------|---------------|
| **High** | PDF de evidencias/adjuntos de OT versionado en el repositorio (~2.5 MB, ruta con nombre de instalación) | `media/ordenes_adjuntos/2026/06/25/ADICIONALES_ESPACIO_ALTO_QUILIN_ANO_2026_260504_103849.pdf` | Eliminar del repo (`git rm --cached`), añadir `media/` a `.gitignore`, rotar/revisar si el PDF contiene datos sensibles; usar almacenamiento solo en servidor. |
| **High** | Media y evidencias protegidas solo con `@login_required`: cualquier rol autenticado puede leer cualquier archivo si conoce/adivina la ruta (IDOR horizontal) | `web/protected_media.py`, `config/urls.py` | Autorizar por rol y/o ownership (p. ej. técnico solo sus OT); preferir URLs firmadas o servir vía vista que resuelva `AdjuntoOrden`/`InformeCliente` por PK con chequeo de permiso. |
| **High** | `orden_subir_adjunto_view` acepta cualquier archivo sin whitelist de extensión, sin tope de tamaño ni magia de contenido (a diferencia de PDFs de informe/comprobante) | `ordenes_trabajo/views.py` (~824–871) | Whitelist (`pdf`, `jpg`, `png`, …), límite de bytes, validar cabecera/MIME; servir con `Content-Disposition: attachment` / `X-Content-Type-Options: nosniff` para evitar XSS almacenado. |
| **High** | Credencial histórica de MySQL (`Chomuske132$$`) y un `SECRET_KEY`/token (`nC1IeThy…`) estuvieron en `settings_production.py` / `settings.py`; el código actual ya no los tiene, pero **siguen en historial Git** | Historial (`git log -S 'Chomuske'`); tests aún referencian los strings en aserciones negativas | Rotar `DB_PASSWORD`, `SECRET_KEY` y `MOREAPP_WEBHOOK_SECRET` en hosting; invalidar sesiones; considerar `git filter-repo` solo si el remoto es privado y el equipo acepta reescritura. |
| **Medium** | `SECRET_KEY` de desarrollo hardcodeada como fallback | `config/settings.py` L33–36 | Mantener solo en local; fallar si `DEBUG=False` sin env; no reutilizar esa clave nunca en Passenger. |
| **Medium** | `SECURE_SSL_REDIRECT` default `False`; HSTS solo se activa si redirect=True; `CSRF_TRUSTED_ORIGINS` incluye `http://inventario.delcochile.cl` | `config/settings_production.py` L49–68; `.env.example` L31 | En producción real detrás de HTTPS: `SECURE_SSL_REDIRECT=True` (o confiar en proxy + header), quitar origen HTTP, activar HSTS. |
| **Medium** | Validadores Django de contraseña definidos pero **no aplicados** en alta/reset/perfil; reset exige solo `len >= 6` | `config/settings.py` L149–162; `web/views.py` (~2769–2893, ~4109–4114) | Usar `django.contrib.auth.password_validation.validate_password` en crear/reset/`update_profile`. |
| **Medium** | Enumeración de usuarios en login: mensajes distintos “RUT no encontrado” vs “Contraseña incorrecta” | `web/views.py` L245–258 | Mensaje genérico único; opcional rate-limit / lockout. |
| **Medium** | `clientes_list_view` y `cliente_historial_view` solo `@login_required` (TECNICO ve padrón y ficha completa); export/import/delete sí tienen rol | `web/views.py` L2902+, L3679+ | Confirmar si es requisito de negocio; si no, restringir lectura sensible a roles administrativos/auditoría. |
| **Medium** | Logout por GET (`<a href="{% url 'logout' %}">`) — logout CSRF | `templates/partials/sidebar.html` L103; `web/views.py` L265–268 | Cambiar a POST + `{% csrf_token %}` (o `LogoutView` de Django). |
| **Medium** | `.gitignore` no ignora `.venv/` ni `media/` (solo `venv/`, `venv38/`); riesgo de subir entornos o adjuntos | `.gitignore` | Añadir `.venv/`, `media/**` (salvo `.gitkeep` si se desea), `*.pdf` bajo media. |
| **Medium** | `.env.example` expone nombres reales de BD/usuario cPanel | `.env.example` L19–20 | Usar placeholders (`DB_NAME=tu_base`, `DB_USER=tu_usuario`). |
| **Medium** | Sin `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` explícitos; adjuntos sin tope de app | settings | Definir límites globales alineados a hosting (p. ej. 15–25 MB). |
| **Medium** | Webhook alternativo `moreapp_webhook_view` con `@permission_classes([AllowAny])` y `error: str(e)` en 500 (hoy **no montado** en `config/urls.py`, sí en `ordenes_trabajo/urls.py`) | `ordenes_trabajo/views.py` L1551–1632 | Eliminar o unificar con el webhook principal; nunca devolver excepciones al cliente. |
| **Low** | Login filtra excepciones con `Error: {str(e)}` | `web/views.py` L259–260 | Log interno + mensaje genérico. |
| **Low** | `{{ numeros_duplicados_json\|safe }}` en plantilla (datos numéricos de BD; riesgo bajo) | `templates/clientes/list.html` L615 | Preferir `json_script` de Django. |
| **Low** | Sin rate-limit / throttling de login ni webhook | — | django-axes / middleware o límites en reverse proxy. |
| **Low** | Dependencias con rangos amplios (`Django>=4.2,<5.0`, etc.); entorno local tiene 4.2.30 | `requirements.txt` | Fijar versiones exactas (`pip freeze` de producción) y escanear con `pip-audit`. |
| **Info** | `ALLOWED_HOSTS` de desarrollo lista `inventario.delcochile` (sin `.cl`) | `config/settings.py` L42–46 | Alinear con dominio real o dejar solo localhost en base. |
| **Info** | `CORS_*` en producción sin evidencia de `corsheaders` en `INSTALLED_APPS` | `settings_production.py` L104–108 | Quitar si no se usa, o instalar/configurar el middleware. |
| **Info** | Tests usan contraseñas débiles (`admin1234`) — solo tests | varios `*/tests.py` | Aceptable; no usar en datos reales. |

---

## Evidencia (snippets clave)

### Producción: secretos obligatorios (bien)

```27:41:config/settings_production.py
# SEGURIDAD
DEBUG = os.environ.get('DEBUG', 'False').strip().lower() == 'true'

SECRET_KEY = _require_env('SECRET_KEY')
_PLACEHOLDER_KEYS = {
    'CAMBIAR-POR-CLAVE-SEGURA-EN-PRODUCCION',
    ...
}
if SECRET_KEY in _PLACEHOLDER_KEYS or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured(...)
```

### Webhook fail-closed + `compare_digest` (bien)

```4575:4585:web/views.py
        expected_secret = str(getattr(settings, 'MOREAPP_WEBHOOK_SECRET', '') or '').strip()
        if not expected_secret:
            ...
            return JsonResponse({'success': False, 'error': 'Webhook no autorizado'}, status=403)
        ...
        if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
            return JsonResponse({'success': False, 'error': 'Webhook no autorizado'}, status=403)
```

### Media solo con login (parcialmente bien; falta RBAC)

```9:18:web/protected_media.py
@login_required
def serve_media(request, path):
    """Adjuntos y archivos subidos (ordenes, comprobantes, etc.)."""
    return django_serve(request, path, document_root=settings.MEDIA_ROOT)


@login_required
def serve_evidencias(request, path):
    """Evidencias de terreno bajo /registros/evidencias/."""
    return django_serve(request, path, document_root=settings.EVIDENCIAS_ROOT)
```

### IDOR OT mitigado para técnicos (bien)

```472:479:ordenes_trabajo/views.py
    orden = get_object_or_404(OrdenTrabajo, pk=pk, eliminado=False)
    usuario = request.user
    if usuario.rol not in ['ADMIN', 'ADMINISTRATIVO', 'GERENCIA', 'AUDITOR']:
        if usuario.rol == 'TECNICO' and orden.tecnico_responsable != usuario:
            messages.error(request, 'No tienes acceso a esta orden')
            return redirect('ordenes_list')
```

### Fallback inseguro en desarrollo

```33:36:config/settings.py
SECRET_KEY = os.getenv(
    'SECRET_KEY',
    'django-insecure-ze21q-q$&2(!*!orvf)w-_s&xttn0^((b+2qzlvew&y$hfb%23',
)
```

### Adjunto sin validación fuerte

```836:860:ordenes_trabajo/views.py
            archivo = request.FILES.get('archivo')
            tipo = request.POST.get('tipo', 'OTRO')
            ...
            adjunto.archivo = archivo
            adjunto.subido_por = request.user
            adjunto.save()
```

### PDF informe: validación correcta (referencia positiva)

```1159:1178:ordenes_trabajo/views.py
    if not nombre.lower().endswith('.pdf'):
        ...
    if archivo.size and archivo.size > MAX_PDF_BYTES:
        ...
    cabecera = archivo.read(5)
    ...
    if cabecera != b'%PDF-':
        ...
```

---

## Qué ya está bien asegurado

1. **Secretos de producción** vía `_require_env` (`SECRET_KEY`, `DB_*`, `MOREAPP_WEBHOOK_SECRET`); rechazo de placeholders / `django-insecure-`.
2. **Webhooks** CSRF-exempt solo donde corresponde, secreto obligatorio, `hmac.compare_digest`, errores genéricos en el endpoint principal; legacy responde 410 tras auth.
3. **Sesión:** timeout absoluto 8 h (`AbsoluteSessionTimeoutMiddleware`), `cycle_key()` al login, `SESSION_COOKIE_HTTPONLY`, cookies `Secure`/`SameSite=Lax` en prod.
4. **CSRF** activo en middleware; login con `{% csrf_token %}`.
5. **RBAC** en export/import/delete clientes, cargas, reportes hub/export, auditoría, pendientes operativos, gestión usuarios, sync/delete MoreApp.
6. **OT:** filtrado por técnico responsable en listados/API queryset; chequeos en detalle, adjuntos, equipos, eliminar (`@admin_only`).
7. **PDF** de informes y comprobantes: extensión + tamaño + cabecera `%PDF-`.
8. **SQL:** sin raw queries de usuario en app (ORM / parámetros); sin `|safe` peligroso generalizado.
9. **Tests de seguridad** (`web/tests_seguridad.py`) cubren webhook 403, media anónima, export clientes por rol, ausencia de secretos hardcodeados en prod.
10. **Passenger** fuerza `config.settings_production`.

---

## Top 5 acciones concretas

1. **Rotar** en Hostingplus: `DB_PASSWORD`, `SECRET_KEY`, `MOREAPP_WEBHOOK_SECRET` (historial Git tuvo password en claro); reiniciar Passenger e invalidar sesiones.
2. **Quitar del repo** el PDF bajo `media/ordenes_adjuntos/...` y ampliar `.gitignore` (`.venv/`, `media/`).
3. **Endurecer `serve_media` / `serve_evidencias`**: autorización por rol u ownership de OT, no solo autenticación.
4. **Validar uploads de adjuntos** como los PDF (whitelist, tamaño, magic bytes) y forzar descarga segura.
5. **Aplicar `validate_password`**, unificar mensajes de login, logout por POST, y activar `SECURE_SSL_REDIRECT`/HSTS (quitar `http://` de `CSRF_TRUSTED_ORIGINS`) en producción.

---

## Matriz rápida por área solicitada

| Área | Estado |
|------|--------|
| 1. Secrets en source | Limpios en código actual; historial Git contaminado; fallback insecure en `settings.py`; DB names en `.env.example` |
| 2. Production settings | Sólidos con matices SSL/HSTS/HTTP origin |
| 3. Auth/sesión | Buena base; enumeración login; logout GET; validators no usados |
| 4. RBAC | Export/import/delete OK; list/historial clientes y media más abiertos |
| 5. Media/evidencias | Auth sí; RBAC/IDOR no |
| 6. Webhooks/API | Principal OK; alternativo AllowAny+leak (no montado) |
| 7. SQLi | Sin hallazgos relevantes |
| 8. XSS | Bajo (`\|safe` JSON números); riesgo vía adjuntos HTML |
| 9. Uploads | PDF bien; adjuntos genéricos débiles |
| 10. Mass assignment / IDOR OT | OT detalle OK; ViewSet no montado; serializer podría permitir reasignación si se expone |
| 11. .gitignore | `.env`/db/logs OK; falta `.venv` y `media/` |
| 12. Dependencies | Rangos amplios; Django 4.2.x LTS razonable; fijar pins + audit |
