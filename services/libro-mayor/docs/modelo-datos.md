# Modelo de datos de libro-mayor

Propuesta en revisión; no hay modelos ni migraciones. Se marcan los
**acuerdos** del usuario; lo demás son propuestas a confirmar en el paso de
cada modelo.

## Convenciones

- Schema `libro_mayor` (acuerdo), declarado una vez en `Base.metadata`
  (`app/models/entities.py`); Alembic limitado a ese schema, con su versión en
  `libro_mayor.alembic_version`.
- No hay schema master ni compartido (arquitectura). `company_id` y `area_id`
  de auth son solo referencias (UUID sin FK); este servicio nunca lee tablas de
  auth, valida esos ids vía su API. Si otro servicio necesita lo mismo, se
  comparte **código** (como `packages/platform-audit`), no tablas.
- Todas las tablas: `id`, `created_at`, `created_by`, `updated_at`,
  `updated_by`, `is_active`, `deleted_at`, `deleted_by` (un `AuditMixin`).
  `created_by`/`updated_by`/`deleted_by` son FK a `actors` (mismo schema).
- `company_id` en todas las tablas de negocio, primero en índices y unicidades.
- Importes `Numeric(19, 4)` en líneas y en límites de reglas (misma escala),
  con signo tal como SAP (acuerdo). Fechas UTC.
- Nombres en inglés, sin mezclar significado SAP y propio (`sap_updated_at`
  frente a `updated_at`).

## actors

**Implementado** (`app/models/entities.py`, revisión `605d4653b27d`).
Acuerdo: catálogo local de actores (opción A), propio de este servicio.

`kind` (`user` | `system` | `service`), `subject_ref` (UUID de usuario de auth,
o nombre estable del proceso, p. ej. `libro-mayor.scheduler`), `label` mínimo
(sin email ni datos personales). Único (`kind`, `subject_ref`).

- Usuario: se registra la primera vez que opera, con el id validado por auth.
- Sistema: filas creadas por migración/seed, p. ej. el scheduler interno
  (acuerdo: la sincronización programada es un proceso interno, sin API key).
- Las filas de `actors` se atribuyen a sí mismas o a un actor de sistema de
  bootstrap; detalle al implementarlo.

## Unicidad entre filas activas

"Único activo" se implementa con índices únicos filtrados por `is_active`
(`unique_active()` en `entities.py`): `WHERE is_active` en PostgreSQL y
`WHERE is_active = 1` en SQL Server. Una baja lógica no bloquea volver a
registrar el mismo valor; las filas dadas de baja se conservan.

## sap_companies

**Implementado** (revisión `8b83c4465b06`). Empresa → compañía SAP.

`company_id` (UUID de auth), `sap_schema` (p. ej. `SBO_RASH_PRODUCCION`),
`source_view` (p. ej. `VW_LIBRO_MAYOR_PERSONALIZADO_2`), `sync_start_date`
(desde qué fecha contable es la primera carga de cada cuenta).

- Único activo `company_id` (una compañía SAP por empresa) y único activo
  `sap_schema` (un schema SAP no puede alimentar dos empresas).
- `sap_schema` y `source_view` se usarán como identificadores SQL: el
  servicio debe validarlos (solo letras, dígitos y `_`) al guardar. No hay
  CHECK de base porque las expresiones regulares no son portables.
- Credenciales HANA fuera de esta tabla (configuración del despliegue).
- Solo administración de plataforma.

## accounts

**Implementado** (revisión `8b83c4465b06`). Cuentas a sincronizar por empresa.

`company_id`, `code` (hasta 20), `match_mode` (`exact` | `prefix`, CHECK),
`name` opcional (referencia; el nombre de cada línea viene de SAP).
Único activo (`company_id`, `code`).

- Ejemplos: `95` prefijo (todo 95…); `979005400` exacta; `701110002` exacta.
- Acuerdo: se prohíben registros superpuestos. Dos cuentas activas de una
  empresa se superponen si pueden cubrir una misma cuenta SAP:

  | Activa | Nueva | ¿Superpone? |
  | --- | --- | --- |
  | `97` prefix | `979005400` exact | Sí |
  | `979005400` exact | `97` prefix | Sí |
  | `97` prefix | `979` prefix | Sí (uno empieza por el otro) |
  | `95` prefix | `979005400` exact | No |
  | `979005400` exact | `979005610` exact | No |

  Regla: si alguna de las dos es prefijo, se superponen cuando el código de
  la otra empieza por ese prefijo (con dos prefijos basta que uno empiece por
  el otro). Dos exactas solo chocan si son iguales, y eso ya lo impide la
  unicidad de base.
