# Contrato de la API de notificaciones (v1, paso 1)

Estado (2026-10-01): **implementado** (pasos 1 y 2, worker y retención). El
contrato exacto es el OpenAPI que genera FastAPI (`/notificaciones/docs`);
este documento registra las decisiones y reglas detrás de cada ruta.

## Convenciones

- Prefijo `/notificaciones` (la central enruta por prefijo). Recursos en
  inglés y kebab-case, como libro-mayor.
- Autenticación: `Authorization: Bearer <token de auth>` y `X-Company-Id`.
  Se validan con `GET /auth/me/permissions`; de ahí salen `user_id`, email y
  permisos. Nunca se aceptan empresa ni actor desde el body.
- Fuera del alcance del usuario (`own`) o de otra empresa: **404**, no 403,
  para no revelar que el recurso existe.
- Errores con el formato de la plataforma (acuerdo 2026-10-01, reemplaza al
  anterior `{"error": {...}}`): `{"detail": "mensaje"}`, sin datos internos.
  Solo cuando el consumidor necesita distinguir el caso se agrega `"code"`
  (p. ej. `idempotency_conflict`, `message_too_large`, `no_smtp_account`) y,
  si aplica, datos extra del caso. Los 401/403/422 de FastAPI ya usan `detail`.
- Listados paginados con `limit` (default 50, máx. 200) y `offset`;
  respuesta `{"items": [...], "total": n}`.
- Fechas ISO 8601 en UTC.

## Permisos por ruta

| Ruta | Permiso mínimo |
| --- | --- |
| `POST /dispatches` | `notifications.send` |
| `GET /dispatches`, `GET /dispatches/{id}` | `notifications.view` |
| `GET /dispatches/{id}/messages`, `GET /messages/{id}` | `notifications.view` |
| `GET /messages/{id}/attachments/{attachment_id}` | `notifications.view` |
| `POST /messages/{id}/retry`, `POST /messages/{id}/cancel` | `notifications.retry` |
| `POST /dispatches/{id}/retry` | `notifications.retry` |
| `GET /messages/{id}/attempts` | `notifications.admin` |
| `/smtp-accounts/...` | `notifications.admin` |

Cada nivel incluye al anterior. Con alcance `own` solo se ven y operan
envíos con `created_by` = el usuario.

## Crear un envío

`POST /notificaciones/dispatches`

Headers: `Authorization`, `X-Company-Id`, `Idempotency-Key` (obligatorio,
1–100 caracteres).

Propuesta: **multipart/form-data**, no JSON con base64. Los adjuntos viajan
como archivos (sin el 33 % extra de base64) y el resto como una parte JSON:

- Parte `payload` (JSON):

```json
{
  "consumer": "payment_provider",
  "consumer_reference": "lote-2026-10-01-001",
  "messages": [
    {
      "consumer_reference": "PROV-00123",
      "to": ["pagos@proveedor.com"],
      "cc": ["tesoreria@miempresa.com"],
      "bcc": [],
      "reply_to": "tesoreria@miempresa.com",
      "subject": "Constancia de pago - Octubre",
      "body_html": "<p>Estimado proveedor...</p>",
      "body_text": null,
      "attachments": ["f1", "f2"]
    }
  ]
}
```

- Partes de archivo con nombre `f1`, `f2`, … Cada mensaje las referencia por
  nombre. Un mismo archivo puede referenciarse desde varios mensajes; se
  guarda una copia por mensaje.

Validaciones (todas antes de guardar; si una falla no se guarda nada):
- Entre 1 y 500 mensajes por envío.
- Por mensaje: al menos un `to`, máximo 50 destinatarios entre to, cc y bcc,
  sin duplicados, emails válidos, `subject` no vacío, `body_html` o
  `body_text`.
- Adjuntos: tipo permitido validado por contenido, nombre saneado, toda
  referencia existe y todo archivo enviado se usa. Acuerdo 6a (2026-10-01):
  pdf, png, jpg/jpeg, gif, xlsx, xls, docx, doc, zip, csv y txt, reconocidos
  por firma propia (`app/services/attachment_types.py`); la extensión debe
  coincidir con el contenido (422 `attachment_type_not_allowed`); csv/txt deben
  ser texto; se guarda el tipo detectado, no el declarado. Archivo vacío: 422.
- Destinatarios normalizados (dominio en minúsculas); los duplicados entre to,
  cc y bcc se quitan sin distinguir mayúsculas, conservando la primera
  aparición. Solo direcciones simples, sin nombre visible. bcc nunca va en los
  headers del correo.
