# Servicio libro-mayor (gastos contables)

Estado: **sincronización desde SAP (manual, programada y delta), categorías,
reglas y motor de clasificación, reclasificación y consultas en vivo en una
sola llamada (tramos en paralelo, sin guardar resultados)**, pendiente de probar contra HANA real. Hay configuración, conexión PostgreSQL,
logs (`packages/platform-audit`) con consulta para el administrador,
health/ready, Dockerfile, Alembic (schema `libro_mayor`), actores, historial de
cambios, identidad y permisos vía auth, rutas de compañía SAP y cuentas, seed,
conexión HANA de solo lectura, lector de la vista (`app/sap/`), líneas del
libro mayor, ejecuciones de sincronización y worker con horario y delta,
categorías, reglas, motor de clasificación, consultas en vivo, consultas
sobre las líneas sincronizadas y homologación de centros de costo con filtro
por áreas. Lo demás descrito en `docs/` son objetivos.

## Propósito

Traer desde SAP Business One (HANA) las líneas del libro mayor de las cuentas
registradas, clasificarlas con reglas administrables y ofrecer consultas de
gastos limitadas a las áreas que cada usuario tiene autorizadas. Primera
empresa prevista: RadioShack (Perú); otro país comparte el mismo servidor HANA
con otra base/schema de compañía.

## Ejecutar en local

Desde `services/libro-mayor`, con un entorno virtual propio:

```powershell
py -3.14 -m venv enviroment   # Python 3.14, igual que el Dockerfile (uuid7)
.\enviroment\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # completar DB_NAME, DB_USER, DB_PASSWORD y AUTH_URL
.\enviroment\Scripts\python.exe -m alembic upgrade head
.\enviroment\Scripts\python.exe scripts/migrate_audit.py
.\enviroment\Scripts\python.exe -m uvicorn app.main:app --reload --port 8003
```

- `http://localhost:8003/libro-mayor/health` → `{"status": "ok"}` (proceso vivo).
- `http://localhost:8003/libro-mayor/ready` → 200 si la base responde; 503 si no.
- Documentación: `http://localhost:8003/libro-mayor/docs`.

El puerto 8003 es solo un ejemplo local (8002 lo usa la central en el
Compose); en Docker el servicio escucha en 8000. `AUTH_URL` debe apuntar a un
auth alcanzable desde donde corre el servicio.

Imagen (desde la raíz del repositorio):

```powershell
docker build -f services/libro-mayor/Dockerfile -t libro-mayor:0.1.0 .
```

## Rutas

Todas bajo `/libro-mayor`. Las de empresa exigen `Authorization: Bearer` y
`X-Company-Id`.

