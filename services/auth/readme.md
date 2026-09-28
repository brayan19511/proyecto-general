# Auth: desarrollo guiado

El usuario implementará el servicio paso a paso. El asistente orienta y revisa; no genera la aplicación completa. Consulta [AGENTS.md](AGENTS.md) y la [guía](docs/desarrollo-guiado.md).

## Qué existe

- app/main.py: instancia de FastAPI con CORSMiddleware (allow_credentials=False). Aún no incluye routers.
- app/core/config.py: PROJECT_NAME, parámetros de conexión (DB_*) y CORS_ORIGINS.
- app/core/db/connection.py: URL, engine, SessionLocal y get_db. Conexión a PostgreSQL comprobada.
- app/core/security.py: hash y verificación de contraseñas con pwdlib (Argon2).
- app/models/entities.py: modelos de identidad, organización, sesiones, límites e historial/seguimiento en el schema `auth`.
- app/models/common/mixin_model.py: campos comunes; created_by/updated_by/deleted_by son FK nullable a users.id.
- app/schemas/user.py: UserCreate (extra="forbid") y UserResponse.
- app/repositories/user_repository.py y app/services/user_service.py: registro de usuario + perfil + historial en una transacción. Todavía sin ruta HTTP.
- app/api/routes/users_router.py: POST /users (registro).
- app/api/routes/seed_router.py + app/services/seed_service.py + app/seeds/data.py: POST /seed idempotente, protegido por SEED_ENABLED y X-Seed-Token.
- app/api/routes/auth_router.py + app/services/auth_service.py + app/core/tokens.py: POST /auth/login, /auth/refresh y /auth/logout (JWT RS256, refresh rotativo).
- app/api/dependencies.py: `get_current_user` (Bearer + sesión vigente en la base) y `require_seed_token`.
- app/api/routes/me_router.py: GET /me (usuario, sesión y membresías con puestos, áreas y roles) y GET /me/permissions (permisos efectivos en la empresa del header X-Company-Id).
- app/api/routes/areas_router.py + app/services/area_service.py + app/repositories/area_repository.py: CRUD de áreas de la empresa activa (plantilla de los demás CRUD). Ayudantes compartidos en app/services/common.py.
- app/api/routes/positions_router.py + app/services/position_service.py + app/repositories/position_repository.py: CRUD de puestos con alcance de área.
- app/api/routes/roles_router.py + app/services/role_service.py + app/repositories/role_repository.py: CRUD de roles y de sus permisos, con regla de delegación.
- app/services/position_role_service.py: roles de cada puesto (rutas en positions_router.py).
- app/api/routes/members_router.py + app/services/member_service.py + app/repositories/member_repository.py: miembros de la empresa y sus puestos.
- app/api/routes/me_router.py también: PATCH /me/profile y gestión de sesiones propias (/me/sessions).
- app/api/routes/admin_router.py + app/services/admin_service.py + app/repositories/admin_repository.py: vistas generales, empresas (crear, renombrar, activar/desactivar), usuarios, cierre de sus sesiones e historial (solo master admin).
- app/services/login_throttle.py: bloqueo de login tras 5 fallos por email + IP (rate_buckets).
- app/services/rate_limit.py + app/core/client_ip.py: límites de volumen por IP y proxies confiables.
- app/services/password_service.py: cambio de contraseña propio y por el master admin.
- app/services/profile_service.py + app/api/routes/profile_router.py: perfil propio (GET/PATCH /auth/me/profile) y documentos (/auth/me/documents).
- app/services/identity_service.py + app/api/routes/catalog_router.py: catálogo de países y tipos de documento, reglas de documentos.
- app/services/api_key_service.py + app/api/routes/api_keys_router.py: API keys (header X-API-Key).
- app/api/routes/history_router.py: GET /history de la empresa activa (history.read).
- app/core/permissions.py: catálogo de permisos y scopes admitidos.
- app/services/access_service.py + app/repositories/access_repository.py: contexto de empresa, permisos efectivos y `CompanyContext.can()`; dependencias `get_company_context` y `require_permission` en app/api/dependencies.py.
- scripts/generate_jwt_keys.py: genera secrets/jwt_private.pem y jwt_public.pem (RS256). secrets/ no se versiona.
- migrations/: Alembic configurado y limitado al schema `auth`. Revisiones aplicadas hasta `8baed1d57096` (head).
- Logs: paquete compartido `../../packages/platform-audit` (schema `audit`), con AuditMiddleware en main.py, pasos en login y seed, y consulta en GET /admin/logs (app/api/routes/logs_router.py). Migrar con `python scripts/migrate_audit.py`.
- requirements.txt: FastAPI, Uvicorn, pydantic-settings, SQLAlchemy, Psycopg 3, Alembic, pwdlib[argon2] y PyJWT[crypto].
- .env.example: variables de configuración sin valores.

