# API central (apigateway)

API Gateway de la plataforma: entrada pública, límites generales, reenvío a los
servicios y coordinación. Python + FastAPI, creado desde `services/base`.

## Estado

- Paso 1 (hecho): configuración, `GET /health`, `GET /ready` y logs (schema `audit`, `service=apigateway`).
- Paso 2 (hecho): reenvío a auth; generalizado (2026-09-30) a varios servicios
  (`app/api/routes/proxy.py`): auth, libro-mayor, notificaciones y
  pagos-proveedores (2026-10-01).
- Paso 3 (hecho): `TRUSTED_PROXIES` con IPs o rangos CIDR (auth y `platform-audit`).
- Compose (hecho): db, pgAdmin, auth, libro-mayor (API y worker),
  notificaciones (API y worker), pagos-proveedores y la central, con redes
  exclusivas entre la central y cada servicio.
- Módulos, etapa 1 (hecho): `AUTH_ENABLED` por configuración.
- Administración (hecho): validación de administrador vía `GET /auth/me` y
  `GET /gateway/admin/logs[/{id}]`.
- Módulos, etapa 2 (hecho): estado de servicios en base (schema `gateway`,
  Alembic, historial), releído cada 5 s. Auth solo por configuración.
- Lista negra de IPs (hecho): `gateway.ip_blocks`, 403 antes de enrutar, releída cada 5 s.
- Siguiente: límites por IP (rate limit) y la aplicación web de administración.
  Ver [docs/modulos-y-administracion.md](docs/modulos-y-administracion.md).

Rutas propias en la raíz (sin prefijo): `/health`, `/ready`, `/docs`.
`/ready` solo revisa dependencias propias de la central (la base de logs); no
consulta a los servicios: si uno cae, la central sigue lista y responde error solo en sus rutas.

## Reenvío a los servicios

Servicios publicados (registro en `app/core/services.py`):

| Servicio | Prefijo | Variables | Default | Panel |
| --- | --- | --- | --- | --- |
| auth | `/auth` | `AUTH_ENABLED`, `AUTH_URL`, `AUTH_TIMEOUT_SECONDS` | habilitado, 30 s | No (solo configuración) |
| libro-mayor | `/libro-mayor` | `LIBRO_MAYOR_ENABLED`, `LIBRO_MAYOR_URL`, `LIBRO_MAYOR_TIMEOUT_SECONDS` | **deshabilitado**, 30 s | Sí |
| notificaciones | `/notificaciones` | `NOTIFICACIONES_ENABLED`, `NOTIFICACIONES_URL`, `NOTIFICACIONES_TIMEOUT_SECONDS` | **deshabilitado**, 30 s (`POST /dispatches` 120 s, `POST /smtp-accounts/...` 130 s) | Sí |
| pagos-proveedores | `/pagos-proveedores` | `PAGOS_PROVEEDORES_ENABLED`, `PAGOS_PROVEEDORES_URL`, `PAGOS_PROVEEDORES_TIMEOUT_SECONDS` | **deshabilitado**, 30 s (`POST /batches...`: crear y enviar lotes, 300 s) | Sí |

Headers propios de notificaciones (2026-10-01): la central reenvía `Idempotency-Key`
(y la admite en CORS) y devuelve `X-Content-Type-Options` y `Cache-Control` de
cualquier servicio. Pendiente: la central lee el cuerpo entero en memoria antes de
reenviarlo (`await request.body()`); un multipart de 100 MB ocupa 100 MB mientras pasa.

| Qué | Cómo |
| --- | --- |
| Rutas publicadas | `app/core/public_routes.py`: por servicio, `Route(prefijo, métodos, timeout)`. Lo que no está responde 404 sin llegar al servicio. Paths con `.` o `..` se rechazan |
| Dejar de publicar algo | Borrar/comentar su línea o quitar un método, y redesplegar. Para ser más fino: una línea más específica en lugar de la general |
| Path | Sin reescribir: `/auth/login` en la central = `/auth/login` en auth |
| Habilitado | `<SERVICIO>_ENABLED`. `false`: sus rutas responden 503 sin llegarle; el servicio sigue corriendo. Aplicar con `docker compose restart apigateway`. Los que tienen panel se apagan también desde `/gateway/admin/services` sin reiniciar |
| Timeout | `<SERVICIO>_TIMEOUT_SECONDS` (30); una ruta puede tener el suyo (`/libro-mayor/live-queries`: 130 s). Agotado: 504. Servicio caído: 502. Mensajes genéricos |
| Reintentos | Ninguno: una mutación podría haberse aplicado |
| Streaming | Todas las respuestas: los bytes pasan a medida que llegan, sin cargarse enteros en memoria (el CSV de libro-mayor). Con streaming, el timeout es la espera para conectar y entre trozos, no la duración total. Si el servicio corta a mitad, la respuesta queda incompleta y el cliente lo detecta |
| gzip | Se reenvía tal cual: la central pasa el `Accept-Encoding` del cliente y devuelve los bytes sin descomprimir con su `Content-Encoding`. Sin `Accept-Encoding` del cliente pide `identity`. Cada servicio decide si comprime (libro-mayor sí, más de 1 KB; auth no) |
| Headers hacia el servicio | Lista positiva: Content-Type, Accept, Accept-Encoding, Authorization, X-Company-Id, X-API-Key, X-Seed-Token, User-Agent |
| Headers de vuelta | Content-Type, Content-Encoding, Content-Length, Content-Disposition, Retry-After y el X-Trace-Id de la central |
| Respuestas del servicio | Se devuelven tal cual (401, 429… no son fallas de la central) |