| Ruta | Quién | Qué hace |
| --- | --- | --- |
| `GET /admin/sap-company` | Admin de plataforma | Compañía SAP activa de la empresa (404 si no hay) |
| `POST /admin/sap-company` | Admin de plataforma | Configura `sap_schema`, `source_view`, `sync_start_date`. 409 si ya hay una activa o si el schema es de otra empresa; 422 si no es un identificador válido |
| `PATCH /admin/sap-company` | Admin de plataforma | Cambia solo lo enviado. `source_view` y `sync_start_date` siempre; `sap_schema` solo si la empresa no tiene líneas (409) |
| `DELETE /admin/sap-company` | Admin de plataforma | Baja lógica |
| `GET /sync-status` | `ledger.view` | Por cuenta: última carga correcta, marca de agua, horas desde la última, fallos seguidos, último error |
| `GET /ledger/lines` | `ledger.view` | Líneas sincronizadas y clasificadas, JSON paginado (`limit` ≤ 5000, `next_offset`). Filtros: `date_from`, `date_to`, `accounts`, `codigo`, `subcodigo`, `no_subcodigo`, `supplier`, `no_supplier`, `cost_center_code`, `unclassified` |
| `GET /ledger/lines.csv` | `ledger.view` | Mismos filtros, todo el rango en CSV en streaming (Excel / Power BI "Desde la web"); `sep=;` opcional |
| `GET /ledger/summary` | `ledger.view` | Mismos filtros; por año, mes, `codigo`, `subcodigo` y, con `by_supplier=true`, `supplier` |
| `GET /accounts` | `ledger.view` | Cuentas activas (`include_inactive=true` para ver bajas); paginado |
| `POST /accounts` | `ledger.admin` | Alta `{code, match_mode, name?}`. 409 si se superpone o si la empresa no tiene compañía SAP; 422 si el código no es numérico |
| `GET /accounts/{id}` | `ledger.view` | Una cuenta, activa o dada de baja |
| `PATCH /accounts/{id}` | `ledger.admin` | Cambia solo lo enviado. `name` siempre; `code`/`match_mode` solo si la cuenta no tiene líneas ni sincronización abierta (409: dar de baja y registrar otra); 409 si se superpone |
| `DELETE /accounts/{id}` | `ledger.admin` | Baja lógica; deja de sincronizarse, se conservan sus líneas |
| `POST /sync-runs` | `ledger.admin` | `{account_id, date_from, date_to}` → 202 con la ejecución `pending`. 409 si la cuenta ya tiene una abierta o falta SAP; 422 si el rango es inválido, futuro o supera `SYNC_MAX_DAYS` |
| `GET /sync-runs` | `ledger.view` | Ejecuciones (filtros `account_id`, `status`), más recientes primero |
| `GET /sync-runs/{id}` | `ledger.view` | Estado y avance: `days_done`/`days_total`, filas leídas, nuevas y actualizadas, `safe_error` |
| `GET/POST /categories`, `GET/PATCH/DELETE /categories/{id}` | GET `ledger.view`; resto `ledger.update` | Categorías de dos niveles (`parent_id` = subcategoría). Baja: 409 si tiene subcategorías o reglas activas |
| `GET/POST /rules`, `GET/PATCH/DELETE /rules/{id}` | GET `ledger.view`; resto `ledger.update` | Reglas en orden de evaluación. Alta, edición y baja registran una reclasificación para el worker |
| `POST /rules/import` | `ledger.update` | Carga masiva en una transacción: `mode` (`append`/`replace`), `dry_run`, categorías por nombre (se crean si faltan). Ver la guía |
| `POST /classification-runs` | `ledger.update` | `{date_from?, date_to?}` → 202. Reclasifica todas las líneas (o un rango) con las reglas activas |
| `GET /classification-runs`, `/{id}` | `ledger.view` | Estado: `rows_checked`, `rows_changed` |
| `POST /live-queries` | `ledger.view` | `{accounts, date_from, date_to, split?, view?}` → **200 con la respuesta completa** (por defecto solo las líneas clasificadas). Consulta SAP en vivo en la misma solicitud; no guarda nada. Ver "Consultas en vivo" |
| `GET /cost-centers` | `ledger.view` (company) | Centros que aparecen en las líneas, con su área y qué homologación aplicó (`match_mode`, `mapping_code`); `unmapped=true` = solo los que faltan (incluye una fila `null` = líneas sin centro) |
| `GET /cost-center-mappings` | `ledger.view` (company) | Homologaciones activas (`include_inactive=true` para ver bajas) |
| `POST /cost-center-mappings` | `ledger.admin` | `{cost_center_code, match_mode?, area_code}` (o `area_id`; `match_mode` `exact` por defecto o `prefix`) → 201. 422 si el área no existe o está de baja en auth; 409 si ese código con ese modo ya tiene área |
| `PATCH /cost-center-mappings/{id}` | `ledger.admin` | `{area_code}` o `{area_id}`: mueve el centro (o prefijo) a otra área. Código y modo no se editan: baja y alta |
| `DELETE /cost-center-mappings/{id}` | `ledger.admin` | Baja lógica: sus líneas pasan a verse solo con alcance company |
| `POST /cost-center-mappings/import` | `ledger.admin` | Carga masiva `{mode, dry_run, mappings}` en una transacción. Ver la guía |
| `POST /admin/seed` | Admin de plataforma | Carga inicial de la empresa (solo con `SEED_ENABLED=true`; si no, 404). Ver "Seed" |
| `GET /admin/logs` | Admin de plataforma (sin `X-Company-Id`) | Logs propios (filtros `trace_id`, `user_id`, `outcome`, `path_prefix`) |
| `GET /admin/logs/{id}` | Admin de plataforma | Log con sus detalles y pasos |

El body no acepta campos no declarados (`created_by`, `company_id`, …): 422.
En PATCH, `null` solo se acepta en `name` (borra el nombre).

Por qué algunos campos no se editan con datos ya sincronizados: las líneas
traídas pertenecen a la cuenta (`code` + `match_mode`) y a la compañía SAP
(`sap_schema`) que las trajeron. Cambiarlos dejaría líneas que ya no
corresponden a su configuración; en ese caso se da de baja y se registra otra.

## Identidad y permisos

`app/api/dependencies.py`. libro-mayor no valida tokens: pregunta a auth.