No existen todavía: recuperación autónoma de cuenta ni pruebas automatizadas.

Motor vigente: solo PostgreSQL (decisión del usuario). SQL Server es un objetivo futuro; los pendientes para activarlo están en [base-de-datos.md](docs/base-de-datos.md).

## Historia breve

Se retiró una implementación anticipada del asistente (rutas, seed/CLI, JWT, límites, business.py, Docker). Después el usuario incorporó configuración, conexión, Alembic, hash de contraseñas y el service de registro paso a paso. El .env local se preservó.

## Inicio mínimo

Desde esta carpeta y con el entorno activado:

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python scripts/migrate_audit.py
python -m uvicorn app.main:app --reload
```

**Todas las rutas del servicio llevan el prefijo `/auth`** (p. ej. `/auth/login`,
`/auth/me`, `/auth/areas`). Swagger: http://127.0.0.1:8000/auth/docs.
Comprobaciones: `GET /auth/health` (proceso vivo) y `GET /auth/ready` (la base responde; 503 si no).

## Docker

El build se hace desde la **raíz del repositorio** (la imagen incluye `packages/platform-audit`):

```powershell
cd D:\proyectos\proyecto-general
docker build -f services/auth/Dockerfile -t auth:0.1.0 .
```

La imagen no contiene secretos. Al ejecutarla se entregan la configuración y
las claves JWT (volumen de solo lectura en `/app/services/auth/secrets`):

```powershell
docker run --rm -p 8001:8000 `
  -v D:\proyectos\proyecto-general\services\auth\.env:/app/services/auth/.env:ro `
  -v D:\proyectos\proyecto-general\services\auth\secrets:/app/services/auth/secrets:ro `
  -e DB_HOST=host.docker.internal `
  auth:0.1.0
```

- `DB_HOST`: desde un contenedor, `localhost` es el propio contenedor. Usa
  `host.docker.internal` para la base publicada en tu máquina, o el nombre del
  servicio (`db`) si auth y PostgreSQL están en el mismo Compose.
- Si pasas la configuración con `docker run --env-file`, los valores **no deben
  llevar comillas**: `--env-file` las conserva como parte del valor
  (`DB_PASSWORD="x"` se lee con comillas). Montar el `.env` como archivo, o
  `env_file` de Docker Compose, sí las interpretan.
- Migraciones: son un paso aparte, no se ejecutan al arrancar:
  `docker run --rm ... auth:0.1.0 sh -c "python -m alembic upgrade head && python scripts/migrate_audit.py"`.
- Corre como usuario sin privilegios (`appuser`), con HEALTHCHECK sobre `/auth/health`
  y Uvicorn con `--no-proxy-headers` (la IP real la resuelve `TRUSTED_PROXIES`).
- Detrás de la API central: `TRUSTED_PROXIES` acepta IPs exactas o rangos CIDR
  (`["127.0.0.1"]` en desarrollo sin Docker; el rango de una red exclusiva de la
  central y auth en Docker). Ver services/apigateway/readme.md.

En Compose, auth ya está en `services/apigateway/docker-compose.yml`, sin puertos
publicados y accesible solo a través de la central. Ver services/apigateway/readme.md.

## Documentación

- [Arquitectura](../../docs/arquitectura.md)
- [Requisitos](docs/requisitos.md)
- [Modelo y diferencias pendientes](docs/modelo-datos.md)
- [Desarrollo guiado, seed y configuraciones](docs/desarrollo-guiado.md)
- [Conexión y migraciones](docs/base-de-datos.md)

## Siguientes pasos propuestos

Ver el orden en [desarrollo-guiado.md](docs/desarrollo-guiado.md#orden-propuesto-sin-implementación-automática). Pendientes priorizados: ver la sección "Pendientes" de [desarrollo-guiado.md](docs/desarrollo-guiado.md).