- `request_hash`: SHA-256 del payload canónico con cada archivo identificado por
  nombre y SHA-256, no por el nombre de la parte multipart.
- Tamaño MIME final de cada mensaje ≤ 25 MB.
- Debe existir al menos una cuenta SMTP activa en la empresa (si no, 422:
  el envío no podría salir).

Implementación 6b (2026-10-01, `app/services/dispatch_service.py`):
- Auth y permisos se validan antes de leer el cuerpo multipart.
- `payload` con `extra="forbid"`: un campo desconocido (p. ej. `company_id`)
  da 422 `validation_error` con la lista `errors` (ubicación y mensaje).
- Cada `Message-ID` es `<uuid7@dominio>` con el dominio del remitente de la
  primera cuenta SMTP activa de la empresa (acuerdo A).
- Se guarda una copia de cada adjunto por mensaje que lo usa.
- La respuesta identifica al solicitante con `requested_by_user_id` (el id de
  usuario de auth), no con el actor interno.
- Queda en `change_history` como `dispatch.create` con consumidor, referencia
  y cantidades (sin destinatarios ni contenido).

Respuestas:

| Código | Caso |
| --- | --- |
| 202 | Envío creado. Body: el envío (como en `GET /dispatches/{id}`) |
| 200 | Misma `Idempotency-Key` y mismo contenido: devuelve el envío existente, sin crear nada |
| 409 | `idempotency_conflict`: misma clave con contenido distinto |
| 413 | La solicitud supera el límite del borde (100 MB) |
| 422 | `validation_error`, `message_too_large` (con `message_index`, `size_bytes`, `limit_bytes`), `no_smtp_account` |

## Consultar envíos

`GET /notificaciones/dispatches?status=&consumer=&consumer_reference=&created_from=&created_to=&requested_by_user_id=&requester_email=`

`GET /notificaciones/dispatches/{id}`:

```json
{
  "id": "…",
  "kind": "standard",
  "consumer": "payment_provider",
  "consumer_reference": "lote-2026-10-01-001",
  "status": "in_progress",
  "counts": {"total": 11, "pending": 0, "sending": 1, "retrying": 2,
             "sent": 7, "failed": 1, "uncertain": 0, "cancelled": 0},
  "created_at": "…",
  "requested_by_user_id": "…",
  "requested_by_email": "persona@empresa.com"
}
```

`status` se calcula: `pending` (ninguno empezó), `in_progress` (alguno en
`pending`/`sending`/`retrying`), `completed` (todos `sent`),
`completed_with_errors` (ninguno en curso y alguno `failed`, `uncertain` o
`cancelled`).

`GET /notificaciones/dispatches/{id}/messages?status=`: lista resumida
(destinatarios, asunto, estado, `consumer_reference`, `sent_at`).

Implementación 6c (2026-10-01, `app/services/dispatch_queries.py`):
- Listado del más nuevo al más antiguo; filtros `status` (calculado, traducido
  a `EXISTS` sobre los mensajes), `consumer`, `consumer_reference`, `kind`,
  `created_from` y `created_to` (exclusivo). Un envío sin mensajes cuenta
  como `pending`.
- Solicitante (2026-10-01, pedido del front para filtrar por usuario):
  `requested_by_email` en la respuesta (el correo que dio auth al crear el
  envío; `null` si lo creó un proceso). Filtros `requested_by_user_id` (id de
  auth) y `requester_email` (parte del correo, sin distinguir mayúsculas; `%`
  y `_` son literales). Con alcance `own` se combinan con "solo propios".
- Alcance `own`: solo envíos con `created_by` = el usuario; los avisos
  (`failure_notice`, creados por un proceso) solo se ven con `company`.
- Otro usuario (own) u otra empresa: 404.
- Descarga: siempre `Content-Disposition: attachment` con `filename*`
  (UTF-8), `X-Content-Type-Options: nosniff` y `Cache-Control: no-store`.

## Consultar un mensaje

`GET /notificaciones/messages/{id}`: destinatarios, asunto, cuerpo, adjuntos
(metadatos y si su contenido sigue disponible), estado, fechas y
`attempts_in_cycle`. Con `notifications.admin` se agrega el detalle técnico
(`message_id_header`, `size_bytes`).

`GET /notificaciones/messages/{id}/attachments/{attachment_id}`: descarga.
**410** si el contenido ya se purgó.

`GET /notificaciones/messages/{id}/attempts`: intentos con cuenta usada,
resultado, código y respuesta SMTP (solo `admin`).

## Reprocesar y cancelar

- `POST /messages/{id}/retry`: solo desde `failed` o `uncertain` → `pending`,
  reinicia `attempts_in_cycle`. 409 desde otro estado.