- Rutas de empresa: **una** llamada a `GET /auth/me/permissions`, reenviando
  el Bearer (con `X-Company-Id`) o la `X-API-Key` (la empresa es la de la
  clave). Auth devuelve `user_id` (campo agregado de forma compatible,
  2026-09-30), empresa validada y permisos con alcance. Una API key nunca es
  administrador de plataforma y sus permisos se limitan a sus scopes.
- Rutas sin empresa (logs): `GET /auth/me`, solo Bearer.

Una sesión revocada, una API key revocada o una membresía dada de baja pierde
acceso de inmediato. Sin reintentos; auth caído → 502, lento → 504. Si auth es
anterior al campo `user_id`, responde 502 "auth no está actualizado":
desplegar auth primero.

**Permisos** (acuerdo del usuario, 2026-09-30): tres niveles, cada uno
incluye al anterior (`app/core/permissions.py`). `ledger.update` y
`ledger.admin` son de alcance `company`; `ledger.view` admite `company` o
`area`:

| Permiso | Puede |
| --- | --- |
| `ledger.view` | Consultar líneas, resumen, CSV y en vivo; ver reglas, categorías, cuentas, sincronizaciones y su estado |
| `ledger.update` | Además crear, editar y dar de baja reglas y categorías, la carga masiva y reclasificar |
| `ledger.admin` | Además cuentas a sincronizar y sincronización manual |

Compañía SAP, seed y logs: solo el administrador de plataforma. Los tres
códigos están en el catálogo de auth (`services/auth/app/core/permissions.py`). Para
activarlos: volver a ejecutar el seed de auth (crea los permisos nuevos del
catálogo) y asignarlos a un rol con `POST /auth/roles/{role_id}/permissions`.
Una API key tiene como máximo los permisos de su usuario, recortados a sus
scopes: para Power BI basta `ledger.view`.

## Áreas y homologación de centros de costo

SAP no trae un área de negocio: trae el centro de costo (`V1141177 T65 REAL
PLAZA PURUCHUCO I`) y algunos centros no corresponden a un área o se
reemplazan por otros. La tabla `cost_center_mappings` dice a qué área de auth
pertenece cada centro. Igual que las cuentas, la homologación es por código
exacto (`exact`, el código completo) o por prefijo (`prefix`, todo centro que
empiece así: `V114` → todas las tiendas `V114…`). Si varias coinciden gana la
exacta y, entre prefijos, el más largo (acuerdo): así `V114` → VENTAS con la
excepción `V1141061` → ADMIN, o `A` → LOG con `A10` → ADMIN.
Un centro termina siempre en una sola área. Con eso se decide quién ve cada
línea:

| Usuario | Permiso en auth | Ve |
| --- | --- | --- |
| Contador master | `ledger.view` alcance `company` | Todo, incluso líneas sin centro o con centro sin homologar |
| Vendedor (puesto en VENTAS) | `ledger.view` alcance `area`, área VENTAS | Solo centros homologados a VENTAS |
| Contador asignado a ventas | `ledger.view` alcance `area`, área VENTAS | Igual que el anterior: solo VENTAS |
| Usuario con puestos en VENTAS y ADMINISTRACION | `ledger.view` alcance `area`, ambas áreas | Solo centros de esas dos áreas |

- Las áreas de un usuario salen de sus puestos activos en auth (unión de
  todos). Para dar o quitar un área se cambian los puestos en auth, no aquí.
- Se aplica en `GET /ledger/lines`, `/ledger/lines.csv`, `/ledger/summary` y
  `POST /live-queries`, siempre en el servidor: un filtro `cost_center_code`
  de otra área devuelve 0 líneas, no las de esa área.
- Un usuario de área sin centros homologados a sus áreas recibe 200 vacío.
- Cambiar o dar de baja una homologación rige en la consulta siguiente: el
  área se resuelve al consultar y no se reprocesan líneas.
- Cada línea devuelta trae `area_id` y `area_name` (null = sin homologar).
- Validación contra auth: al homologar, libro-mayor pide `GET /auth/areas`
  con las credenciales del mismo usuario y solo acepta un área activa de la
  empresa. Guarda `area_code` y `area_name` como copia para mostrarlos; si se
  renombra el área en auth, basta un PATCH para refrescarlos.
- Homologar es `ledger.admin`; ver las homologaciones y `GET /cost-centers`
  pide `ledger.view` de alcance company (un usuario de área no ve el mapa de
  toda la empresa).

## Seed

