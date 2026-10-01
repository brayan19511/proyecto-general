# Modelo de datos de notificaciones

Estado (2026-10-01): **propuesta** para el paso 1 del alcance (envío con
cuerpo armado). Nada implementado ni acordado todavía; cada tabla se revisa
con el usuario antes de escribir código. Las plantillas (paso 2) no están
aquí.

## Convenciones

Mismas que libro-mayor (`services/libro-mayor/docs/modelo-datos.md`):

- Schema propio `notificaciones`, declarado una vez en `Base.metadata`;
  Alembic limitado a ese schema. Los logs técnicos van al schema `audit` de
  `packages/platform-audit`.
- `company_id` y los ids de usuario de auth son referencias (UUID sin FK);
  nunca se leen tablas de auth.
- Todas las tablas: `id`, `created_at`, `created_by`, `updated_at`,
  `updated_by`, `is_active`, `deleted_at`, `deleted_by` (`AuditMixin`), con
  `*_by` como FK a `actors`.
- `company_id` en todas las tablas de negocio, primero en índices.
- Nombres y valores de estado en inglés; fechas UTC.
- Estados con CHECK de valores fijos.

Tamaños y plazos que no son columnas van en la configuración del servicio:
límite de 25 MB por mensaje, 3 reintentos automáticos, esperas entre
reintentos, aviso a los 2 días, cancelación a los 3, duración del bloqueo del
worker y claves de cifrado.

## actors

Igual que libro-mayor: `kind` (`user` | `system` | `service`), `subject_ref`,
`label` sin datos personales. Único (`kind`, `subject_ref`).

- Usuario: se registra la primera vez que opera, con el id validado por auth.
- Sistema: `notificaciones.worker` (envía, reintenta, marca inciertos) y
  `notificaciones.retention` (avisos y cancelación por plazo), creados por
  migración.

## change_history

Igual que libro-mayor: historial de negocio genérico, solo anexado, en la
misma transacción que el cambio. Acciones previstas:

- `smtp_account.create`, `.update`, `.delete`, `.restore`
- `message.retry`, `message.cancel` (manual o por plazo)

Las transiciones que hace el worker al enviar no van aquí: quedan en
`message_attempts`, que ya es su historial.

## smtp_accounts

Cuentas SMTP por empresa (acuerdo 2).

| Columna | Tipo | Nota |
| --- | --- | --- |
| `company_id` | UUID | |
| `name` | String(100) | Único activo (`company_id`, `name`) |
| `host` | String(255) | |
| `port` | Integer | CHECK 1–65535 |
| `security` | String(10) | `starttls` \| `ssl` (CHECK). Sin opción en claro |
| `username` | String(255) nullable | Relays sin autenticación |
| `password_encrypted` | Text nullable | Cifrada; nunca se devuelve |
| `from_email` | String(320) | Remitente |
| `from_name` | String(100) nullable | Nombre visible |
| `priority` | Integer | Menor = primero |
| `timeout_seconds` | Integer | Default 30 |

- Orden de uso: `priority`, luego `created_at`. Propuesta: **sin** unicidad
  de prioridad, porque intercambiar dos prioridades chocaría con un índice
  único no diferido. El listado muestra el orden efectivo.
- Índice (`company_id`, `is_active`, `priority`).
- Historial: `before`/`after` sin la contraseña; si cambia se anota
  `password_changed: true`.
- Cifrado: `cryptography` (Fernet). Propuesta: `MultiFernet` con varias claves
  en el entorno para poder rotarlas sin perder las contraseñas guardadas.

## dispatches

El envío: el trabajo que agrupa N mensajes.

| Columna | Tipo | Nota |
| --- | --- | --- |
| `company_id` | UUID | |
| `kind` | String(20) | `standard` \| `failure_notice` (CHECK) |
| `idempotency_key` | String(100) | Del header `Idempotency-Key` |
| `request_hash` | String(64) | SHA-256 del contenido recibido |
| `consumer` | String(50) nullable | Informativo, p. ej. `payment_provider` |
| `consumer_reference` | String(100) nullable | P. ej. id del lote del consumidor |
| `requester_email` | String(320) nullable | De `/auth/me` al crear (acuerdo 11) |
| `notice_for_dispatch_id` | FK nullable | Solo en `failure_notice` |
| `trace_id` | String | Enlace con `audit.logs` |

