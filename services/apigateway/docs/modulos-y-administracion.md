# Módulos, lista negra y administración de la central

Objetivo: desactivar un servicio (módulo) de forma rápida y controlada, sin
detener los demás ni el propio servicio, y preparar la administración que luego
usará una aplicación web.

Estado: la **etapa 1 está implementada**. El resto es un **diseño propuesto**,
pendiente de confirmar antes de implementarlo (ver "Decisiones pendientes").

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

## Etapa 2 (diseño): estado en base de datos, sin reiniciar

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

`gateway.change_history`: historial de negocio de solo anexado (acción, actor,
recurso, antes/después, trace_id), en la misma transacción que el cambio.

Implica que la central pase a tener tablas propias: Alembic limitado al schema
`gateway` y `COPY` de migraciones en su Dockerfile.

### Lectura y propagación

- Cada réplica de la central guarda el estado en memoria y lo relee cada
  `GATEWAY_STATE_TTL_SECONDS` (propuesta: 5). Un cambio aplica en ≤ TTL en todas
  las réplicas, sin reinicio. No hace falta Redis.
- Si la base falla al releer: se conserva el último estado conocido y se
  registra un aviso. Al arrancar sin base: vale la configuración.
- Las solicitudes en curso terminan; solo las nuevas reciben 503.

### Auth es especial

Si auth se deshabilita, nadie puede iniciar sesión, **incluido el panel**, y la
central no podría validar al administrador para volver a habilitarlo.
Propuesta: auth solo se deshabilita por configuración (`AUTH_ENABLED`); el
panel no ofrece esa acción.

## Lista negra de IPs (diseño): sí, en base de datos

Es persistente, la gestiona un administrador y necesita historial: va en la
base de la central, no en memoria ni en la configuración.

- `gateway.ip_blocks`: `network` (IP o rango CIDR), `reason`, `expires_at`
  (null = sin vencimiento), campos comunes. Desbloquear = baja lógica, con historial.
- Se comprueba en un middleware de la central **antes** de enrutar: aplica a
  todos los servicios. Respuesta **403** genérica. Mismo esquema de caché con TTL.
- La IP evaluada es la real (`TRUSTED_PROXIES`). En Docker Desktop todas las
  conexiones del host llegan con la misma IP: no probar bloqueos ahí.
- Los límites por IP (rate limit) irán en el mismo punto, con su propio
  almacenamiento de contadores.

## API de administración de la central (diseño)

Bajo `/gateway/admin/...`, para la futura aplicación web:

| Ruta | Uso |
| --- | --- |
| `GET /gateway/admin/services` / `PATCH /gateway/admin/services/{service}` | Ver y cambiar el estado (etapa 2) |
| `GET/POST /gateway/admin/ip-blocks`, `DELETE /gateway/admin/ip-blocks/{id}` | Lista negra (DELETE = baja lógica) |
| `GET /gateway/admin/logs`, `GET /gateway/admin/logs/{id}` | Logs de la central (`service=apigateway`), con `platform_audit.queries` |

Validación del administrador (propuesta): la central llama a
`GET /auth/me` con el Bearer recibido y exige `is_platform_admin=true`.
Respeta revocaciones (auth consulta sesión y usuario en su base), no comparte
claves y reutiliza un contrato existente. Coste: una llamada a auth por
solicitud administrativa. Sin auth disponible, la administración responde 503.
Los usuarios, empresas y logs de auth se siguen consultando en auth
(`/auth/admin/...`): la central no los duplica.

## Orden propuesto

1. ~~`AUTH_ENABLED` por configuración.~~ Hecho.
2. Validación de administrador vía `/auth/me` + `GET /gateway/admin/logs`.
3. Schema `gateway` con Alembic + `service_states` + historial + caché con TTL.
4. `ip_blocks` + middleware de bloqueo.
5. Aplicación web de administración.

## Decisiones pendientes

- Validar al administrador con `/auth/me` (propuesta) o verificando el JWT en la central.
- TTL de la caché de estado (propuesta 5 s).
- Que auth no se pueda deshabilitar desde el panel (propuesta).
- Código y cuerpo de respuesta para IP bloqueada (propuesta 403 genérico).