### Publicar un servicio nuevo

1. `config.py`: `<SERVICIO>_ENABLED` (false por defecto), `<SERVICIO>_URL` y
   `<SERVICIO>_TIMEOUT_SECONDS`, más su validación (URL obligatoria si está
   habilitado).
2. `public_routes.py`: su lista de rutas (solo lo que debe ser público).
3. `services.py`: su entrada en `SERVICES` (prefijo, URL, timeout, rutas,
   `panel_managed`). El reenvío y el cliente HTTP salen de ahí.
4. `app/core/audit.py`: campos sensibles propios de sus bodies, si los tiene.
5. `desarrollo/plataforma-completa/docker-compose.yml`: sus contenedores, su red exclusiva con la central
   (subred fija en su `TRUSTED_PROXIES`) y `<SERVICIO>_URL`.
6. `.env.template` y esta tabla.

### Logs y correlación

Una solicitud genera dos filas en `audit.logs` con el mismo `trace_id`:

| service | parent_operation_id | ip_address |
| --- | --- | --- |
| apigateway | NULL (borde público) | IP de quien conectó a la central |
| auth | id de la fila de la central | la misma IP (vía X-Forwarded-For) |

La central envía `X-Trace-Id`, `X-Parent-Operation-Id` y `X-Forwarded-For`; auth
los acepta solo porque la conexión viene de su `TRUSTED_PROXIES`. La diferencia
de `duration_ms` entre ambas filas es el costo de la central y la red.

La central guarda los bodies que reenvía, enmascarados: `app/core/audit.py`
incluye los campos extra que oculta auth. Al publicar otro servicio, agregar los
suyos (libro-mayor no lleva secretos en sus bodies: las credenciales SAP son
variables de entorno). Las respuestas se guardan solo con error (≥ 400).

### IP del cliente

- Cliente directo: la central descarta cualquier `X-Forwarded-For` recibido
  (se registra en los headers, pero no se usa) y envía la IP de la conexión.
- Detrás de Nginx o un balanceador: poner su IP o rango en `TRUSTED_PROXIES`
  de la central; entonces conserva la cadena y agrega la IP del proxy.

| Entorno | IP que ve la central | IP que ve auth | TRUSTED_PROXIES de auth |
| --- | --- | --- | --- |
| Local sin Docker | 127.0.0.1 | 127.0.0.1 | `["127.0.0.1"]` (solo desarrollo) |
| Docker Desktop | gateway de Docker (172.x.0.1), igual para todos | IP del contenedor de la central | rango de la red exclusiva |
| Servidor con Nginx | IP de Nginx (la real viene en X-Forwarded-For) | IP de la central | rango de la red exclusiva |
| Docker detrás de caddy (este compose) | la del cliente que informa caddy (`proxy-net` en `TRUSTED_PROXIES`); en Docker Desktop es la del host | IP de la central | rango de la red exclusiva |

### Docker: redes

`desarrollo/plataforma-completa/docker-compose.yml` levanta db, pgAdmin, auth, libro-mayor, la central, el front y caddy:

| Red | Quién | Para qué |
| --- | --- | --- |
| `edge` | central | publica `127.0.0.1:${GATEWAY_PORT:-8001}` (solo esta máquina) |
| `auth-net` (172.30.0.0/24, `internal`) | central, auth | única red en la que auth confía (`TRUSTED_PROXIES`) |
| `data` | db, pgAdmin, auth, central | base de datos |
| `proxy-net` (172.32.0.0/24, `internal`) | caddy (172.32.0.10), central, front, pgAdmin | caddy llega a cada uno por su alias `*.proxy`; la central solo confía en el `X-Forwarded-For` que llega por esta red |