- Quien lo solicitó es `created_by`, que es el actor usuario.
- Único (`company_id`, `created_by`, `idempotency_key`), sobre todas las
  filas. Misma clave con igual `request_hash` devuelve el envío existente;
  con distinto hash, 409. Ser por solicitante evita que la clave de un
  usuario revele el envío de otro.
- Propuesta: el estado y el progreso **no se guardan**; se calculan
  agregando los estados de sus mensajes. Así varios workers no se pelean por
  actualizar la misma fila.
- Índices (`company_id`, `created_at`) y (`company_id`, `created_by`,
  `created_at`) para el alcance `own`.
- El aviso previo es un envío más, de tipo `failure_notice`, creado por
  `notificaciones.retention`. Reutiliza todo el flujo, y un aviso fallido
  nunca genera otro aviso.

## messages

Un correo dentro de un envío.

| Columna | Tipo | Nota |
| --- | --- | --- |
| `company_id` | UUID | Repetido para filtrar sin join |
| `dispatch_id` | FK | |
| `sequence` | Integer | Único (`dispatch_id`, `sequence`) |
| `consumer_reference` | String(100) nullable | P. ej. código del proveedor |
| `to_addresses`, `cc_addresses`, `bcc_addresses` | JSON | Listas |
| `reply_to` | String(320) nullable | |
| `subject` | String(998) | Límite de línea de RFC 5322 |
| `body_html`, `body_text` | Text nullable | CHECK: al menos uno |
| `message_id_header` | String(255) | `Message-ID` generado al crear, igual en cada intento |
| `size_bytes` | Integer | Tamaño MIME final, validado contra 25 MB |
| `status` | String(20) | Ver estados |
| `attempts_in_cycle` | Integer | Se reinicia en el reproceso manual |
| `next_attempt_at` | DateTime nullable | Cuándo puede tomarlo el worker |
| `locked_until` | DateTime nullable | Bloqueo del worker |
| `locked_by` | String(100) nullable | Id del proceso worker |
| `last_attempt_at` | DateTime nullable | Desde aquí corren los 2 y 3 días |
| `sent_at` | DateTime nullable | |
| `notice_dispatch_id` | FK nullable | Aviso que ya lo incluyó |
| `cancelled_at` | DateTime nullable | |
| `cancel_reason` | String(20) nullable | `manual` \| `expired` |

Estados (`status`):

| Estado | Significado | Sale hacia |
| --- | --- | --- |
| `pending` | Espera su primer intento | `sending` |
| `sending` | Tomado por un worker | `sent`, `retrying`, `failed`, `uncertain` |
| `retrying` | Falló transitoriamente; espera `next_attempt_at` | `sending` |
| `sent` | El servidor lo aceptó | Final |
| `failed` | Error permanente o agotó los 3 reintentos | `pending` (reproceso), `cancelled` |
| `uncertain` | No se sabe si salió | `pending` (reproceso), `cancelled` |
| `cancelled` | Manual o por plazo | Final |

- El worker toma mensajes `pending`/`retrying` con `next_attempt_at <= now`
  usando `FOR UPDATE SKIP LOCKED`, los pasa a `sending` y fija
  `locked_until`.
- Corrección a la propuesta del alcance: si vence el bloqueo de un mensaje
  en `sending`, **no vuelve a la cola**, pasa a `uncertain`. El worker pudo
  morir después de transmitirlo, y reenviarlo podría duplicarlo.
- Índices: (`status`, `next_attempt_at`) para el worker;
  (`status`, `locked_until`) para detectar bloqueos vencidos;
  (`company_id`, `dispatch_id`); (`status`, `last_attempt_at`) para el
  proceso de plazos.
- Destinatarios en JSON (propuesta): simple y portable. Si luego se necesita
  buscar "qué se envió a tal correo", se agrega una tabla de destinatarios.
- `is_active` no se usa para cancelar: cancelar es un estado. Los mensajes
  no se dan de baja.

Acuerdos de la revisión de `messages` (2026-10-01):
- Validación al crear: sintaxis de cada email, sin duplicados entre to, cc y
  bcc, al menos un `to`, máximo 50 destinatarios por mensaje (sumando los
  tres) y 25 MB sobre el mensaje MIME final.