- La base solo impide repetir el mismo `code`; la superposición la valida el
  servicio al registrar (comparación "empieza por", no portable como
  restricción). Para que dos registros simultáneos no pasen ambos la
  validación, el servicio bloquea la fila de `sap_companies` de la empresa
  (`with_for_update()` en SQLAlchemy) durante la transacción. Implementado en
  `app/services/account_service.py` y probado con altas simultáneas en
  PostgreSQL; en SQL Server el bloqueo está por validar. Sin compañía SAP
  activa no se registran cuentas (409).
- Así cada línea pertenece a una sola cuenta registrada y
  `ledger_lines.account_id` no es ambiguo. Para pasar de `97` a cuentas
  explícitas se da de baja el prefijo y luego se registran las exactas.
- Dar de baja una cuenta detiene su sincronización; no toca líneas ya traídas.
- Una cuenta nueva hace su primera carga desde `sap_companies.sync_start_date`.

## change_history

**Implementado** (revisión `d96307b64e1a`). Historial de negocio genérico
(acuerdo), en lugar de una tabla por entidad.

`action` (p. ej. `account.create`, `account.delete`), `resource_type`,
`resource_id`, `company_id` (nullable), `trace_id` (enlace con `audit.logs`),
`before`/`after` JSON con campos permitidos. Actor y fecha en
`created_by`/`created_at`. Índices (`resource_type`, `resource_id`) y
(`company_id`, `created_at`).

- Se inserta en la misma transacción que el cambio (`app/services/history.py`).
- Solo anexado: un listener del ORM rechaza UPDATE/DELETE de estas filas (no
  protege contra SQL directo). Una corrección es otro evento.
- Lo usarán también reglas, categorías y homologaciones.

## expense_categories

**Implementado** (revisión `f1cfc1eac2ab`). Acuerdo: catálogo de categorías.

`company_id`, `parent_id` nullable (NULL = categoría; con valor =
subcategoría; solo dos niveles), `code` (p. ej. `GV08`), `name` (p. ej.
`OPERACIONES`). Único activo (`company_id`, `code`) en ambos niveles. Se
edita `code` y `name`; no cambia de nivel ni de padre. Baja: 409 si tiene
subcategorías o reglas activas. Historial en `change_history`.

## expense_rules

**Implementado** (revisión `f1cfc1eac2ab`). Antes `finance.reglas_gastos`.

`company_id`, `priority`, condiciones (`account_code`, `counter_account_code`,
`cost_center_code`, `include_text`, `exclude_text`, `amount_min`,
`amount_max` en `Numeric(19,4)`) y resultado (`category_id` → categoría o
subcategoría, `report_name`).

- Acuerdo: sin `tipo_regla`.
- Validaciones: al menos una condición; `amount_min <= amount_max` (también
  CHECK); categoría activa de la misma empresa.
- Orden `priority, id`; gana la primera que cumple todas sus condiciones.
- Índice (`company_id`, `is_active`, `priority`). Historial en `change_history`.

## classification_runs

**Implementado.** Reclasificación de `ledger_lines` en el worker.
`reason` (`rule_change` | `manual`), `rule_id` (la regla que la originó),
`date_from`/`date_to` (manual, opcional), `status`, `rows_checked`,
`rows_changed`, `last_line_id` (avance por lotes), `started_at`,
`heartbeat_at`, `finished_at`, `safe_error`, `trace_id`.

## Consultas en vivo (sin tablas)

Retiradas en la revisión `0708533d3e77` (decisión del usuario, 2026-09-30):
`live_queries`, `live_query_parts` y `live_query_lines` eran de la versión
asíncrona. La consulta en vivo ahora responde en la misma solicitud y no
guarda resultados.

## ledger_lines

**Implementado** (revisión `a5f6bc046f7c`). Copia local de líneas SAP, tal
como vienen (acuerdo). Nunca se borran.

- Único (`company_id`, `sap_transaction_id`, `sap_line`), la clave SAP.
- Datos SAP (columna de la vista entre paréntesis): `posting_date`
  (fecha_contabilizacion), `document_date`, `document_number`,
  `transaction_type`, `folio`, `document_type`, `account_code` y
  `account_name` (cuenta_asociada y su nombre), `supplier`, `description`,
  `line_comment`, `counter_account_code`/`counter_account_name`,
  `reference_1..3`, `amount_local`/`amount_foreign` (`Numeric(19,4)`, con
  signo), `cost_center_code`/`cost_center_area`/`cost_center_name`
  (centro_costo, centro_area, nombre_area), `sap_created_at`/`sap_updated_at`
  (hora de SAP sin zona). La correspondencia completa está en `FIELD_MAP`
  (`app/services/sync_service.py`).
- Propios: `account_id` (FK a la cuenta registrada que la trajo; reemplaza
  `tipo_cuenta = cuenta[:2]`) y `last_sync_run_id` (FK a la ejecución que la
  trajo o actualizó por última vez). `created_by`/`updated_by` = actor
  `libro-mayor.worker`.