- `POST /messages/{id}/cancel`: desde `pending`, `retrying`, `failed` o
  `uncertain` → `cancelled` (`manual`) y purga adjuntos. 409 si está
  `sending`, `sent` o `cancelled`.
- `POST /dispatches/{id}/retry`: reprocesa todos sus mensajes `failed` y
  `uncertain`. Responde cuántos se reencolaron.
- Propuesta: body opcional `{"reason": "..."}` que se guarda en
  `change_history`.

Para `uncertain`, el front debe advertir que el destinatario quizá ya lo
recibió.

Implementación (2026-10-01, `app/services/message_actions.py`):
- Permiso `notifications.retry` (own o company). Fuera del alcance: 404.
- Estado no válido: 409 `invalid_status`.
- Reprocesar deja `attempts_in_cycle = 0` (3 reintentos automáticos de nuevo),
  `next_attempt_at = ahora` y `notice_dispatch_id = NULL` (el plazo de aviso y
  cancelación vuelve a empezar si falla otra vez).
- Cancelar purga los adjuntos y no se puede deshacer.
- El mensaje se relee con `FOR UPDATE`: si el worker lo está tomando, se espera
  y se ve en `sending` (409), nunca se cancela a mitad de un envío.
- Respuesta de `/messages/{id}/retry` y `/cancel`: el resumen del mensaje.
  `/dispatches/{id}/retry`: `{"requeued": n}`.
- Cada mensaje afectado queda en `change_history` (`message.retry` /
  `message.cancel`) con el estado anterior y nuevo y el `reason`.

## Cuentas SMTP

| Ruta | Uso |
| --- | --- |
| `GET /smtp-accounts` | Lista en orden efectivo (`priority`, `created_at`); `?include_inactive=true` |
| `POST /smtp-accounts` | Alta |
| `GET /smtp-accounts/{id}` | Detalle |
| `PATCH /smtp-accounts/{id}` | Edición parcial, incluida la contraseña |
| `DELETE /smtp-accounts/{id}` | Baja lógica |
| `POST /smtp-accounts/{id}/restore` | Restaurar |
| `POST /smtp-accounts/{id}/test` | Conecta y autentica sin enviar; responde `ok` o la categoría de error |

Body de alta:

```json
{
  "name": "Office 365 principal",
  "host": "smtp.office365.com",
  "port": 587,
  "security": "starttls",
  "username": "notificaciones@miempresa.com",
  "password": "…",
  "from_email": "notificaciones@miempresa.com",
  "from_name": "Tesorería",
  "priority": 1,
  "timeout_seconds": 30
}
```

Las respuestas nunca incluyen `password`; muestran `has_password`.

Reglas (acuerdo 2026-10-01, implementado en 4c-1 salvo `test`):
- `username` y `password` van juntos: los dos o ninguno (relay sin
  autenticación). 422 si no.
- `PATCH`: si `password` no se envía, no cambia; un texto la reemplaza;
  `null` la borra. `username`, `password` y `from_name` admiten `null`; el
  resto no (422).
- La contraseña no se recorta; el resto de textos sí. Nombre, usuario y
  nombre visible no admiten saltos de línea ni caracteres de control.
- `from_email` no tiene que ser igual a `username`; algunos proveedores solo
  envían como el usuario autenticado o con permiso "enviar como".
- Nombre único entre cuentas activas de la empresa (409). Restaurar responde
  409 si otra activa usa el nombre. Se permite dar de baja la última activa.
- Cada alta, edición, baja y restauración queda en `change_history`, sin la
  contraseña (`has_password` y, si cambió, `password_changed`).

Conexión y prueba (acuerdo 2026-10-01, 4c-2; `app/services/smtp_transport.py`):
- Puerto dentro de `SMTP_ALLOWED_PORTS` (default 25, 465, 587, 2525): se
  valida al guardar (422) y al conectar.
- SSRF: todas las direcciones del host deben ser públicas o estar en
  `SMTP_ALLOWED_PRIVATE_NETWORKS`; se conecta a la IP comprobada. Loopback,
  privadas, link-local y multicast se rechazan.
- TLS obligatorio y certificado verificado contra las CA del sistema más
  `SMTP_CA_BUNDLE` (opción A), salvo hosts en `SMTP_TLS_UNVERIFIED_HOSTS`
  (opción B, último recurso). Con un relay interno conviene registrar el
  host por el nombre del certificado, no por la IP.
