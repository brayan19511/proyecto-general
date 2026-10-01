# Contrato de la API de notificaciones (v1, paso 1)

Estado (2026-10-01): **acordado**, no implementado. El
contrato definitivo será el OpenAPI que genere FastAPI; este documento fija
las decisiones antes de escribir código.

## Convenciones

- Prefijo `/notificaciones` (la central enruta por prefijo). Recursos en
  inglés y kebab-case, como libro-mayor.
- Autenticación: `Authorization: Bearer <token de auth>` y `X-Company-Id`.
  Se validan con `GET /auth/me/permissions`; de ahí salen `user_id`, email y
  permisos. Nunca se aceptan empresa ni actor desde el body.
- Fuera del alcance del usuario (`own`) o de otra empresa: **404**, no 403,
  para no revelar que el recurso existe.
- Errores con forma única: `{"error": {"code": "...", "message": "...",
  "details": {...}}}`, sin datos internos.
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
  referencia existe y todo archivo enviado se usa.
- Tamaño MIME final de cada mensaje ≤ 25 MB.
- Debe existir al menos una cuenta SMTP activa en la empresa (si no, 422:
  el envío no podría salir).

Respuestas:

| Código | Caso |
| --- | --- |
| 202 | Envío creado. Body: el envío (como en `GET /dispatches/{id}`) |
| 200 | Misma `Idempotency-Key` y mismo contenido: devuelve el envío existente, sin crear nada |
| 409 | `idempotency_conflict`: misma clave con contenido distinto |
| 413 | La solicitud supera el límite del borde (100 MB) |
| 422 | `validation_error`, `message_too_large` (con `message_index`, `size_bytes`, `limit_bytes`), `no_smtp_account` |

## Consultar envíos

`GET /notificaciones/dispatches?status=&consumer=&consumer_reference=&created_from=&created_to=`

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
  "created_by": {"id": "…", "label": "…"}
}
```

`status` se calcula: `pending` (ninguno empezó), `in_progress` (alguno en
`pending`/`sending`/`retrying`), `completed` (todos `sent`),
`completed_with_errors` (ninguno en curso y alguno `failed`, `uncertain` o
`cancelled`).

`GET /notificaciones/dispatches/{id}/messages?status=`: lista resumida
(destinatarios, asunto, estado, `consumer_reference`, `sent_at`).

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
