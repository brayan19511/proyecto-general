# Integración con la API central

Estado (2026-09-30): implementado. La central publica libro-mayor con su
reenvío genérico (`services/apigateway/app/api/routes/proxy.py`), **apagado por
defecto**. Falta activarlo en un entorno real y probar contra HANA.

## Activar

1. En `services/apigateway/.env`: `LIBRO_MAYOR_ENABLED=true`. En el Compose,
   `LIBRO_MAYOR_URL` ya apunta a `http://libro-mayor.internal:8000`; fuera de
   Docker, poner la dirección local (p. ej. `http://127.0.0.1:8002`).
2. `docker compose --env-file ../../services/apigateway/.env up -d --build` desde `desarrollo/plataforma-completa` (levanta
   `libro-mayor-migrate`, `libro-mayor` y `libro-mayor-worker`) o, si ya
   estaban arriba, `docker compose restart apigateway`.
3. Comprobar: `GET http://127.0.0.1:8001/libro-mayor/health` a través de la
   central.

Apagarlo sin reiniciar: `PATCH /gateway/admin/services/libro-mayor` desde el
panel (administrador de plataforma). Sus rutas responden 503 y el servicio y el
worker siguen corriendo.

## Qué publica la central

Lista explícita en `services/apigateway/app/core/public_routes.py`
(`LIBRO_MAYOR_ROUTES`); lo demás responde 404 sin llegar al servicio.

| Prefijo | Métodos | Nota |
| --- | --- | --- |
| `/libro-mayor/health`, `/ready`, `/docs`, `/redoc`, `/openapi.json` | GET | |
| `/libro-mayor/accounts`, `/categories`, `/rules`, `/cost-center-mappings` | GET, POST, PATCH, DELETE | Incluye `/rules/import` y `/cost-center-mappings/import` |
| `/libro-mayor/cost-centers`, `/sync-status`, `/ledger` | GET | `/ledger` = `lines`, `lines.csv`, `summary` |
| `/libro-mayor/sync-runs`, `/classification-runs` | GET, POST, PATCH, DELETE | El servicio solo implementa GET y POST |
| `/libro-mayor/live-queries` | POST | Timeout propio: 130 s |
| `/libro-mayor/admin/sap-company` | GET, POST, PATCH, DELETE | Admin de plataforma (lo valida el servicio) |
| `/libro-mayor/admin/logs` | GET | Admin de plataforma |
| `/libro-mayor/admin/seed` | POST | Solo existe con `SEED_ENABLED=true` (decisión del usuario: igual que auth) |

## Cómo reenvía

- **Sin reescribir el path**, sin reintentos. 404 si no está publicado, 503
  deshabilitado, 504 timeout, 502 caído.
- **Timeout**: `LIBRO_MAYOR_TIMEOUT_SECONDS` (30) y 130 s para
  `/live-queries` (libro-mayor corta a los 120 s y devuelve su propio 504).
- **Streaming** en todas las respuestas (decisión del usuario): el CSV de un año
  pasa por la central sin cargarse en memoria. El timeout es la espera entre
  trozos, no la duración de la descarga.
- **gzip tal cual** (decisión del usuario): la central pasa el
  `Accept-Encoding` del cliente y devuelve los bytes comprimidos por
  libro-mayor con su `Content-Encoding`; no comprime ni descomprime.
- **Content-Disposition** llega al cliente (nombre del CSV) y está expuesto en
  CORS para el navegador.
- La central no autoriza: libro-mayor valida identidad y permisos con auth en
  cada solicitud.

## Contenedores (en `desarrollo/plataforma-completa/docker-compose.yml`)

| Contenedor | Qué hace | Redes |
| --- | --- | --- |
| `libro-mayor-migrate` | `alembic upgrade head` + schema `audit`; después de `apigateway-migrate` | data |
| `libro-mayor` | API, sin puerto publicado; `TRUSTED_PROXIES` = `172.31.0.0/24` | data, auth-net, sap-egress, libro-mayor-net (`libro-mayor.internal`) |
| `libro-mayor-worker` | Sincronización programada y reclasificaciones (`restart: unless-stopped`) | data, sap-egress |

- `libro-mayor-net` es interna (solo la central y libro-mayor). `sap-egress` da
  salida hacia el HANA, que está fuera de la plataforma.
- El `.env` de libro-mayor (montado de solo lectura) debe usar la misma base
  del Compose (`DB_NAME`, `DB_USER`, `DB_PASSWORD`); `DB_HOST`, `AUTH_URL` y
  `TRUSTED_PROXIES` los fija el Compose.
- libro-mayor llama a auth por `auth-net`, que está en el `TRUSTED_PROXIES` de
  auth: auth confía en el `X-Forwarded-For` que envíe (es lo que enlaza los
  logs).
- Puede haber más de un worker (`SKIP LOCKED`, turnos sin duplicar); con uno basta.

## Antes de producción

1. Probar contra HANA real desde el contenedor (`scripts/check_sap.py`).
2. Confirmar `SYNC_SCHEDULE` y `SAP_TIMEZONE`.
3. En auth: volver a ejecutar el seed (crea `ledger.*`), crear las áreas y
   asignar los permisos `ledger.*` a los roles de los puestos.
4. Cargar las reglas (`data/import/reglas_rash_peru.json`) y la homologación
   (`data/import/homologacion_rash_peru.json`), primero con `dry_run: true`.
5. Crear las API keys de Power BI o Excel con `ledger.view`.
6. Usar credenciales SAP de solo lectura propias del servicio (no las de un
   administrador) y rotar las que se hayan compartido.