`POST /libro-mayor/admin/seed` con Bearer de administrador de plataforma y
`X-Company-Id`. Carga la compañía SAP y las cuentas de `app/seeds/data.py`
para el código de esa empresa en auth (hoy `RASH`: 95 y 97 por prefijo y dos
cuentas 701110… exactas; los datos los define el usuario en `data.py`).

- Solo existe con `SEED_ENABLED=true`: activarlo, ejecutarlo y volver a `false`.
- No usa token de bootstrap como auth: el administrador ya existe y se
  autentica con su sesión. Cada alta queda en `change_history` a su nombre.
- Idempotente y en una transacción: lo que existe igual se deja
  (`existing`), lo dado de baja no se reactiva (`kept_deactivated`), y un
  conflicto (otra compañía SAP activa, misma cuenta con otro modo,
  superposición) responde 409 sin guardar nada.
- Para agregar cuentas: editar `data.py` y volver a ejecutar, o `POST /accounts`.

## SAP HANA

Solo lectura. `app/sap/connection.py` crea el engine la primera vez que se usa;
sin `SAP_HOST` el servicio arranca igual y lo que necesite SAP responde 409.
`app/sap/ledger_reader.py` contiene todo el SQL hacia SAP:

- Columnas explícitas de la vista (`SAP_COLUMNS`, contrato tomado de
  proyecto-05), nunca `SELECT *`. No pide `usuario_id` ni `autor`.
- Schema y vista validados (letras, dígitos, `_`) y entre comillas; cuentas y
  fechas siempre como parámetros.
- Las cuentas se traducen a `"cuenta_asociada" = :a0` (exacta) o
  `LIKE :a1` con `95%` (prefijo).

Probar la conexión y el contrato de la vista (no escribe nada):

```powershell
.\enviroment\Scripts\python.exe scripts/check_sap.py --schema SBO_RASH_PRODUCCION --view VW_LIBRO_MAYOR_PERSONALIZADO_2
.\enviroment\Scripts\python.exe scripts/check_sap.py --schema SBO_RASH_PRODUCCION --view VW_LIBRO_MAYOR_PERSONALIZADO_2 --account 95 --mode prefix --date 2026-09-01
```

Muestra columnas faltantes o extra frente al contrato, cuántas líneas hay ese
día, el tipo Python de cada columna y si hay claves (`transaccion_id`,
`linea`) repetidas.

**Aviso Windows:** el driver `hdbcli` para Windows se cierra con *segmentation
fault* cuando **no logra conectar** (probado con Python 3.13/hdbcli 2.28, el
entorno de proyecto-05, y 3.14/2.30). En Linux (imagen Docker) el mismo caso da
un error normal. Si en Windows el script se cierra sin mensaje, revisar host,
puerto, VPN o firewall, o ejecutarlo dentro del contenedor.

## Sincronización

1. `POST /sync-runs` valida y registra la ejecución `pending`. No consulta SAP:
   el trabajo pesado nunca corre dentro de la solicitud HTTP.
2. El worker la toma, consulta SAP **por mes** (el delta, de una vez) y guarda
   cada tramo (líneas + avance) en una transacción. Si SAP o la red fallan,
   reintenta el tramo `SYNC_RETRIES` veces (30 s, 2 min). Si sigue fallando,
   la ejecución queda `failed` con un `safe_error` y hasta dónde llegó; la
   marca de agua no avanza y el siguiente turno recupera lo que faltó.
   `GET /sync-status` muestra fallos seguidos y horas desde la última carga
   correcta por cuenta.
3. Upsert por la clave SAP (`company_id`, `transaccion_id`, `linea`): nueva →
   se inserta; existente y cambiada en SAP → se actualiza; igual → no se toca.
   Repetir un rango no duplica. Consulta las existentes y actualiza con el ORM
   (portable; sin `ON CONFLICT` ni `MERGE`).
4. Las líneas se guardan tal como vienen (textos, signos, centros vacíos) y sin
   clasificar (`rule_id` llegará con el motor de reglas).
5. Si SAP devuelve un dato que no cumple el contrato (clave o importe vacío,
   fecha inválida, texto más largo que la columna, claves repetidas), la
   ejecución falla con un mensaje claro; no se recorta ni se corrige nada.

Una cuenta no puede tener dos ejecuciones pendientes o en curso (índice único
filtrado). Una ejecución `running` sin avance en `SYNC_STALE_MINUTES` se marca
`failed` como interrumpida; se reintenta creando otra.

### Tipos de ejecución

