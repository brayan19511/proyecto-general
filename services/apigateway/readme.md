# API central (apigateway)

API Gateway de la plataforma: entrada pública, límites generales, reenvío a los
servicios y coordinación. Python + FastAPI, creado desde `services/base`.

## Estado

- Paso 1 (hecho): configuración, `GET /health`, `GET /ready` y logs (schema `audit`, `service=apigateway`).
- Paso 2 (hecho): reenvío a auth (`app/api/routes/auth_proxy.py`).
- Paso 3 (hecho): `TRUSTED_PROXIES` con IPs o rangos CIDR (auth y `platform-audit`).

Rutas propias en la raíz (sin prefijo): `/health`, `/ready`, `/docs`.
`/ready` solo revisa dependencias propias de la central (la base de logs); no
consulta a auth: si auth cae, la central sigue lista y responde error solo en `/auth/*`.

## Reenvío a auth

| Qué | Cómo |
| --- | --- |
| Rutas publicadas | `PUBLIC_ROUTES` en `auth_proxy.py`: (prefijo, métodos). Lo que no está responde 404 sin llegar a auth. Paths con `.` o `..` se rechazan |
| Dejar de publicar algo | Borrar/comentar su línea o quitar un método, y redesplegar. Para ser más fino: una línea más específica en lugar de la general |
| Path | Sin reescribir: `/auth/login` en la central = `/auth/login` en auth |
| Timeout | `AUTH_TIMEOUT_SECONDS` (30). Agotado: 504. Auth caída: 502. Mensajes genéricos |
| Reintentos | Ninguno: una mutación podría haberse aplicado |
| Headers hacia auth | Lista positiva: Content-Type, Accept, Authorization, X-Company-Id, X-API-Key, X-Seed-Token, User-Agent |
| Headers de vuelta | Content-Type, Retry-After y el X-Trace-Id de la central |
| Respuestas de auth | Se devuelven tal cual (401, 429… no son fallas de la central) |

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
incluye los campos extra que oculta auth. Al publicar otro servicio, agregar los suyos.

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

### Docker: redes

`docker-compose.yml` levanta db, pgAdmin, auth y la central:

| Red | Quién | Para qué |
| --- | --- | --- |
| `edge` | central | publica `127.0.0.1:${GATEWAY_PORT:-8001}` (solo esta máquina) |
| `auth-net` (172.30.0.0/24, `internal`) | central, auth | única red en la que auth confía (`TRUSTED_PROXIES`) |
| `data` | db, pgAdmin, auth, central | base de datos |

- Auth no publica puertos: desde fuera solo se llega a través de la central.
- La central llama a `http://auth.internal:8000`: ese alias existe solo en
  `auth-net`, así la conexión sale siempre desde la IP confiable. Por `data`
  auth también es alcanzable, pero sin confianza (la traza y la IP se ignoran).
- Confiar en un rango confía en todo contenedor de esa red: no agregar otros servicios a `auth-net`.

## Configuración

Un `.env` en esta carpeta sirve al Compose (db, pgAdmin, auth, central) y a la
aplicación (ver `.env.template`). La base puede estar en Docker, en tu PC o en
la nube: solo cambia `DB_HOST`/`DB_PORT` (desde un contenedor, `localhost` es
el propio contenedor; usa `host.docker.internal` o `db`).

## Inicio mínimo

Desde esta carpeta y con un entorno virtual activado (auth en el puerto 8000, la central en el 8001):

```powershell
python -m pip install -r requirements.txt
python scripts/migrate_audit.py
python -m uvicorn app.main:app --reload --port 8001 --no-proxy-headers
```


## Docker

Desde esta carpeta. Usa el `.env` de aquí (base, pgAdmin, puertos) y monta el
`.env` y `secrets/` de auth; los valores propios de Docker (DB_HOST=db,
TRUSTED_PROXIES, AUTH_URL) están en `environment` del Compose.

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f apigateway auth
```

- Detén antes los Uvicorn locales que usen el puerto 8001, o define
  `GATEWAY_PORT=8002` en el `.env`.
- Nombre de proyecto `proyecto-central`: reutiliza el contenedor y el volumen `db` existentes.
- Migraciones: paso aparte, no se ejecutan al arrancar (idempotentes):
  `docker compose run --rm auth sh -c "python -m alembic upgrade head && python scripts/migrate_audit.py"`
  y `docker compose run --rm apigateway python scripts/migrate_audit.py`.
- Versiones de imagen: `AUTH_IMAGE` y `APIGATEWAY_IMAGE` en `.env` (default `auth:0.1.0`, `apigateway:0.1.0`).
- `docker compose down` detiene todo; los datos siguen en el volumen `db`.

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