- `POST /smtp-accounts/{id}/test`: 200 `{"ok": true}` o
  `{"ok": false, "error_kind": "blocked_address" | "connection" | "timeout" |
  "tls" | "auth" | "credentials_unreadable" | "unknown"}`. No envía correo ni
  escribe historial; queda como paso en los logs.

## Salud

`GET /notificaciones/health` (proceso vivo) y `GET /notificaciones/ready`
(base de datos accesible). Propuesta: `ready` del worker como comprobación
de su contenedor, no como ruta HTTP.

## Acuerdos del usuario (2026-10-01)

1. Creación en multipart: parte `payload` (JSON) y archivos referenciados por
   nombre.
2. Máximo 500 mensajes por envío.
3. 202 al crear; 200 al devolver el envío existente por idempotencia.
4. Sin cuenta SMTP activa en la empresa, la creación responde
   422 `no_smtp_account`.
5. Se incluye `POST /dispatches/{id}/retry` y `reason` opcional en reproceso y
   cancelación, guardado en `change_history`.
6. En la central se publican todas las rutas salvo `health` y `ready`.

## Plantillas (paso 2a, 2026-10-01)

`/templates` con `notifications.admin` (company): `GET` (listado por código,
`include_inactive`), `POST`, `GET/PATCH/DELETE /{id}`, `POST /{id}/restore` y
`POST /{id}/preview` (`{"parameters": {...}}` → asunto y cuerpos armados, sin
guardar ni enviar).

- Campos: `code` (`^[a-z0-9][a-z0-9_.-]{0,99}$`, único entre activas de la
  empresa, 409), `name`, `description`, `subject_template`,
  `body_html_template` y/o `body_text_template`, destinatarios fijos `to`,
  `cc`, `bcc` (normalizados y sin duplicados, máx. 50) y `reply_to`.
- Jinja2 en `SandboxedEnvironment`: la sintaxis se valida al guardar (422
  `template_error`); operaciones bloqueadas por el sandbox → 422
  `template_error`.
- HTML con autoescape de los valores; asunto y texto sin escapar. El asunto
  armado debe quedar en una línea, no vacío y ≤ 998 caracteres.
- Parámetros faltantes (ajuste del acuerdo 3, por compatibilidad con las
  plantillas de proyecto-05): imprimirlo o recorrerlo → 422
  `template_parameter_missing`; en una condición, `or` o `| default(...)`
  cuenta como falso, para admitir campos opcionales como
  `{{ pago.suggested_filename or pago.archivo }}`.
- Editar o dar de baja una plantilla no cambia lo ya enviado. Cada cambio en
  `change_history` con la plantilla completa (no tiene secretos).

### Envíos con plantilla (paso 2b, 2026-10-01)

En `POST /dispatches`, cada mensaje lleva contenido armado (`subject` +
`body_html`/`body_text`) **o** una plantilla (`template_code` + `parameters`),
nunca ambos (422 `validation_error`). `template_code` también puede ir a nivel
de envío como valor por defecto; en ese caso ningún mensaje lleva contenido
armado, pero cualquiera puede indicar otro `template_code`.

```json
{"consumer": "payment_provider", "consumer_reference": "lote-1",
 "template_code": "payment_provider_summary",
 "messages": [{"consumer_reference": "P1", "to": ["pagos@prov.com"],
               "parameters": {"proveedor": "ACME SAC", "pagos": [...]}, "attachments": ["f1"]}]}
```

- Plantilla inexistente o dada de baja: 422 `template_not_found`.
- Parámetro faltante o error al armar: 422 con `code` y `message_index`.
- Destinatarios: los del consumidor primero, luego los fijos de la plantilla;
  sin duplicados (gana la primera aparición) y máximo 50. `to` puede ir vacío si
  la plantilla trae `to` fijos. `reply_to`: el del mensaje o el de la plantilla.
- Se guarda el resultado armado y `template_id`; los `parameters` no se guardan.
- `request_hash` incluye `template_code` y `parameters` (orden de claves
  indiferente).

## Carga inicial (seed, 2026-10-01)

`POST /notificaciones/admin/seed`: solo existe con `SEED_ENABLED=true` y solo
la ejecuta el administrador de plataforma, con su sesión y `X-Company-Id`
(como libro-mayor; sin token de bootstrap). Datos por código de empresa en
`app/seeds/data.py`; HTML en `app/seeds/templates/`.

- Hoy: la plantilla `payment_provider_summary` para `RASH` (la de proyecto-05,
  con `asunto` y `mensaje` opcionales).
- Idempotente: activa existente → `existing` sin modificarla; solo dada de baja
  → `kept_deactivated` sin reactivarla; inexistente → `created`.
- No siembra cuentas SMTP (contraseñas) ni datos de negocio.