- Auth no publica puertos: desde fuera solo se llega a través de la central.
- La central llama a `http://auth.internal:8000`: ese alias existe solo en
  `auth-net`, así la conexión sale siempre desde la IP confiable. Por `data`
  auth también es alcanzable, pero sin confianza (la traza y la IP se ignoran).
- Confiar en un rango confía en todo contenedor de esa red: no agregar otros servicios a `auth-net`.

### Acceso desde la red (HTTPS con caddy)

Caddy (`services/edge`) es la única entrada desde otros equipos: `/` (front),
`/auth`, `/libro-mayor` y `/gateway` (la central) y el puerto 8443 (pgAdmin).
Por ahora en modo `http` (`http://<IP de la PC>/`); con dominio, `dns` (HTTPS). Rechaza solicitudes de más
de 100 MB (413). La base no se publica a la red (`DB_BIND=127.0.0.1`).

| Variable (`.env`) | Default | Para qué |
| --- | --- | --- |
| `EDGE_BIND` | `127.0.0.1` | `0.0.0.0` para entrar desde otros equipos |
| `SITE_ADDRESS` | `localhost` | nombre o IP con que se entra (debe coincidir con la URL) |
| `CADDY_TLS` | `http` | `http` = red local sin dominio (`http://<IP>/`, sin cifrado); `internal` = CA propia (solo esta máquina); `dns` = dominio propio + Let's Encrypt (ver `services/edge/README.md`) |
| `EDGE_HTTP_PORT` / `EDGE_HTTPS_PORT` / `EDGE_PGADMIN_PORT` | 80 / 443 / 8443 | puertos publicados |
| `GATEWAY_BIND`, `DB_BIND` | `127.0.0.1` | acceso directo (desarrollo); no abrirlos a la red |

Para entrar desde otros equipos: `CADDY_TLS=http` (sin dominio) o `dns` (dominio
propio, HTTPS); en ninguno hay que instalar nada. Con `internal`, cada equipo tendría que confiar en la CA de Caddy (si
no, el navegador advierte y el portapapeles no funciona); su raíz se exporta
así (desde `desarrollo/plataforma-completa`):

```bash
MSYS_NO_PATHCONV=1 docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

La CA vive en el volumen `caddy_data`: borrarlo genera otra y hay que volver a
instalarla. Para DBeaver desde otro equipo: túnel SSH a esta máquina
(`ssh -L 5432:localhost:5432 usuario@host`), no abrir la base.

## Administración (`/gateway/admin/...`)

Solo para el administrador de plataforma. La central valida el Bearer
preguntando a auth (`GET /auth/me`, exige `is_platform_admin=true`); ver
`app/api/dependencies.py`. Probar: `POST /auth/login` en http://localhost:8001/auth/docs,
copiar el `access_token`, "Authorize" en http://localhost:8001/docs y llamar a
`GET /gateway/admin/logs`.

| Ruta | Qué devuelve |
| --- | --- |
| `GET /gateway/admin/logs` | Cabeceras de la central, más recientes primero. Filtros: `trace_id`, `user_id`, `outcome`, `path_prefix`, `limit`, `offset` |
| `GET /gateway/admin/logs/{id}` | Cabecera + detalles (request, response, errores) + pasos |
| `GET /gateway/admin/services` | Estado de cada servicio publicado (efectivo, configuración, base) |
| `PATCH /gateway/admin/services/{service}` | Habilitar/deshabilitar desde el panel (auth: 409, solo por configuración) |
| `GET /gateway/admin/history` | Historial de cambios de la central (`resource_type`: `service_state`, `ip_block`) |
| `GET / POST /gateway/admin/ip-blocks`, `DELETE /gateway/admin/ip-blocks/{id}` | Lista negra: listar, bloquear IP o rango (con vencimiento opcional), desbloquear (baja lógica) |

Si un bloqueo deja fuera a quien no debía: `IP_BLOCKS_ENABLED=false` en el `.env`
y `restart apigateway` (`docker compose --env-file ../../services/apigateway/.env …` desde `desarrollo/plataforma-completa`). La API ya impide bloquear tu propia IP.

Los de auth siguen en `/auth/admin/logs`; se relacionan por `trace_id`.

## Configuración

Un `.env` en esta carpeta sirve al Compose de desarrollo completo
(`desarrollo/plataforma-completa`, con `--env-file`) y a la aplicación (ver
`.env.template`). La base puede estar en Docker, en tu PC o en
la nube: solo cambia `DB_HOST`/`DB_PORT` (desde un contenedor, `localhost` es
el propio contenedor; usa `host.docker.internal` o `db`).

## Inicio mínimo

Desde esta carpeta y con un entorno virtual activado (auth en el puerto 8000, la central en el 8001):

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python scripts/migrate_audit.py
python -m uvicorn app.main:app --reload --port 8001 --no-proxy-headers
```