- El cuerpo HTML se muestra en el front dentro de un `<iframe sandbox>` sin
  scripts (requisito para front-central).
- Se permite reprocesar errores permanentes, pero sin editar destinatarios ni
  contenido; para corregir se crea un envío nuevo.
- `consumer_reference` por mensaje se mantiene (p. ej. código del proveedor).

## message_attachments

| Columna | Tipo | Nota |
| --- | --- | --- |
| `company_id` | UUID | |
| `message_id` | FK | |
| `sequence` | Integer | Único (`message_id`, `sequence`) |
| `filename` | String(255) | |
| `content_type` | String(100) | |
| `size_bytes` | Integer | |
| `sha256` | String(64) | |
| `content` | LargeBinary nullable | Carga diferida: no se lee en listados |
| `content_purged_at` | DateTime nullable | |

- Purga (acuerdo 5): `content` pasa a NULL y se fija `content_purged_at`
  cuando el mensaje queda `sent` o `cancelled`. La fila y sus metadatos se
  conservan; no es un borrado de fila.
- `bytea` en PostgreSQL, `VARBINARY(MAX)` en SQL Server.

## message_attempts

Solo anexado: una fila por cada cuenta probada en cada intento.

| Columna | Tipo | Nota |
| --- | --- | --- |
| `company_id` | UUID | |
| `message_id` | FK | |
| `attempt_number` | Integer | Intento del mensaje (acumulado) |
| `smtp_account_id` | FK nullable | NULL si no había cuenta activa |
| `started_at`, `finished_at` | DateTime | |
| `outcome` | String(20) | `sent` \| `transient_error` \| `permanent_error` \| `uncertain` \| `no_account` |
| `smtp_code` | Integer nullable | |
| `error_kind` | String(100) nullable | Categoría o tipo de excepción |
| `smtp_response` | String(500) nullable | Respuesta del servidor, truncada; solo `admin` |

- Se inserta al terminar cada prueba (no se actualiza después). Un listener
  rechaza UPDATE/DELETE, como en `change_history`.
- Failover: si la cuenta 1 falla antes de aceptarse el mensaje y la 2 lo
  envía, quedan dos filas con el mismo `attempt_number`.
- Índice (`message_id`, `attempt_number`).

## Acuerdos del usuario (2026-10-01)

Aceptadas las decisiones de la propuesta: estado del envío calculado (no
guardado); bloqueo vencido en `sending` → `uncertain`; aviso previo como envío
de tipo `failure_notice`; idempotencia por (`company_id`, `created_by`,
`idempotency_key`) con `request_hash`; destinatarios en JSON; prioridad de
cuentas sin unicidad; el reproceso manual reinicia `attempts_in_cycle`.

- Los destinatarios de cada mensaje son la lista final: los que envía el
  consumidor (p. ej. correos del proveedor) más los fijos. En el paso 2 los
  fijos vendrán de la plantilla (equivalente a `mailing_parameters` de
  proyecto-05) y se guardará aquí el resultado ya combinado.

## Pendientes de esta propuesta

- Nombre del schema (`notificaciones`).
- Ninguno en las tablas del paso 1.

Acuerdos de la revisión de `smtp_accounts`, `message_attachments` y
`message_attempts` (2026-10-01):
- Solo `starttls` o `ssl`; no se admite SMTP en claro.
- `POST .../test` comprueba conexión y autenticación sin enviar correo.
- Cifrado con `MultiFernet` y lista de claves en el entorno para rotarlas.
- La contraseña se puede cambiar pero nunca se devuelve (`has_password`).
- Adjuntos: lista positiva de tipos (PDF, imágenes, Excel, Word, ZIP),
  validados por contenido y no solo por extensión; nombre de archivo
  saneado (sin rutas ni caracteres de control).
- Sin máximo de cantidad de adjuntos; solo el límite de 25 MB por mensaje.
- Si un mensaje supera 25 MB, la creación del envío se rechaza (422) indicando
  qué mensaje, su tamaño y el límite. Notificaciones **no divide** mensajes:
  dividir cambia lo que recibe el destinatario y es decisión del consumidor.
- `smtp_response` truncada a 500 caracteres, visible solo para `admin`.
- Clasificación: `4xx` transitorio (reintento), `5xx` permanente, conexión,
  TLS o autenticación → siguiente cuenta, corte tras transmitir → incierto.
