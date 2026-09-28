# Plantilla de servicio FastAPI

Lee las instrucciones raíz (`AGENTS.md`) y `docs/arquitectura.md`. Esta carpeta
no es un servicio desplegable: es el punto de partida para copiar uno nuevo.

## Qué trae

- `app/core/config.py`: nombre/versión, logs, base de datos, CORS y `TRUSTED_PROXIES`.
- `app/core/db/connection.py`: engine y sesiones SQLAlchemy (PostgreSQL; SQL Server por validar).
- `app/core/audit.py` + `AuditMiddleware` en `main.py`: logs en el schema `audit` (packages/platform-audit).
- `GET /<prefijo>/health` (proceso vivo) y `GET /<prefijo>/ready` (la base responde; 503 si no).
- `Dockerfile` (build desde la raíz del repo), `requirements.txt`, `.env.example`, `scripts/migrate_audit.py`.

## Crear un servicio nuevo

1. Copiar `services/base` a `services/<servicio>` (sin `.env`, `enviroment/`, `__pycache__/`).
2. Reemplazar "base" por el nombre: `PREFIX` en `main.py`, defaults de `config.py`,
   rutas/tag/HEALTHCHECK del `Dockerfile` y `SERVICE_NAME` del `.env.example`.
3. Crear el `.env` propio del servicio a partir de `.env.example`.
4. Si tiene tablas: schema propio en `Base.metadata`, Alembic limitado a ese schema
   y `COPY` de `migrations/` y `alembic.ini` en el Dockerfile.

## Pendiente de revisar

`app/models/`, `migrations_example/` y `docs/` son copias antiguas de auth
(tablas de usuarios, FK a `users.id`). No usarlas en un servicio nuevo: otro
servicio no puede tener FK a tablas de auth. El modelo común de atribución para
servicios que no sean auth está pendiente de decisión.