## Docker

El Compose de desarrollo está en `desarrollo/plataforma-completa` (uno por
servicio en `desarrollo/<servicio>`, producción en `produccion/`). Usa el `.env`
de aquí (base, pgAdmin, puertos, binds) con `--env-file` y monta el `.env` y
`secrets/` de auth y el `.env` de libro-mayor; los valores propios de
Docker (DB_HOST=db, TRUSTED_PROXIES, AUTH_URL, LIBRO_MAYOR_URL) están en
`environment` del Compose.

libro-mayor en el Compose: `libro-mayor-migrate`, `libro-mayor` (API, sin
puerto publicado) y `libro-mayor-worker` (sincronización programada y
reclasificaciones; `restart: unless-stopped`). Su `.env` debe usar el mismo
`DB_NAME`, `DB_USER` y `DB_PASSWORD` que la base del Compose. La red
`sap-egress` les da salida hacia SAP HANA. Para publicarlo por la central:
`LIBRO_MAYOR_ENABLED=true` en el `.env` de aquí y `restart apigateway`.

```powershell
cd ..\..\desarrollo\plataforma-completa
docker compose --env-file ../../services/apigateway/.env up -d --build
docker compose --env-file ../../services/apigateway/.env ps
docker compose --env-file ../../services/apigateway/.env logs -f apigateway auth
```

Para no repetir `--env-file`, copiar `services/apigateway/.env` a
`desarrollo/plataforma-completa/.env` (ignorado por git).

- Detén antes los Uvicorn locales que usen el puerto 8001, o define
  `GATEWAY_PORT=8002` en el `.env`.
- Nombre de proyecto `proyecto-central`: reutiliza el contenedor y el volumen `db` existentes.
- Migraciones automáticas en cada `up`: `auth-migrate` y `apigateway-migrate`
  (y `libro-mayor-migrate`) son contenedores de un solo uso con la misma imagen
  que su app. Aplican `alembic upgrade head` y el schema `audit`, y terminan;
  cada app arranca solo si su migración terminó bien. Van en cadena
  (auth → apigateway → libro-mayor) porque todos migran `audit`. Sin cambios
  pendientes no hacen nada. Si una app no arranca, revisar primero
  `docker compose logs auth-migrate apigateway-migrate libro-mayor-migrate`.
- Los seeds no son automáticos (acuerdo): tras una base nueva (`down -v`),
  habilitar `SEED_ENABLED`, ejecutar `POST /auth/seed` y volver a deshabilitarlo.
- Versiones de imagen: `AUTH_IMAGE`, `APIGATEWAY_IMAGE` y `LIBRO_MAYOR_IMAGE` en `.env` (default `auth:0.1.0`, `apigateway:0.1.0`, `libro-mayor:0.1.0`).
- `docker compose down` detiene todo; los datos siguen en el volumen `db`.
  `docker compose down -v` borra también el volumen: la base queda vacía y la
  siguiente `up` la migra desde cero.

## Cómo probar

Todo va contra la central (`http://localhost:8001`), con las mismas rutas de auth:

| Qué | URL |
| --- | --- |
| Swagger de auth, a través de la central | http://localhost:8001/auth/docs |
| Swagger propio de la central (solo health/ready) | http://localhost:8001/docs |
| Estado de la central / de auth | `/health`, `/ready` / `/auth/health`, `/auth/ready` |

En `/auth/docs`, "Try it out" llama a `/auth/...` del mismo origen, o sea, pasa
por la central. Flujo: `POST /auth/login` → copiar `access_token` → "Authorize"
→ probar `GET /auth/me`.

Cada respuesta trae `X-Trace-Id`. Para ver las dos operaciones (pgAdmin o psql):

```sql
select service, parent_operation_id, ip_address, status_code, duration_ms
from audit.logs where trace_id = '<X-Trace-Id>' order by started_at;
```

Esperado: una fila `apigateway` y otra `auth` con `parent_operation_id` = id de
la primera y la misma IP. En Docker Desktop esa IP es la del gateway de Docker
(172.x.0.1), no 127.0.0.1: es como Docker entrega las conexiones del host.
