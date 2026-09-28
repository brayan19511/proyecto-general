# Módulos, lista negra y administración de la central

Objetivo: desactivar un servicio (módulo) de forma rápida y controlada, sin
detener los demás ni el propio servicio, y preparar la administración que luego
usará una aplicación web.

Estado: implementados la **etapa 1** (`AUTH_ENABLED`), la **validación del
administrador**, la **consulta de logs**, la **etapa 2** (estado de servicios en
base, TTL 5 s) y la **lista negra de IPs**. Pendiente: límites por IP (rate limit).

## Qué significa "deshabilitar un servicio"

- La central deja de enviarle tráfico: sus rutas publicadas responden
  **503** `{"detail": "El servicio <x> está deshabilitado."}` sin contactarlo.
- El servicio **no se detiene**: su contenedor sigue vivo (mantenimiento,
  migraciones, llamadas internas). Detenerlo es otra acción (`docker compose stop`),
  con otro resultado (la central respondería 502).
- Los demás servicios y la central siguen funcionando; `/ready` de la central no cambia.
- Deshabilitar no borra ni concede nada: habilitar un servicio no otorga
  permisos a usuarios o empresas.
- Rutas no publicadas siguen respondiendo 404 (no se revela qué existe).

## Etapa 1 (implementada): por configuración

| Variable | Default | Efecto |
| --- | --- | --- |
| `AUTH_ENABLED` | `true` | `false` = `/auth/*` responde 503; no se crea el cliente HTTP ni se abren conexiones hacia auth |
| `AUTH_URL` | — | Obligatoria solo si `AUTH_ENABLED=true` (validada al arrancar) |

Aplicar un cambio: editar el `.env` de la central y reiniciar **solo** la central.

```powershell
docker compose restart apigateway
```

Medido en local: la central vuelve en ~3 s y auth no se interrumpe. Durante
esos segundos la central no responde (una sola réplica). Cada servicio nuevo
publicado sigue el mismo patrón: `<SERVICIO>_ENABLED` + `<SERVICIO>_URL`.

Límite de esta etapa: requiere reiniciar la central y editar archivos del
servidor. La etapa 2 lo resuelve.

## Etapa 2 (implementada): estado en base de datos, sin reiniciar

### Regla de estado efectivo

```text
habilitado = <SERVICIO>_ENABLED (config)  Y  estado en base (si existe)
```

- La configuración es el **interruptor maestro**: con `false`, nada lo habilita
  desde la base ni desde el panel.
- Sin fila en la base, vale la configuración.

### Datos (schema `gateway`, propiedad de la central)

`gateway.service_states`: `service` (único), `is_enabled`, `reason`, más los
campos comunes (`id`, `created_at/by`, `updated_at/by`, `is_active`,
`deleted_at/by`). `is_enabled` no es `is_active`: deshabilitar un servicio no es
una baja lógica de la fila.

`gateway.change_history`: historial de negocio de solo anexado (acción,
`resource_type`, `resource_id`, actor en `created_by`, antes/después, trace_id),
en la misma transacción que el cambio. Acciones: `service_state.enable` / `service_state.disable`.

Actores: `created_by`/`updated_by`/`deleted_by` guardan el id del usuario de
auth validado por `/auth/me`, **sin clave foránea** (la central no accede a
tablas de auth). Ids con `uuid4`.

Tablas propias con Alembic limitado al schema `gateway`; versión en
`gateway.alembic_version`, separada de la de auth (`public.alembic_version`) y de `audit`.

Código: `app/core/services.py` (registro `SERVICES`, regla efectiva y relectura),
`app/api/routes/services_router.py` (API), `app/models/entities.py` (tablas).

### Lectura y propagación

- TTL (*time to live*): cada réplica guarda el estado en memoria y una tarea en
  segundo plano lo relee cada `GATEWAY_STATE_TTL_SECONDS` (**5, decisión del
  usuario**); las solicitudes nunca esperan a la base. La réplica que recibe el
  PATCH lo aplica de inmediato. Medido: otra réplica lo vio en 4,2 s. Un cambio aplica en ≤ TTL en todas
  las réplicas, sin reinicio. No hace falta Redis.
- Si la base falla al releer: se conserva el último estado conocido y se
  registra un aviso. Al arrancar sin base: vale la configuración.
- Las solicitudes en curso terminan; solo las nuevas reciben 503.

### Auth es especial

Si auth se deshabilita, nadie puede iniciar sesión, **incluido el panel**, y la
central no podría validar al administrador para volver a habilitarlo.
**Decisión del usuario:** auth solo se deshabilita por configuración
(`AUTH_ENABLED`). En el registro tiene `panel_managed=False` y el PATCH responde
409. Volver a habilitarlo = `AUTH_ENABLED=true` + reiniciar solo la central.

## Lista negra de IPs (implementada)

Persistente, gestionada por un administrador y con historial: vive en la base
de la central (`gateway.ip_blocks`), no en memoria ni en la configuración.

- Campos: `network` (IP o rango CIDR, normalizado: `203.0.113.7` → `203.0.113.7/32`),
  `reason`, `expires_at` (null = sin vencimiento) y los campos comunes.
- Desbloquear = baja lógica (`is_active=false`, `deleted_at/by`), con historial
  (`ip_block.create` / `ip_block.delete`). Un bloqueo vencido deja de aplicarse
  al instante sin cambiar la fila (sigue apareciendo en el listado).