| `kind` | Quién la crea | Qué lee de SAP |
| --- | --- | --- |
| `sync` | `POST /sync-runs` | Rango de fechas de contabilización, día por día |
| `initial` | Horario, si la cuenta nunca completó un `initial` o `delta` | Desde `sap_companies.sync_start_date` hasta hoy, día por día |
| `delta` | Horario, las siguientes veces | Líneas creadas o actualizadas en SAP desde la marca de agua, en una consulta |

**Marca de agua** de una cuenta: el `date_to` (día SAP en que se creó) del
último `initial` o `delta` correcto. El siguiente delta relee **desde ese día
inclusive**: si SAP solo guarda la fecha (sin hora) de actualización, releer
el día evita perder cambios hechos después de la lectura anterior; el upsert
no duplica. Un `sync` manual no mueve la marca de agua (solo cubre su rango).
Un delta fallido tampoco: el siguiente turno vuelve a leer desde el mismo día.

### Horario

`SYNC_SCHEDULE` (default `06:00,10:00,14:00,18:00`) en `SAP_TIMEZONE`
(default `America/Lima`); **ambos por confirmar**. En cada vuelta el worker
calcula el último turno que ya pasó y crea, si falta, una ejecución por
cuenta activa (de empresas con compañía SAP activa) para ese turno:

- Si la cuenta tiene una ejecución abierta (p. ej. una manual), espera y la
  crea para el mismo turno cuando termine.
- Un índice único (`account_id`, `schedule_slot`) impide duplicarla si hay
  varios workers.
- Si el worker estuvo apagado varios turnos, al volver crea solo la del último:
  el delta recupera todos los cambios desde la marca de agua.
- `SYNC_SCHEDULE=off` desactiva el horario (solo manuales). Vacío no lo
  desactiva: una variable vacía usa el default.
- Las ejecuciones del horario se atribuyen al actor `libro-mayor.scheduler`
  (`origin=schedule`).

### Worker

Proceso separado de la API, misma imagen:

```powershell
.\enviroment\Scripts\python.exe -m app.worker          # queda corriendo
.\enviroment\Scripts\python.exe -m app.worker --once   # procesa las pendientes y termina
```

En Docker: `docker run ... libro-mayor:0.1.0 python -m app.worker` (el `CMD`
por defecto sigue siendo la API). Pueden correr varios: cada uno toma una
ejecución distinta (`SKIP LOCKED`). Con SIGTERM/Ctrl+C termina la ejecución en
curso y sale. Escribe en la salida estándar solo mensajes seguros: de un
error guarda el tipo y el código del driver, nunca el texto crudo (puede
traer datos). Las líneas y el estado de las ejecuciones se atribuyen al actor
de sistema `libro-mayor.worker`; quién pidió la ejecución queda en su
`created_by` y cada línea apunta a su última ejecución (`last_sync_run_id`).

## Clasificación

Motor: `app/services/classifier.py`, función pura usada igual por la
sincronización, la reclasificación y las consultas en vivo.

- Reglas activas de la empresa por `priority` y luego `id`; **gana la primera
  que cumple**. Una condición vacía no filtra; todas las llenas deben cumplirse.
- `account_code`, `counter_account_code`, `cost_center_code`: iguales exactos.
- `include_text` debe aparecer y `exclude_text` no, sin distinguir
  mayúsculas, en proveedor, descripción o referencias 1–3 (texto tal como
  viene de SAP).
- `amount_min`/`amount_max`: importe en moneda local **con signo**.
- `nombre_cuenta` (columna `report_name`): nombre con que se muestra la línea
  en reportes, como en proyecto-05. `codigo`/`subcodigo` agrupan; `nombre_cuenta`
  distingue, p. ej. "DIFERENCIA POR REDONDEO" y "DIFERENCIA DE INVENTARIO"
  dentro de la misma subcategoría. Opcional.
- Resultado: `rule_id` en la línea (NULL = sin clasificar). La categoría y la
  subcategoría se resuelven al leer: renombrarlas no obliga a reclasificar.
  `nombre_cuenta` vacío = nombre de la cuenta SAP.
- Nombres de la clasificación en la API (acuerdo, como proyecto-05): `codigo`
  (categoría), `subcodigo` (subcategoría) y `nombre_cuenta`. Las categorías se
  identifican por nombre, únicas en su nivel; no tienen código aparte.
- Sin `tipo_regla` ni pandas (acuerdos).

Cuándo se clasifica:

| Momento | Qué líneas |
| --- | --- |
| Sincronización | Cada línea nueva o cambiada, con las reglas vigentes al guardar |
| Alta, edición o baja de regla | Reclasificación `rule_change` en el worker: las que tenían esa regla + las que podrían cumplirla ahora (prefiltro SQL por cuenta, contrapartida, centro e importes; los textos se evalúan en Python) |
| `POST /classification-runs` | Todas las de la empresa o un rango de contabilización. Usarla una vez para clasificar lo sincronizado antes de tener reglas |

Carga masiva: `POST /rules/import` (todo o nada, `dry_run` para revisar antes,
`mode=replace` da de baja las activas sin borrar filas, una sola
reclasificación al final). `scripts/convert_legacy_rules.py` convierte el SQL
de proyecto-05; las reglas de RASH Perú convertidas están en
`data/import/reglas_rash_peru.json`.

La reclasificación avanza por lotes (`CLASSIFY_BATCH_SIZE`) con commit por
lote. No guarda historial por línea: el registro es la ejecución
(`classification_runs`, con quién la originó en `created_by`).

## Consultas en vivo

Una sola llamada que consulta SAP, clasifica y **devuelve la respuesta
completa**. No guarda nada en la base: la memoria se libera al responder.

```json
POST /libro-mayor/live-queries
{"accounts": ["95*", "97*", "701110002"], "date_from": "2026-01-01", "date_to": "2026-12-31",
 "split": "month", "view": "full"}
```

| Campo | Valores |
| --- | --- |
| `accounts` | `"95*"` = todas las que empiezan por 95; `"701110002"` = exacta. No hace falta que estén registradas; repetidas se ignoran |
| `split` | `month` (default: un año = 12 tramos) o `day` |
| `view` | `lines` (default: solo líneas), `summary` (solo totales, liviano) o `full` (ambos) |

Respuesta: `lines_total`, `chunks`, `elapsed_ms`, `summary` (por año, mes,
categoría y subcategoría: cantidad e importes con signo) y `lines` (en orden
contable, cada una con `rule_id`, `codigo`, `subcodigo` y `nombre_cuenta`).
`lines` es null con `view=summary`; `summary` es null con `view=lines`.

Cómo funciona:

1. Parte el rango en tramos (meses o días).
2. Consulta SAP **cada tramo en paralelo** en hilos de este proceso y clasifica
   cada línea con las reglas activas (las mismas para todos los tramos).
3. Une los tramos en orden y responde.

Controles de memoria y carga:

- **Pool compartido** (`LIVE_QUERY_PARALLEL`, 4): entre TODAS las solicitudes,
  el proceso nunca tiene más de N consultas abiertas contra SAP; las demás
  esperan turno. Probado: 6 consultas simultáneas → nunca más de 4 a SAP.
- **`view=lines` o `full`**: como máximo `LIVE_QUERY_MAX_LINES` (100 000)
  líneas; si se supera, 422 sugiriendo acotar o pedir `view=summary`.
- **`view=summary`**: cada tramo se resume al llegar y sus líneas se descartan;
  un año pesa unos pocos KB y no tiene límite de líneas.
- **Tiempo máximo** `LIVE_QUERY_TIMEOUT_SECONDS` (120 s) → 504. En la central esta
  ruta tiene su propio timeout (130 s), mayor que el de libro-mayor.
- Otros límites: `LIVE_QUERY_MAX_DAYS` (366) y `LIVE_QUERY_MAX_ACCOUNTS` (20).

Errores: 422 (cuenta, rango o demasiadas líneas), 409 (falta SAP o compañía
SAP), 502 (SAP falló o devolvió datos fuera de contrato; solo mensaje seguro),
504 (tiempo). Un usuario de área solo recibe las líneas de sus áreas (ver
"Áreas y homologación").

Prioridad del worker (sincronización y reclasificación): 1) reclasificaciones,
2) sincronizaciones. Las consultas en vivo no pasan por el worker.

## Consultas sobre lo sincronizado

`GET /ledger/lines` (JSON paginado), `/ledger/lines.csv` (todo el filtro en
streaming) y `/ledger/summary`. Leen `ledger_lines` en PostgreSQL, ya
clasificadas: no van a SAP ni evalúan reglas. Pensadas para reportes, la app
web y Excel / Power BI con API key (`X-API-Key`, ver la guía). El CSV lleva
BOM UTF-8, fechas ISO e importes con punto y signo. Un usuario de área solo
recibe las líneas de sus áreas (ver "Áreas y homologación").

Respuestas de más de 1 KB van comprimidas con gzip si el cliente lo acepta.

## Logs

- Cada solicitud queda en `audit.logs` con el usuario y la empresa validados
  (`set_actor` en las dependencias).