- Clasificación (revisión `f1cfc1eac2ab`): `rule_id` nullable (FK
  `fk_ledger_lines_rule_id` a `expense_rules`) y `classified_at`. La
  categoría y el nombre de reporte se obtienen por `rule_id`, no se copian.
- Las columnas SAP están en el mixin `SapLineColumns` (`entities.py`).
- Índices: (`company_id`, `posting_date`), (`account_id`, `posting_date`),
  (`company_id`, `cost_center_code`), (`company_id`, `sap_updated_at`).
- Confirmar con `scripts/check_sap.py` los tipos reales y si `centro_area` y
  `centro_costo` son campos distintos (en el export de septiembre 2026 "Area"
  es el nombre del centro).

## cost_centers

Catálogo local de centros de costo SAP. `company_id`, `code` (p. ej.
`V1141177`), `sap_name` (p. ej. `T65 REAL PLAZA PURUCHUCO I`),
`first_seen_at`, `last_seen_at`. Único (`company_id`, `code`). Se alimenta al
sincronizar; origen adicional desde SAP pendiente.

## cost_center_mappings

Homologación acordada: centro de costo → área de auth.

`company_id`, `cost_center_code` (código completo o prefijo), `match_mode`
(`exact` | `prefix`; acuerdo: la columna existe desde el inicio, primero solo
se usa `exact`), `auth_area_id` (UUID de auth, sin FK, validado contra auth al
guardar). Único activo (`company_id`, `cost_center_code`, `match_mode`);
acuerdo: un centro pertenece a una sola área. Baja lógica e historial
en `change_history`. Con `prefix`: exacto > prefijo más largo.

## sync_runs

**Implementado** (revisión `a5f6bc046f7c`). Estado persistente de cada
sincronización (no es un log técnico).

`company_id`, `account_id` (FK), `kind` (`sync` manual | `initial` |
`delta`, ver readme),
`origin` (`manual` | `schedule`; no se llama `trigger` porque es palabra
reservada en SQL Server), `status` (`pending` | `running` | `succeeded` |
`failed`), `date_from`/`date_to` (fechas de contabilización, inclusivas),
`days_total`, `days_done`, `rows_read`, `rows_inserted`, `rows_updated`,
`started_at`, `heartbeat_at`, `finished_at`, `safe_error` (mensaje apto para
mostrar), `trace_id` (solicitud que la creó), `schedule_slot` (turno del
horario en UTC; NULL en las manuales). Quién la pidió: `created_by`
(usuario o `libro-mayor.scheduler`).

- Índice único filtrado por `status IN ('pending', 'running')` sobre
  `account_id`: una sola ejecución abierta por cuenta.
- Índice único filtrado (`account_id`, `schedule_slot`) donde no es NULL: una
  sola ejecución por cuenta y turno aunque haya varios workers.
- CHECK de estado, tipo, origen y `date_to >= date_from`.
- Sin `idempotency_key`: repetir es seguro porque el upsert no duplica, y la
  unicidad impide dos abiertas a la vez.
- Marca de agua (implementado, revisión `d608ca9bd49a`): se deriva de
  `sync_runs` (máximo `date_to` de `initial`/`delta` correctos), sin tabla
  aparte. No se toma de las líneas locales (proyecto-05 lo hacía y un sync
  manual podía adelantarla).

## Diferencias deliberadas con proyecto-05

| proyecto-05 | Aquí |
| --- | --- |
| Sin empresa en tablas | `company_id` en todas |
| `db.delete(regla)` | Baja lógica + historial |
| `activo` propio | `is_active` + `deleted_at/by` comunes |
| `created_by` = usuario, también en jobs | Catálogo `actors` con actor de sistema |
| `commit` por lote de 5000 en upsert | Estado de ejecución; decidir transacción por lote vs total |
| Schemas SAP permitidos en código | Tabla/configuración por empresa |
| Cuentas `95`/`97` en constantes, `tipo_cuenta = cuenta[:2]` | Tabla `accounts` (prefijo o exacta) y `account_id` |
| `tipo_regla` libre | Eliminado (acuerdo) |
| `codigo`/`subcodigo` como texto en regla y línea | `expense_categories` y `rule_id` |
| `tiene_regla` | `rule_id IS NOT NULL` |
| `rule_id` sin FK | FK dentro del schema |
| `updated_by` sobrescrito en cada carga | `last_sync_run_id` |
| Escalas `(19,6)` y `(19,4)` | `(19,4)` en ambos |
| pandas/numpy | Python simple (acuerdo; revisar si el volumen lo exige) |
| Tablas `Job`/`JobBatch`/`JobItem` + Celery | `sync_runs` + worker propio |
| `float` en resumen | `Decimal` |
