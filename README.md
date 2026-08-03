# DELCO_INVT

Plataforma web de **inventario operativo, clientes y órdenes de trabajo** para DELCO Chile.  
Producción: [inventario.delcochile.cl](https://inventario.delcochile.cl)

Integra formularios de terreno vía **MoreApp**, controla equipos (medidores, SIM, módems), gestiona OT y da seguimiento administrativo (SCi4, comunicación, cargas, comprobantes).

---

## 1. Qué es y para qué sirve

| Área | Permite |
|------|---------|
| **Inventario** | Controlar medidores, SIM y módems: estados, custodia, movimientos auditables |
| **Clientes** | Ficha del punto, historial, alarmas STB/SCi4, vínculo con equipos y OT |
| **Órdenes de trabajo** | Ciclo completo: asignación → ejecución → validación → cierre |
| **MoreApp** | Recibir informes de terreno, revisar, reprocesar y vincular a OT/cliente |
| **Administración** | Cargas de oficina, validación de comunicación, comprobantes PDF, reportes |

---

## 2. Stack técnico

| Ítem | Detalle |
|------|---------|
| Framework | Django 4.2 (compatible Python **3.8**) |
| API | Django REST Framework |
| Base de datos | MySQL en producción (PyMySQL); SQLite en desarrollo local |
| Hosting | Passenger / cPanel (Hostingplus) — `passenger_wsgi.py` |
| Dependencias | `requirements.txt` |
| Entorno local recomendado | `venv38` (misma versión de Python que el hosting) |

Apps Django instaladas:

`usuarios` · `ordenes_trabajo` · `web` · `clientes` · `inventario` · `importaciones` · `integraciones` · `catalogos` · `reportes` · `soporte` · `cargas`

---

## 3. Roles de usuario

| Rol | Uso típico |
|-----|------------|
| **ADMIN** | Acceso total: usuarios, inventario, OT, clientes, configuración |
| **ADMINISTRATIVO** | Validación de OT, SCi4, cargas, comunicación, comprobantes |
| **TECNICO** | Sus OT: ejecución, equipos, solicitud de comunicación, adjuntos |
| **GERENCIA** | Consulta / reportes / seguimiento |
| **AUDITOR** | Observación de OT, auditoría, sin validar cierre administrativo |

---

## 4. Módulos y qué incluyen

### 4.1 Inventario (`inventario`, vistas en `web`)
- Alta, edición, importación/exportación y modificación masiva de equipos
- Custodia por técnico, estados y ubicación
- Kardex de **movimientos** (origen/destino/responsable, tipo MoreApp)

### 4.2 Clientes (`clientes`)
- CRUD, historial, importación/exportación
- **SCi4 (base comercial externa, sin API):**
  - Estados: sin registro / pendiente / actualizado
  - Alerta al cambiar datos críticos (serie, módem, IP, puerto, SIM, etc.)
  - OT de tipo **CAMBIO / INSTALACIÓN / RETIRO** marca pendiente **solo si la ficha del cliente cambió**
  - Botón “Marcar actualizado en SCi4” en historial del cliente
- Alarmas operativas (STB / SCi4) en listado y dashboard

### 4.3 Órdenes de trabajo (`ordenes_trabajo`)
- Creación, listado con colas, asignación masiva, detalle completo
- Estados: asignada, en ejecución, pendiente validación, realizada, validada, observada, finalizada, cancelada, reasignada, etc.
- Validación administrativa y OT derivada al observar/rechazar
- Equipos en OT, adjuntos, informes PDF
- **Respaldo PDF MoreApp** cuando no llega por sincronización
- **Trabajos terminados:** `/ordenes/terminadas/` (Volver conserva `?desde=terminadas`)
- **Validación de comunicación:** técnico solicita prueba; admin registra Exitosa/Fallida
- **Comprobante de cambio de medidor:** solo **subida de PDF** existente (no genera acta ni firma en pantalla)
  - Listado: `/ordenes/comprobantes-cambio/`

### 4.4 Cargas administrativas (`cargas`)
- Hub y listado de tareas de oficina
- Tipos: validación OT, verificación SCi4, MoreApp, comunicación, etc.
- “Generar desde pendientes” (OT por validar, clientes SCi4, comunicación pendiente)
- Completar una carga SCi4 marca el cliente como actualizado (y viceversa)
- Orden de prioridad real: **ALTA → MEDIA → BAJA**

### 4.5 MoreApp e integraciones (`integraciones`, `reportes`)
- Webhook: `/api/moreapp-webhook/`
- Listado/detalle/sincronizar/reprocesar informes
- Estados de revisión: `PENDIENTE`, `CON_ADVERTENCIA`, `REVISADO`, `DESCARTADO`
- Cola operativa: `/operacional/pendientes/`

### 4.6 Otros
- **Reportes** hub y exportaciones
- **Auditoría** de eventos
- **Catálogos** (diagnóstico, etc.)
- **Soporte** (tickets / ayuda interna, si está habilitado)
- **Importaciones** con registro de errores y corrección de filas

---

## 5. Rutas funcionales clave

| Ruta | Descripción |
|------|-------------|
| `/dashboard/` | Indicadores y excepciones |
| `/inventario/` | Equipos |
| `/movimientos/` | Kardex |
| `/clientes/` | Clientes y alarmas |
| `/ordenes/` | Órdenes activas / colas |
| `/ordenes/terminadas/` | Trabajos cerrados |
| `/ordenes/comprobantes-cambio/` | Comprobantes PDF de cambio de medidor |
| `/cargas/` | Hub de cargas administrativas |
| `/reportes/moreapp/` | Informes MoreApp |
| `/operacional/pendientes/` | Cola de revisión operativa |
| `/auditoria/` | Eventos de auditoría |
| `/api/moreapp-webhook/` | Entrada de formularios MoreApp |

---

## 6. Flujo operativo recomendado

1. Revisar **dashboard** y alarmas (SCi4 / STB / envejecimiento).
2. Sincronizar o revisar **MoreApp** → cola `/operacional/pendientes/`.
3. Trabajar **OT** (técnico en terreno → validación administrativa → finalizada).
4. Si aplica cambio de medidor: **subir PDF** del comprobante en la OT.
5. Si el técnico pide prueba de red: **validación de comunicación** en el detalle.
6. Usar **cargas** (`/cargas/`) para repartir trabajo de oficina; “Generar desde pendientes”.
7. Tras actualizar la base comercial externa: marcar cliente **SCi4 actualizado**.
8. Ejecutar `verificar_calidad` en cierre diario/semanal.

---

## 7. Desarrollo local

### Requisitos
- Python **3.8** (recomendado: carpeta `venv38`, alineada al hosting)
- Dependencias de `requirements.txt`

### Arranque típico (Windows)

```powershell
cd DELCO_INVT
.\venv38\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver
```

### Comandos útiles

```bash
python manage.py check
python manage.py migrate
python manage.py inicializar_estados
python manage.py verificar_calidad --solo-reporte
python manage.py verificar_calidad
python manage.py test ordenes_trabajo.tests cargas.tests
```

Settings:
- Desarrollo: `config.settings` (vía `manage.py`)
- Producción (Passenger): `config.settings_production`

---

## 8. Despliegue en producción

1. `git pull` en la rama `Principal`
2. Instalar/actualizar dependencias si cambió `requirements.txt`
3. **Migrar siempre** tras pull:

```bash
python manage.py migrate
```

Migraciones recientes a tener en cuenta (si el servidor aún no las tiene):

- `clientes` — campos/estado SCi4  
- `ordenes_trabajo.0017+` — comunicación, etc.  
- `ordenes_trabajo.0018` — comprobante cambio medidor  
- `ordenes_trabajo.0019` — serie instalada del comprobante puede ir en blanco  
- `cargas.0001` — cargas administrativas  

4. Reiniciar la app Passenger / Python App en el panel del hosting  
5. Verificar login y rutas nuevas (`/cargas/`, `/ordenes/terminadas/`, comprobantes)

> La app `cargas` se importa en `web/urls.py` de forma fija: el deploy debe incluir la app y su migración o el sitio no arranca.

---

## 9. Seguridad y trazabilidad

- Acciones relevantes quedan con **usuario responsable** (movimientos, validaciones, SCi4, cargas, comunicación, comprobantes)
- MoreApp se traza por `submission_id` / sincronización
- Roles limitan vistas y acciones sensibles (exportación de clientes: ADMIN / ADMINISTRATIVO / GERENCIA / AUDITOR)
- Sesión con timeout absoluto (`AbsoluteSessionTimeoutMiddleware`)
- Auditoría consultable en `/auditoria/`
- **Secretos preferidos por entorno** (Passenger o `.env` en el servidor): `SECRET_KEY`, `DB_*`, `MOREAPP_WEBHOOK_SECRET` — ver `.env.example`
- Webhook `/api/moreapp-webhook/` exige secreto (`X-MoreApp-Secret` o `Authorization: Bearer …`); sin secreto → 403
- `/media/` y `/registros/evidencias/` requieren sesión autenticada
- En producción se carga `.env` del servidor si existe; si faltan variables, hay **fallbacks de compatibilidad** para no tumbar el sitio (definir env y rotar credenciales lo antes posible)

### Variables de entorno (producción / Passenger)

| Variable | Obligatoria | Notas |
|----------|-------------|--------|
| `SECRET_KEY` | Recomendada | Clave larga única (hay fallback temporal) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Recomendada | MySQL Hostingplus (hay fallbacks temporales) |
| `MOREAPP_WEBHOOK_SECRET` | Recomendada | Mismo valor configurado en MoreApp |
| `ALLOWED_HOSTS` | Recomendada | Lista separada por comas |
| `CSRF_TRUSTED_ORIGINS` | Recomendada | Con esquema `https://…` |
| `SECURE_SSL_REDIRECT` | Recomendada | `True` cuando el proxy envía `X-Forwarded-Proto` |
| `DEBUG` | — | Debe ser `False` en producción |

Tras rotar `DB_PASSWORD` o `MOREAPP_WEBHOOK_SECRET`, actualizar Passenger o el `.env` del servidor y MoreApp, luego reiniciar la app.

---

## 10. Feedback de producción (implementado)

Resumen de lo incorporado a partir del feedback operativo:

| ID | Entrega |
|----|---------|
| 1.1 | Respaldo PDF MoreApp en OT |
| 1.2 | Vista trabajos terminados + navegación Volver |
| 1.3 | Cargas administrativas |
| 2.1 / 2.1b | SCi4 visible + pendiente por cambios críticos / OT de equipo |
| 2.2 | Comprobante cambio medidor (solo upload PDF) |
| 3 | Validación de comunicación técnico ↔ administración |

Correcciones asociadas: sin serie falsa `VER_PDF`, cierre correcto de solicitudes de comunicación, prioridad de cargas, SCi4 solo con cambio real de ficha, sync carga↔SCi4, preservar `desde=terminadas` tras acciones en el detalle.

---

## 11. Estructura del repositorio (alto nivel)

```
DELCO_INVT/
├── config/              # settings, urls raíz, storage, wsgi
├── web/                 # vistas principales, urls, middleware, dashboards
├── usuarios/            # autenticación y roles
├── inventario/          # medidores, SIM, módems, movimientos
├── clientes/            # ficha cliente + lógica SCi4
├── ordenes_trabajo/     # OT, comunicación, comprobantes, sync inventario
├── cargas/              # tareas administrativas
├── integraciones/       # MoreApp y afines
├── reportes/            # hub reportes / MoreApp
├── importaciones/       # import Excel y errores
├── catalogos/           # catálogos auxiliares
├── soporte/             # soporte interno
├── templates/           # plantillas HTML
├── static/              # estáticos
├── media/               # archivos subidos (local)
├── requirements.txt
├── passenger_wsgi.py    # entrada Passenger producción
├── manage.py
└── README.md
```

---

## 12. Estado actual

- Base funcional activa en producción.
- Feedback operativo (SCi4, cargas, comunicación, comprobantes, terminadas, respaldo MoreApp) **implementado** en rama `Principal`.
- Tras cada deploy: **pull + migrate + reinicio**.

Para dudas de negocio o de despliegue, revisar este README y el historial de commits en `Principal`.