- Los servicios registran pasos (`account.create`, `account.delete`,
  `sap_company.create`, `sap_company.delete`) en `audit.logs_steps`.
- Las llamadas a auth llevan `X-Trace-Id` y `X-Parent-Operation-Id`: si auth
  tiene a libro-mayor en su `TRUSTED_PROXIES`, sus logs quedan enlazados.
- `scripts/migrate_audit.py` crea o actualiza el schema `audit` (idempotente).

## Historial de cambios

`libro_mayor.change_history`, de solo anexado: una fila por alta o baja de
compañía SAP o cuenta, con `action`, recurso, empresa, `trace_id`, actor,
fecha y `before`/`after` (solo campos permitidos). Se guarda en la misma
transacción que el cambio. El ORM impide editar o borrar eventos (no protege
contra SQL directo).

## Actores y AuditMixin

`app/models/common/mixin_model.py`: mismos campos comunes que la plantilla
(`id`, `created_*`, `updated_*`, `is_active`, `deleted_*`), con FK a
`libro_mayor.actors` en lugar de `users` de auth.

- `created_by`/`updated_by` obligatorios; `deleted_by` solo en bajas.
- En el alta, `updated_at`/`updated_by` = `created_at`/`created_by`. Al
  actualizar, el código los asigna (no hay `onupdate` automático).
- `actors`: `kind` (`user` | `system` | `service`), `subject_ref` (id de
  usuario de auth o nombre del proceso, p. ej. `libro-mayor.scheduler`).
- `app/services/actors.py` registra el actor la primera vez que opera, en la
  misma transacción del cambio, y se atribuye su propia alta. Sin seed.

## Migraciones (Alembic)

Schema `libro_mayor`, declarado una vez en `app/models/entities.py`. Alembic
crea el schema si no existe, guarda su versión en
`libro_mayor.alembic_version`, solo compara este schema y sus tablas, y tiene
`downgrade` deshabilitado (un error se corrige con otra migración).
`alembic.ini` no tiene URL: usa el `.env`.

| Revisión | Contenido |
| --- | --- |
| `605d4653b27d` actores | `actors` |
| `8b83c4465b06` companias sap y cuentas | `sap_companies`, `accounts`; únicos solo entre filas activas |
| `d96307b64e1a` historial de cambios | `change_history` |
| `a5f6bc046f7c` sincronizaciones y lineas | `sync_runs` (una abierta por cuenta) y `ledger_lines` (única por clave SAP) |
| `d608ca9bd49a` horario y delta | `sync_runs.schedule_slot` (única por cuenta y turno) y tipos `initial`/`delta`. El cambio del CHECK se escribió a mano: autogenerate no detecta cambios en CHECK |
| `f1cfc1eac2ab` categorias reglas y consultas en vivo | `expense_categories`, `expense_rules`, `classification_runs`; `ledger_lines.rule_id` y `classified_at`; tablas de la consulta en vivo asíncrona (retiradas en la siguiente) |
| `0708533d3e77` retirar consultas en vivo asincronas | Borra `live_queries`, `live_query_parts`, `live_query_lines` (decisión del usuario: la consulta en vivo responde en la misma llamada). Escrita a mano: autogenerate nunca propone borrar tablas |
| `7096d47b8a5d` categorias por nombre | Quita `expense_categories.code`; nombre único por nivel (índices filtrados) |

```powershell
.\enviroment\Scripts\python.exe -m alembic current
.\enviroment\Scripts\python.exe -m alembic revision --autogenerate -m "mensaje"
# Revisar el archivo generado en migrations/versions antes de aplicarlo.
.\enviroment\Scripts\python.exe -m alembic upgrade head
```

Cada archivo nuevo de modelos se importa en `app/models/__init__.py`.

## Configuración

