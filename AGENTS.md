# AGENTS.md

## Cursor Cloud specific instructions

This is a Django project (`DELCO_INVT`) — inventory management with MoreApp integration. See `README.md` for functional routes and operational commands.

### Environment / how to run

- Python 3.12 with a virtualenv at `.venv`. The update script creates it and installs `requirements.txt`. Activate with `. .venv/bin/activate` before any `manage.py` command.
- Default dev settings are `config.settings` (used automatically by `manage.py`). It falls back to **SQLite** (`db.sqlite3`) whenever the `DB_*` env vars are absent — no MySQL is needed for local development.
- `config.settings_production` targets MySQL with hardcoded/prod credentials and is only for the Passenger/cPanel host; do not use it locally.
- Custom user model: login uses **RUT** as the username field (not email). `createsuperuser` won't prompt for the required `nombre`/`apellido`/`nombre_interno` fields, so create admins via `manage.py shell` using `Usuario.objects.create_superuser(rut=..., email=..., password=..., nombre=..., apellido=..., nombre_interno=...)`.
- After migrating, run `python manage.py inicializar_estados` to seed the standard inventory states.
- Run the dev server with `python manage.py runserver 0.0.0.0:8000`. Entry point `/` redirects to `/login/`; after login you land on `/dashboard/`.

### Tests / checks

- `python manage.py check` — Django system checks.
- The app-level `*/tests.py` files are empty scaffolds (no real unit tests). The root-level `test_*.py` / `comprehensive_test.py` files are **standalone diagnostic scripts**, not `TestCase`s — do NOT run them via `manage.py test` (auto-discovery breaks because `test_functional.py` calls `setup_test_environment()` at import). Run a standalone script directly, e.g. `python test_django.py`, or scope the runner to app labels (`python manage.py test usuarios inventario ...`).
