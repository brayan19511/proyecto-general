# Modelo de datos de pagos-proveedores

Estado (2026-10-01): **implementado** (migraciones Alembic del schema `pagos_proveedores`). Convenciones iguales a
notificaciones: schema `pagos_proveedores`, `AuditMixin`, `actors` propio,
`change_history` (con `reason`), `company_id` sin FK, baja lógica, nombres en
inglés y fechas UTC.

## company_settings

Una fila activa por empresa (índice único filtrado), creada al guardar la
primera vez (acuerdo 2026-10-01).

| Campo | Uso |
|---|---|
| `company_id` | Empresa de auth (sin FK) |
| `default_template_code` | Plantilla de notificaciones de los lotes; `NULL` = `DEFAULT_TEMPLATE_CODE` del servicio. La elige `payments.admin` |

## providers

Maestro de proveedores por empresa.

| Columna | Nota |
| --- | --- |
| `company_id`, `tax_id` | RUC/DNI normalizado (solo alfanuméricos en mayúscula). Único entre activos de la empresa |
| `legal_name` | Razón social |
| `commercial_names` | JSON: otros nombres con que aparece en las constancias |
| `match_names` | JSON derivado (claves normalizadas de razón social y nombres comerciales) para buscar por nombre. Se recalcula al guardar; nunca viene del body |
| `payment_emails` | JSON, normalizados |

Implementado (2026-10-01): `tax_id` con `document_key` (solo alfanuméricos en
mayúscula, como `clave_documento` de proyecto-05); `match_names` con
`name_key` (sin tildes, mayúscula, sin puntuación, como `clave_comparacion`).
Regla agregada: una clave de nombre no puede pertenecer a dos proveedores
activos de la empresa (409), porque el lector no sabría a quién asignar la
constancia. Correos y nombres comerciales sin duplicados. Búsqueda por RUC/DNI
y razón social.

## batches

| Columna | Nota |
| --- | --- |
| `company_id`, `reference` | Referencia opcional del usuario; va como `consumer_reference` a notificaciones |
| `status` | `draft` → `sending` → `sent` |
| `notification_dispatch_id` | Id del envío en notificaciones |
| `sent_at` | Quién subió: `created_by`; quién envió: `updated_by` |

- Descartar: baja lógica solo en `draft` (acuerdo 4).
- Hasta 100 archivos por lote, leídos al subirlos (acuerdo 5).

## batch_files

| Columna | Nota |
| --- | --- |
| `batch_id`, `sequence`, `original_filename`, `suggested_filename` | `suggested_filename` = titular + fecha (ZIP) |
| `size_bytes`, `sha256`, `content` | Contenido en la base, carga diferida, sin purga (retención indefinida) |
| `parse_status`, `parse_error`, `used_ocr` | `parsed` o `error` |
| `beneficiary_name`, `beneficiary_tax_id`, `account`, `currency`, `amount` (`Numeric(19,2)`), `operation_date` | Lo extraído |
| `extracted` | JSON con el resto de lo que lee el parser |
| `already_sent_in_batch_id` | Este pago ya se envió en otro lote de la empresa (aviso, no bloquea) |
| `already_sent_match` | Cómo se detectó: `file` (mismo `sha256`) o `data` (otro PDF con el mismo RUC/DNI, cuenta, moneda, monto y fecha; y número de operación si ambos lo tienen). Acuerdo 2026-10-01 |
| `delivery_id` | Entrega a la que se asignó al enviar |

Mismo `sha256` dos veces en un lote: 422 (acuerdo 3).

Ajustes al implementar (2026-10-01, paso 5a):
- Sin columna `suggested_filename`: el nombre titular + fecha se calcula con
  los grupos (usa la razón social del maestro cuando la constancia no trae
  nombre), igual que el ZIP de proyecto-05.
- Quitar una constancia de un borrador (`DELETE /batches/{id}/files/{file_id}`,
  baja lógica): sin esto, un PDF ilegible bloquearía todo el lote.
- `batches` guarda también `template_code`, `custom_subject` y
  `custom_message`, fijados al enviar para que un reintento mande lo mismo.
- Máximo 25 MB por constancia (el límite de un correo en notificaciones).

## batch_deliveries

Una por proveedor al enviar: `batch_id`, `provider_id`, copia de `tax_id`,
`legal_name` y `payment_emails` en ese momento, `totals` (JSON por moneda). Su
id es el `consumer_reference` de cada mensaje en notificaciones.

## Reglas acordadas

1. Grupos calculados al consultar un borrador, con el maestro actual; solo se
   congelan al enviar (`batch_deliveries`). No hay `refresh`.
2. Envío en dos fases: (1) bloquear, validar, crear entregas y pasar a
   `sending`; (2) llamar a notificaciones con `Idempotency-Key` = id del lote y
   el contenido congelado; si responde, `sent`. Reintentar desde `sending`
   reenvía lo mismo (200 si ya se creó).
3. Duplicados: 422 en el mismo lote; aviso si ya se envió en otro.
4. Descartar solo en `draft`.
5. Lectura al subir, máximo 100 archivos por lote.

## Cobertura de proyecto-05

| proyecto-05 | Aquí |
| --- | --- |
| CRUD de proveedores con búsqueda y filtro activo | `providers` + rutas |
| `/payments/preview` | Crear lote + `GET /batches/{id}` (grupos al momento) |
| `/payments/renamed-zip` | ZIP del lote desde `batch_files` |
| `/payments/send` y `/send-async` (con `batch_size`) | Envío del lote vía notificaciones (asíncrono allí; `batch_size` ya no aplica) |
| `mailing_parameter_id` / `_name` | `template_code` opcional al enviar (default `payment_provider_summary`) |
| `subject_override`, `message_override` | Parámetros `asunto` y `mensaje` que recibe la plantilla (sin columnas nuevas) |
| Constancias archivadas (listar y descargar) | `batch_files` del lote: listar y descargar |
| Seguimiento del job | Estado del envío consultado en notificaciones |