- `IpBlockMiddleware` lo comprueba **antes** de enrutar, contra la copia en
  memoria (misma relectura cada 5 s, `app/core/refresh.py`): aplica a todos los
  servicios y a la administración. Respuesta **403** `{"detail": "Acceso denegado."}`,
  sin revelar el motivo. Excepción: `/health` y `/ready`.
- Queda en los logs de la central (el middleware va dentro de `AuditMiddleware`)
  y el navegador puede leer el 403 (va dentro de CORS).
- La IP evaluada es la real (`TRUSTED_PROXIES`). En Docker Desktop todas las
  conexiones del host llegan con la misma IP: no probar bloqueos ahí.

Protecciones para no quedarse fuera:

- La API rechaza (409) un rango que contenga la IP de quien lo crea.
- `IP_BLOCKS_ENABLED=false` en el `.env` + reiniciar la central desactiva toda
  la lista negra (recuperación si se bloquea a quien no debía).

Validaciones: IP/rango inválido → 422; `expires_at` sin zona horaria o pasada → 422;
campos no permitidos en el body → 422; mismo rango ya bloqueado y vigente → 409.

Los límites por IP (rate limit) irán en el mismo punto, con su propio
almacenamiento de contadores (pendiente).

## API de administración de la central

Bajo `/gateway/admin/...`, para la aplicación web (React):

| Ruta | Uso |
| --- | --- |
| `GET /gateway/admin/logs`, `GET /gateway/admin/logs/{id}` | **Implementado.** Logs de la central (`service=apigateway`), con `platform_audit.queries`. Filtros: `trace_id`, `user_id`, `outcome`, `path_prefix`, `limit`, `offset` |
| `GET /gateway/admin/services` | **Implementado.** Por servicio: `enabled` (efectivo), `enabled_by_config`, `panel_managed`, `db_enabled`, `reason`, `updated_at/by` |
| `PATCH /gateway/admin/services/{service}` | **Implementado.** Body `{"is_enabled": bool, "reason": str?}` (otros campos: 422). 404 servicio desconocido, 409 si solo se cambia por configuración |
| `GET /gateway/admin/history` | **Implementado.** Historial de la central; filtros `resource_type`, `resource_id`, `limit`, `offset` |
| `GET /gateway/admin/ip-blocks` | **Implementado.** Bloqueos activos (incluye vencidos); `include_inactive=true` agrega los desbloqueados. `limit`, `offset` |
| `POST /gateway/admin/ip-blocks` | **Implementado.** Body `{"network": "203.0.113.0/24", "reason": str?, "expires_at": datetime?}` → 201 |
| `DELETE /gateway/admin/ip-blocks/{id}` | **Implementado.** Desbloquear (baja lógica) → 204; 404 si no existe o ya estaba desbloqueado |

Validación del administrador (**decisión del usuario, implementada** en
`app/api/dependencies.py`): la central llama a `GET /auth/me` con el Bearer
recibido y exige `is_platform_admin=true`. Solo Bearer (no API keys). Respuestas:
401 sin token o token inválido, 403 si no es administrador, 502/504 si auth
falla, 503 con `AUTH_ENABLED=false`. El actor validado se registra con `set_actor`.
Respeta revocaciones (auth consulta sesión y usuario en su base), no comparte
claves y reutiliza un contrato existente. Coste: una llamada a auth por
solicitud administrativa. Sin auth disponible, la administración no funciona.
Los usuarios, empresas y logs de auth se siguen consultando en auth
(`/auth/admin/...`): la central no los duplica.

## Orden propuesto

1. ~~`AUTH_ENABLED` por configuración.~~ Hecho.
2. ~~Validación de administrador vía `/auth/me` + `GET /gateway/admin/logs`.~~ Hecho.
3. ~~Schema `gateway` con Alembic + `service_states` + historial + caché con TTL.~~ Hecho.
4. ~~`ip_blocks` + middleware de bloqueo.~~ Hecho.
5. Aplicación web de administración.

## Aplicación web de administración (React)

Una sola aplicación que habla **solo con la central**; nunca directo con los servicios:

| Pantalla | Rutas (a través de la central) |
| --- | --- |
| Login / sesión | `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me` |
| Usuarios, empresas (admin de plataforma) | `/auth/admin/users`, `/auth/admin/companies`, ... |
| Áreas, puestos, roles, miembros (empresa activa, `X-Company-Id`) | `/auth/areas`, `/auth/positions`, `/auth/roles`, `/auth/members` |
| Catálogos | `/auth/catalog/countries`, `/auth/catalog/document-types` |
| Logs de auth / de la central | `/auth/admin/logs` / `/gateway/admin/logs` (se relacionan por `trace_id`) |
| Servicios y lista negra | `/gateway/admin/services`, `/gateway/admin/ip-blocks` (etapas 3-4) |

- El origen de la app (p. ej. `http://localhost:5173` con Vite) va en
  `CORS_ORIGINS` de la **central**; el navegador no habla con auth.
- La app solo muestra u oculta opciones: la autorización real la aplica cada
  servicio (y la central en `/gateway/admin`).
- Cada servicio nuevo publica sus rutas en la central y la app las consume igual.

## Decisiones pendientes

- Código y cuerpo de respuesta para IP bloqueada (propuesta 403 genérico).
