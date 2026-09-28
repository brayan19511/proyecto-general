# Referencia: implementación previa en proyecto-05

Código previo del usuario en `D:\proyectos\proyecto-05\app\api\finance\libro_mayor`
(también en github.com/brayan19511/proyecto-05). Es **referencia de flujo**, no
código a copiar: no seguía las reglas de esta plataforma (multiempresa, bajas
lógicas, historial, actores). No modificar ese proyecto desde aquí.

## Estructura

| Archivo | Responsabilidad |
| --- | --- |
| `constants.py` | Columnas de búsqueda de texto; cuentas `95`/`97` |
| `repository/sap_finance_repository.py` | SQL a la vista HANA `VW_LIBRO_MAYOR_PERSONALIZADO_2` por rango o delta |
| `repository/libro_mayor_repository.py` | Consultas locales, candidatos por regla, upsert, actualización de clasificación, resumen, exportación |
| `repository/reglas_gastos_repository.py` | CRUD de reglas |
| `service/libro_mayor_rules_service.py` | Motor de reglas con pandas (máscaras por condición) |
| `libro_mayor_service.py` | `sync` y `sync_delta`: SAP → DataFrame → reglas → upsert |
| `service/libro_mayor_reproces_service.py` | Reproceso por regla, cuenta, rango, regla borrada o todo |
| `service/reglas_gastos_service.py` | CRUD de reglas + reproceso inmediato |
| `service/libro_mayor_job_service.py` | Crea jobs con un ítem por cuenta y día |
| `service/libro_mayor_job_processor.py` | Ejecuta ítems con estado, cancelación y progreso |
| `libro_mayor_router.py` | Endpoints `/libro-mayor/...` |
| `app/workers/ledger_tasks.py`, `scheduled_tasks.py` | Celery: procesa lotes y *tick* de tareas programadas |

## Flujo que se conserva

1. Leer de SAP por rango de fechas o delta (`fecha_creacion`/`fecha_actualizacion`
   ≥ última actualización local) y cuenta con `LIKE 'NN%'`.
2. Quedarse con las columnas conocidas.
3. Aplicar reglas activas por `prioridad, id_regla`; primera coincidencia gana.
4. Upsert por (`transaccion_id`, `linea`).
5. Al crear/editar una regla: candidatos = líneas con esa regla ∪ líneas que
   cumplen sus condiciones; reclasificar con todas las reglas.
6. Al borrar una regla: reclasificar las líneas que la tenían.
7. Trabajos troceados por cuenta y día, con idempotency key y progreso.

## Endpoints previos

`POST /sync`, `/sync-async`, `/sync-delta`, `/sync-delta-async`,
`/sync-delta-all`, `/sync-delta-all-async`, `/reprocess/rule/{id}`,
`/reprocess/date-range`, `/reprocess/date-range-async`;
`GET /get-all`, `/get-by-sap`, `/export-excel`, `/summary`, `/summary-detail`;
CRUD `/rule`. Permisos: `ledger.sync`, `ledger.view`, `ledger.export`,
`expenses.view`, `expenses.edit`, `sap.read`, `sap.execute`.

## Problemas a no repetir

- **Sin empresa**: no hay `company_id`; ninguna consulta local filtra empresa.
  Las reglas de una compañía se aplicarían a la otra.
- **Sin filtro por área**: cualquier usuario con `ledger.view` ve todo.
- **Borrado físico** de reglas (`db.delete`), sin historial.
- **Schemas SAP en código** (`ALLOWED_COMPANIES`) e interpolados con f-string;
  la lista cerrada evita inyección, pero debe venir de configuración.
- **Cuentas y fecha inicial fijas** (`95`, `97`, `2026-01-01`).
- **Commit por lote** en `upsert` y `update_classification`: un fallo deja la
  carga a medias sin registro de hasta dónde llegó.
- **Marca de agua** tomada de la línea local más reciente, no de una ejecución
  confirmada; en `sync_delta` se pasa un `datetime` donde se esperaba `date`.
- **`tipo_cuenta = cuenta[:2]`**: asume cuentas de dos dígitos de prefijo.
- **Upsert sobrescribe `updated_by`** con el usuario de la ejecución y un job
  automático requiere `user_id`.
- **`HTTPException` dentro de servicios** y `except Exception` genérico en el
  router; mezcla capas.
- **Candidatos por regla** filtran por monto/texto aunque la regla sea de otro
  tipo, y `texto_excluido` no se usa al buscar candidatos (correcto, pero debe
  documentarse por qué).
- **`reprocess_all`** llama a `get_all()`, que no existe en el repositorio.
- **`float`** en el resumen de importes.
- **`get_by_account`** de reglas usa `ILIKE '%cuenta%'`: coincide con
  cuentas que solo contienen el texto.
- **Carga completa en memoria** con `.all()` tras `yield_per` y DataFrames
  enteros; revisar volumen antes de decidir pandas.

## Decisiones pendientes derivadas

- ¿Se mantiene pandas para el motor de reglas o una función Python simple por
  línea? pandas acelera grandes volúmenes pero es una dependencia pesada; se
  decidirá midiendo el volumen real de una cuenta/mes.
- ¿Se conserva la infraestructura genérica de jobs (Job/JobBatch/JobItem +
  Celery) o un `sync_runs` simple? Recomendación: simple al inicio.