| Variable | Para qué | Default | Cuándo cambiarla |
| --- | --- | --- | --- |
| `PROJECT_NAME` | Título en `/docs` | `Libro mayor` | Opcional |
| `SERVICE_NAME` / `SERVICE_VERSION` | Identifican al servicio en `audit.logs` | `libro-mayor` / `0.1.0` | Versión: en cada despliegue |
| `AUDIT_ENABLED` | Activa los logs de solicitudes | `true` | `false` para pruebas sin schema `audit` |
| `AUDIT_MAX_BODY_BYTES` | Máximo de body guardado por solicitud | `4096` | Rara vez |
| `DB_ENGINE` | Motor de la base local | `postgresql` | `mssql` solo cuando se valide |
| `DB_HOST` / `DB_PORT` | Servidor de la base local | `localhost` / `5432` | Docker o nube |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | Base y credenciales | Obligatorias | Siempre |
| `AUTH_URL` | URL interna de auth, sin `/auth` | Obligatoria | Por entorno (`http://auth:8000` en el Compose) |
| `AUTH_TIMEOUT_SECONDS` | Espera máxima por llamada a auth | `30` | Si auth está lejos o lento |
| `CORS_ORIGINS` | Orígenes web (lista JSON) | `[]` | Si un front llama directo, sin central |
| `TRUSTED_PROXIES` | IPs/CIDR de la central o balanceador | `[]` | Al ponerlo detrás de la central |
| `SAP_HOST` / `SAP_PORT` | Servidor HANA | vacío (SAP deshabilitado) / `30015` | Para consultar o sincronizar SAP |
| `SAP_USER` / `SAP_PASSWORD` | Usuario HANA solo con SELECT sobre las vistas | vacío | Obligatorios si hay `SAP_HOST` |
| `SAP_ENCRYPT` / `SAP_VALIDATE_CERTIFICATE` | TLS hacia HANA | `true` / `true` | `false` solo si el servidor no admite TLS (tráfico sin cifrar) |
| `SAP_CONNECT_TIMEOUT_SECONDS` | Espera para abrir la conexión | `30` | Red lenta |
| `SAP_QUERY_TIMEOUT_SECONDS` | Máximo por consulta | `300` | Cargas grandes (p. ej. cuentas 70) |
| `SYNC_MAX_DAYS` | Máximo de días por ejecución manual | `366` | Si se necesitan rangos más largos |
| `SYNC_RETRIES` / `SYNC_RETRY_SECONDS` | Reintentos por tramo si SAP o la red fallan, y espera inicial (luego ×4) | `2` / `30` | `0` = sin reintentos |
| `SYNC_POLL_SECONDS` | Cada cuánto el worker busca pendientes | `10` | Rara vez |
| `SYNC_STALE_MINUTES` | Sin avance en este tiempo = interrumpida | `30` | Si un día de una cuenta tarda más (p. ej. ventas 70) |
| `SYNC_SCHEDULE` | Turnos diarios del worker (`HH:MM,…` en `SAP_TIMEZONE`) | `06:00,10:00,14:00,18:00` (por confirmar) | Cambiar horas; `off` = sin horario |
| `SAP_TIMEZONE` | Zona horaria del servidor SAP: define "hoy" en SAP y el horario | `America/Lima` (por confirmar) | Si SAP corre en otra zona |
| `CLASSIFY_BATCH_SIZE` | Líneas por lote al reclasificar | `2000` | Volúmenes grandes |
| `LIVE_QUERY_MAX_DAYS` / `LIVE_QUERY_MAX_ACCOUNTS` | Límites de una consulta en vivo | `366` / `20` | Según la carga que tolere SAP |
| `LIVE_QUERY_PARALLEL` | Consultas a SAP a la vez en el proceso, entre todas las solicitudes | `4` | Subir si SAP lo tolera; es el freno de carga |
| `LIVE_QUERY_MAX_LINES` | Máximo de líneas con `view=full` | `100000` | Según la memoria del contenedor |
| `LIVE_QUERY_TIMEOUT_SECONDS` | Tiempo máximo de una consulta en vivo | `120` | Rangos grandes; si pasa de 120, subir también el de la ruta en la central (`public_routes.py`, 130 s) |
| `SEED_ENABLED` | Habilita `POST /admin/seed` | `false` | Solo para ejecutar el seed |

## Documentación

- [Guía de configuración y uso, con ejemplos JSON](docs/guia-configuracion.md)
- [Instrucciones del servicio](AGENTS.md)
- [Requisitos y alcance](docs/requisitos.md)
- [Modelo de datos](docs/modelo-datos.md)
- [Referencia: implementación previa en proyecto-05](docs/referencia-proyecto-05.md)
- [Guía de configuración y uso](docs/guia-configuracion.md)
- [Integración con la central](docs/integracion-central.md)

## Dependencias con otros servicios

- auth: identidad, empresa activa y permisos con alcance.
- API central: publicado (2026-09-30), apagado por defecto
  (`LIBRO_MAYOR_ENABLED`). Rutas, contenedores y cómo activarlo:
  [integración con la central](docs/integracion-central.md).
- SAP HANA: origen de datos de solo lectura, fuera de la plataforma
  (`hdbcli` + `sqlalchemy-hana`). `tzdata` aporta la base de zonas horarias
  (Windows y la imagen slim no traen una del sistema).
