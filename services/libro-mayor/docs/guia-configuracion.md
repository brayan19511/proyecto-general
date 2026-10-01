# Guía de configuración y uso (con ejemplos)

Flujo para dejar una empresa lista: conectar SAP, registrar cuentas, armar
categorías y reglas, clasificar y consultar. Todas las rutas van bajo
`/libro-mayor` y, salvo los logs, llevan estos headers:

```http
Authorization: Bearer <access_token de POST /auth/login>
X-Company-Id: <id de la empresa en auth>
Content-Type: application/json
```

O, para integraciones que no pueden renovar un token (Excel, Power BI), una
API key creada por el usuario en auth, sin `X-Company-Id` (la empresa es la de
la clave):

```http
X-API-Key: <clave>
```

Los ids (`<id …>`) los devuelve cada alta. Los importes viajan como texto
(`"1500.00"`) para no perder decimales.

Nombres de la clasificación (como en proyecto-05): **`codigo`** = categoría
(p. ej. `OPERACIONES GV08`), **`subcodigo`** = subcategoría (p. ej.
`DIFERENCIA EN UNIDADES DE COSTEO`), **`nombre_cuenta`** = nombre con que se
muestra la línea en reportes.

## Resumen del flujo

| Paso | Qué | Ruta | Quién |
| --- | --- | --- | --- |
| 1 | Compañía SAP de la empresa | `POST /admin/sap-company` (o el seed) | Admin de plataforma |
| 2 | Cuentas a sincronizar | `POST /accounts` | `ledger.admin` |
| 3 | Categorías (`codigo`) y subcategorías (`subcodigo`) | `POST /categories` | `ledger.update` |
| 4 | Reglas de gasto (una a una o carga masiva) | `POST /rules` o `POST /rules/import` | `ledger.update` |
| 5 | Traer datos de SAP | Horario del worker, o `POST /sync-runs` | `ledger.admin` (manual) |
| 6 | Clasificar lo ya traído | `POST /classification-runs` | `ledger.update` |
| 7 | Consultar en vivo | `POST /live-queries` | `ledger.view` |
| 8 | Consultar lo sincronizado (reportes, Excel, Power BI) | `GET /ledger/lines`, `/ledger/lines.csv`, `/ledger/summary` | `ledger.view` |
| 9 | Homologar centros de costo a áreas (para usuarios de área) | `POST /cost-center-mappings` o `/cost-center-mappings/import` | `ledger.admin` |

Permisos: `ledger.view` (ver y consultar), `ledger.update` (además modificar
reglas y categorías) y `ledger.admin` (además cuentas y sincronización manual).
Cada uno incluye al anterior. Todas las rutas GET piden `ledger.view`.

Los pasos 3 y 4 no dependen de 1, 2 y 5: se pueden armar reglas antes o
después de sincronizar. La carga masiva (4) crea las categorías que falten,
así que el paso 3 solo hace falta para altas sueltas. Las consultas en vivo
(7) solo necesitan el paso 1 y, para ver la clasificación, el 4.

## 1. Compañía SAP

```http
POST /libro-mayor/admin/sap-company
```
```json
{
  "sap_schema": "SBO_RASH_PRODUCCION",
  "source_view": "VW_LIBRO_MAYOR_PERSONALIZADO_2",
  "sync_start_date": "2026-01-01"
}
```

- Una por empresa. `sync_start_date`: desde qué fecha contable se carga una
  cuenta la primera vez.
- Cambiar después: `PATCH /admin/sap-company` con solo lo que cambia, p. ej.
  `{"sync_start_date": "2026-06-01"}`. `sap_schema` no se cambia si ya hay
  líneas sincronizadas.
- Alternativa: `POST /admin/seed` (con `SEED_ENABLED=true`) carga compañía y
  cuentas de `app/seeds/data.py`.

## 2. Cuentas a sincronizar

```http
POST /libro-mayor/accounts
```
```json
{"code": "95", "match_mode": "prefix", "name": "GASTOS 95"}
```
```json
{"code": "701110002", "match_mode": "exact", "name": "VENTAS POWERZONE"}
```

- `prefix` = todas las que empiezan por el código; `exact` = esa cuenta.
- No se permiten superposiciones: con `95` (prefix) activo, `959005993`
  (exact) responde 409.
- Listar: `GET /accounts`. Renombrar: `PATCH /accounts/{id}` con
  `{"name": "…"}`. Baja: `DELETE /accounts/{id}`.

Solo hace falta para sincronizar (guardar líneas). Las consultas en vivo
aceptan cualquier cuenta, registrada o no.

## 3. Categorías (`codigo`) y subcategorías (`subcodigo`)

Se identifican **por nombre** (acuerdo, como en proyecto-05). Primero la
categoría:

```http
POST /libro-mayor/categories
```
```json
{"name": "OPERACIONES GV08"}
```

Respuesta (resumida): `{"id": "<id OPERACIONES GV08>", "parent_id": null, "name": "OPERACIONES GV08", …}`.

Luego sus subcategorías, con `parent_id`:

```json
{"name": "DIFERENCIA EN UNIDADES DE COSTEO", "parent_id": "<id OPERACIONES GV08>"}
```

- El nombre es único entre las activas del mismo nivel (sin distinguir
  mayúsculas): una categoría, entre las categorías de la empresa; una
  subcategoría, dentro de su categoría. La misma subcategoría ("GASTOS
  DIVERSOS") puede existir bajo categorías distintas.
- No hay tercer nivel (422).
- Renombrar: `PATCH /categories/{id}` con `{"name": "…"}`: no hace falta
  reclasificar. Baja: `DELETE /categories/{id}` (409 si tiene subcategorías o
  reglas activas).

## 4. Reglas de gasto (`expense_rules`)

Una regla dice: "si una línea cumple estas condiciones, va a esta categoría".

```http
POST /libro-mayor/rules
```

| Campo | Para qué |
| --- | --- |
| `priority` | Obligatorio. Menor = se evalúa antes. **Gana la primera que cumple** |
| `category_id` | Obligatorio. Categoría o subcategoría de destino (su id) |
| `account_code` | Condición: cuenta SAP exacta (`959005993`) |
| `counter_account_code` | Condición: contrapartida exacta |
| `cost_center_code` | Condición: centro de costo exacto (`A0202001`) |
| `include_text` | Condición: este texto debe aparecer (sin distinguir mayúsculas) en proveedor, descripción o referencias 1–3 |
| `exclude_text` | Condición: este texto NO debe aparecer |
| `amount_min` / `amount_max` | Condición: importe en moneda local **con signo** |
| `nombre_cuenta` | Opcional. Nombre con que se muestra la línea en reportes (ver abajo) |

Condición vacía = no filtra. Todas las condiciones llenas deben cumplirse. Al
menos una condición es obligatoria.

Ejemplos, de lo más específico (prioridad baja) a lo más general:

Texto (p. ej. un proveedor, en esa cuenta):
```json
{"priority": 1, "category_id": "<id GASTOS EXTRAORDINARIOS GV11 > GASTOS EXTRAORDINARIOS>",
 "account_code": "959008690", "include_text": "PROVISIONES GESTION HUMANA", "amount_min": "5000",
 "nombre_cuenta": "PROVISIONES DIVERSAS"}
```

Cuenta + centro de costo:
```json
{"priority": 2, "category_id": "<id OTROS GASTOS E-COMMERCE GV09 > GASTOS DIVERSOS>",
 "account_code": "959005998", "cost_center_code": "A0202001", "nombre_cuenta": "GASTOS DIVERSOS"}
```

Cuenta + contrapartida:
```json
{"priority": 20, "category_id": "<id OPERACIONES GV08 > DIFERENCIA EN UNIDADES DE COSTEO>",
 "account_code": "959005993", "counter_account_code": "201110000", "nombre_cuenta": "DIFERENCIA DE INVENTARIO"}
```

Solo cuenta (lo que quede de esa cuenta):
```json
{"priority": 100, "category_id": "<id OPERACIONES GV08 > DIFERENCIA EN UNIDADES DE COSTEO>",
 "account_code": "959005991", "nombre_cuenta": "DIFERENCIA POR REDONDEO"}
```

Consejos:
- Numerar prioridades con espacio (1, 2, 5, 10…) deja lugar para intercalar.
- Reglas específicas (varias condiciones o texto) con prioridad menor que las
  generales (solo cuenta); si no, la general gana antes.
- Texto como aparece en SAP, incluso con caracteres dañados (`Nota Cr�dito`).

Editar: `PATCH /rules/{id}` con solo lo que cambia, p. ej. `{"priority": 5}`.
Para quitar una condición, enviarla en `null`: `{"exclude_text": null}`.
`priority` y `category_id` no admiten `null`. Baja: `DELETE /rules/{id}`.
Listar en orden de evaluación: `GET /rules`.

Cada alta, edición o baja **reclasifica sola** las líneas afectadas
(la hace el worker, segundos después). Seguimiento: `GET /classification-runs`.

### Carga masiva (`POST /rules/import`)

Para cargar muchas reglas de una vez (p. ej. las de proyecto-05). Usa los
nombres de proyecto-05: `codigo` y `subcodigo` por nombre (si no existen, se
crean) y `nombre_cuenta`.

```http
POST /libro-mayor/rules/import
```
```json
{
  "mode": "replace",
  "dry_run": true,
  "rules": [
    {"priority": 10, "codigo": "OPERACIONES GV08", "subcodigo": "DIFERENCIA EN UNIDADES DE COSTEO",
     "account_code": "959005993", "nombre_cuenta": "DIFERENCIA DE INVENTARIO"},
    {"priority": 1, "codigo": "CORPORATIVO", "subcodigo": "GASTOS DIVERSOS",
     "account_code": "959005998", "cost_center_code": "A0000001", "nombre_cuenta": "GASTOS DIVERSOS"},
    {"priority": 1, "codigo": "GASTOS EXTRAORDINARIOS GV11", "subcodigo": "GASTOS EXTRAORDINARIOS",
     "account_code": "959008690", "include_text": "PROVISIONES GESTION HUMANA", "amount_min": "5000",
     "nombre_cuenta": "PROVISIONES DIVERSAS"}
  ]
}
```

| Campo | Valores |
| --- | --- |
| `mode` | `append` (default): solo agrega. `replace`: da de baja todas las reglas activas y crea estas (el `DELETE` + `INSERT` de proyecto-05, sin borrar filas) |
| `dry_run` | `true`: valida y muestra qué pasaría **sin guardar nada**. Usarlo siempre primero |
| `rules[]` | Mismas condiciones que `POST /rules`, con `codigo`/`subcodigo` por nombre en lugar de `category_id` |

- **Todo o nada:** si una fila no es válida, responde 422 con el número de
  fila y no guarda nada.
- **Categorías:** se busca una activa con ese nombre en su nivel (sin
  distinguir mayúsculas); si no existe, se crea.
- **Avisos** (no impiden importar): categorías que parecen la misma
  (`OPERACIONES` y `OPERACIONES GV08`), nombres que solo difieren en espacios,
  reglas repetidas.
- Al final registra **una** reclasificación de todas las líneas.

Respuesta (resumida):
```json
{"mode": "replace", "dry_run": true, "rules_created": 225, "rules_deactivated": 0,
 "categories_created": [{"name": "OPERACIONES GV08", "parent": null},
                        {"name": "DIFERENCIA EN UNIDADES DE COSTEO", "parent": "OPERACIONES GV08"}],
 "warnings": ["Categorías que parecen la misma (difieren en el código GV): OPERACIONES / OPERACIONES GV08"],
 "classification_run_id": null}
```

**Desde el SQL de proyecto-05:** `scripts/convert_legacy_rules.py` lee un
`INSERT INTO finance.reglas_gastos (…) VALUES …` y escribe el JSON (con
`mode: replace` y `dry_run: true`). No se conecta a ninguna base.

```powershell
.\enviroment\Scripts\python.exe scripts/convert_legacy_rules.py reglas.sql reglas.json
```

Las 225 reglas de RASH Perú ya convertidas: `data/import/reglas_rash_peru.json`.
Enviarlo tal cual (dry run), revisar `warnings` y `categories_created`, y
repetirlo con `"dry_run": false`.

### ¿Para qué es `nombre_cuenta`?

Es el `nombre_cuenta` de proyecto-05. `codigo` y `subcodigo` agrupan;
`nombre_cuenta` es la etiqueta de la línea. En el Excel de septiembre 2026,
líneas con el mismo `codigo` (OPERACIONES GV08) y `subcodigo` (DIFERENCIA EN
UNIDADES DE COSTEO) se muestran como "DIFERENCIA POR REDONDEO" o "DIFERENCIA
DE INVENTARIO". Es opcional: sin él, la línea muestra el nombre de la cuenta
SAP.

## 5. Traer datos de SAP (sincronización)

### Cómo funciona

Todo va **por cuenta registrada**. En cada turno de `SYNC_SCHEDULE` (default
06:00, 10:00, 14:00, 18:00) el worker (`python -m app.worker`) crea una
ejecución por cada cuenta activa y las procesa (varias en paralelo si corren
varios workers):

| Tipo | Cuándo | Qué consulta a SAP |
| --- | --- | --- |
| `initial` | La cuenta nunca completó una carga | **Por mes**, desde `sync_start_date` hasta hoy (un año = 12 consultas); cada mes se guarda con su avance |
| `delta` | Las siguientes veces | Una consulta: todo lo creado o modificado en SAP desde la última carga correcta (de cualquier fecha contable) |
| `sync` | A mano (`POST /sync-runs`) | Por mes, el rango pedido |

- Cada línea se **clasifica al guardarse** con las reglas vigentes. Al
  consultar lo guardado no se evalúan reglas: se lee la regla guardada.
- Repetir no duplica: la línea se identifica por su clave SAP (transacción +
  línea); si SAP la cambió, se actualiza.
- **Cuenta nueva**: en el siguiente turno se detecta que nunca se cargó y se
  hace su `initial`; luego sigue con deltas. Para no esperar al turno, lanzar
  un `sync` manual.
- Un fallo deja la ejecución `failed` con hasta dónde llegó; el siguiente
  turno lo reintenta.

### Si SAP o internet se caen

1. **Reintentos dentro del mismo turno:** si una consulta a SAP falla por
   conexión, se reintenta 2 veces (espera 30 s y luego 2 min; `SYNC_RETRIES`,
   `SYNC_RETRY_SECONDS`). Un corte corto no hace fallar el turno.
2. **Si sigue fallando:** la ejecución queda `failed` con un mensaje seguro
   (p. ej. `Error de base de datos o de SAP (Error, código -10709)`). La marca
   de agua **no avanza**.
3. **Recuperación automática:** el siguiente turno pide desde la misma marca
   de agua y trae todo lo que faltó, aunque SAP haya estado caído un día
   entero. No se pierden cambios ni se duplican líneas.
4. **Vigilarlo:** `GET /libro-mayor/sync-status` → por cuenta:
   `last_success_at`, `hours_since_success`, `consecutive_failures` y
   `last_error`. Con el horario por defecto, un día de SAP caído son 4 fallos
   seguidos; vuelve a 0 con la primera carga correcta.

```json
[{"code": "95", "match_mode": "prefix", "watermark": "2026-09-29",
  "last_success_at": "2026-09-29T15:00:12Z", "hours_since_success": 26.5,
  "consecutive_failures": 4, "last_run_status": "failed",
  "last_error": "Error de base de datos o de SAP (Error, código -10709)."}]
```

### Sincronización manual

```http
POST /libro-mayor/sync-runs
```
```json
{"account_id": "<id cuenta>", "date_from": "2026-09-01", "date_to": "2026-09-30"}
```

Responde 202 (la hace el worker). Avance: `GET /sync-runs/{id}` →
`status`, `days_done`/`days_total`, `rows_inserted`, `rows_updated`.

## 6. Clasificar lo ya sincronizado

Las líneas nuevas se clasifican al sincronizarse y los cambios de reglas
reclasifican solos. Lo traído antes de tener reglas queda sin clasificar hasta
reclasificar una vez (la carga masiva ya lo hace al final):

```http
POST /libro-mayor/classification-runs
```
```json
{}
```
Todas las líneas de la empresa. O un rango contable:
```json
{"date_from": "2026-01-01", "date_to": "2026-03-31"}
```

Responde 202. Avance: `GET /classification-runs/{id}` → `rows_checked`,
`rows_changed`.

## 7. Consulta en vivo

Consulta SAP en el momento, clasifica y devuelve la respuesta en la misma
llamada. No guarda nada.

```http
POST /libro-mayor/live-queries
```
```json
{
  "accounts": ["95*", "97*", "701110002"],
  "date_from": "2026-01-01",
  "date_to": "2026-09-30",
  "split": "month"
}
```

| Campo | Valores |
| --- | --- |
| `accounts` | `"95*"` = empiezan por 95; `"701110002"` = exacta |
| `split` | `month` (default) o `day`: tramos consultados a SAP en paralelo |
| `view` | `lines` (default: solo líneas), `summary` (solo resumen, liviano) o `full` (ambos) |

Respuesta (sin `view`, o sea solo líneas; resumida):

```json
{
  "accounts": ["95*", "97*", "701110002"],
  "split": "month", "chunks": 9, "lines_total": 2343, "elapsed_ms": 1840,
  "summary": null,
  "lines": [
    {
      "posting_date": "2026-09-01", "sap_transaction_id": 74959701, "sap_line": 1,
      "account_code": "959005993", "account_name": "DIFERENCIA DE INVENTARIO",
      "supplier": "DIFERENCIA DE INVENTARIO", "description": "Goods Issue",
      "amount_local": "459.3435", "amount_foreign": "0.0000",
      "cost_center_code": null,
      "rule_id": "<id regla>",
      "codigo": "OPERACIONES GV08",
      "subcodigo": "DIFERENCIA EN UNIDADES DE COSTEO",
      "nombre_cuenta": "DIFERENCIA DE INVENTARIO"
    }
  ]
}
```

Con `view: "summary"`, `lines` es `null` y `summary` trae una fila por año,
mes, `codigo` y `subcodigo`:

```json
{"year": 2026, "month": 9, "codigo": "OPERACIONES GV08", "subcodigo": "DIFERENCIA EN UNIDADES DE COSTEO",
 "lines": 1486, "amount_local": "152340.1200", "amount_foreign": "0.0000"}
```

`codigo: null` = sin clasificar. Límites: 366 días, 20 cuentas, 100 000
líneas con `lines`/`full` (más: 422, usar `summary`), 120 s (504).

## 8. Consultar lo sincronizado (reportes, Excel, Power BI)

Lee la copia local ya clasificada (`ledger_lines`), no SAP: es mucho más
rápido (un año de resumen en milisegundos). Solo GET y parámetros en la URL.

| Ruta | Devuelve |
| --- | --- |
| `GET /ledger/lines` | JSON paginado: `total`, `limit` (hasta 5000), `offset`, `next_offset` (null = no hay más), `lines` |
| `GET /ledger/lines.csv` | **Todo** el filtro en CSV, en streaming (sin páginas), para Excel / Power BI |
| `GET /ledger/summary` | Por año, mes, `codigo` y `subcodigo` (y `supplier` con `by_supplier=true`): cantidad e importes |

Parámetros (iguales en las tres):

| Parámetro | Ejemplo | |
| --- | --- | --- |
| `date_from`, `date_to` | `2026-01-01`, `2026-09-30` | Obligatorios; fecha contable |
| `accounts` | `95*,701110002` | Opcional; `*` = prefijo |
| `codigo`, `subcodigo` | `OPERACIONES GV08` | Opcional; por nombre, sin distinguir mayúsculas |
| `cost_center_code` | `A0202001` | Opcional |
| `unclassified` | `true` / `false` | Opcional; solo sin regla / solo clasificadas |
| `no_subcodigo` | `true` | Opcional; solo clasificadas en una categoría principal (sin subcategoría). No se combina con `subcodigo` |
| `supplier` | `LUZ DEL SUR S.A.A.` | Opcional; proveedor exacto, tal como viene de SAP |
| `no_supplier` | `true` | Opcional; solo líneas sin proveedor (NULL o vacío en SAP). No se combina con `supplier` |
| `by_supplier` (solo summary) | `true` | Agrupa también por proveedor: cada fila trae `supplier` (null = sin proveedor). Sin él, la respuesta no cambia |
| `sep` (solo CSV) | `;` | `,` por defecto; `;` para Excel en español |
| `limit`, `offset` (solo JSON) | `1000`, `0` | Página |

```http
GET /libro-mayor/ledger/lines?date_from=2026-01-01&date_to=2026-09-30&accounts=95*,97*&limit=1000
GET /libro-mayor/ledger/summary?date_from=2026-01-01&date_to=2026-09-30&codigo=OPERACIONES%20GV08
GET /libro-mayor/ledger/lines.csv?date_from=2026-01-01&date_to=2026-09-30&sep=;
```

### Tabla con detalle al hacer clic (tablix, drill down)

- **App web o reporte que llama a la API:** la tabla de meses sale de
  `GET /ledger/summary` (una fila por año, mes, `codigo`, `subcodigo`). Al hacer
  clic en una celda se pide solo ese detalle, p. ej.
  `GET /ledger/lines?date_from=2026-03-01&date_to=2026-03-31&codigo=OPERACIONES%20GV08&subcodigo=GASTOS%20DIVERSOS&limit=1000`,
  y se pagina con `offset=next_offset` si hay más.
- **Tercer nivel por proveedor:** `GET /ledger/summary?...&by_supplier=true`
  trae una fila por año, mes, `codigo`, `subcodigo` y `supplier`. El detalle de
  un proveedor agrega `supplier=<nombre>`; los nodos "sin asignar" usan
  `no_subcodigo=true`, `no_supplier=true` o `unclassified=true` (sin regla),
  así ninguna línea queda fuera ni se mezcla con otra rama.
- **Power BI:** importar una vez `lines.csv` del rango (ver abajo); la matriz,
  el resumen por mes y el "obtener detalles" al hacer clic los resuelve Power BI
  con los datos ya cargados, sin volver a llamar a la API.

### Compresión (gzip)

Automática: el navegador, Excel, Power BI y Postman envían `Accept-Encoding:
gzip`; el servicio comprime las respuestas de más de 1 KB y el cliente las
descomprime solo. No hay nada que configurar; el CSV o el JSON viaja unas 10
veces más liviano.

### Excel ("Obtener datos → Desde la web")

1. Crear una API key en auth (`POST /auth/api-keys`, con alcance que incluya
   `ledger.view`) y guardarla: se muestra una sola vez. El usuario debe tener
   `ledger.view` por su puesto: la clave no da más permisos que los suyos.
2. En Excel: **Datos → Obtener datos → Desde otras fuentes → Desde la web →
   Avanzado**.
3. Partes de la URL: `http://<servidor>/libro-mayor/ledger/lines.csv?date_from=2026-01-01&date_to=2026-09-30&sep=;`
4. Parámetro de encabezado de la solicitud HTTP: `X-API-Key` = `<clave>`.
5. Acceso: **Anónimo** (la clave va en el encabezado).
6. Power Query detecta el CSV: revisar tipos (fecha, número con `.` decimal:
   en "Cambiar tipo → Usar configuración regional" elegir Inglés (EE. UU.)
   para los importes). **Actualizar** vuelve a pedir el rango completo.

No hace falta paginar: el CSV trae todo el filtro. La paginación (`/lines`) es
para aplicaciones web.

### Power BI (Power Query M)

```powerquery
let
    Origen = Csv.Document(
        Web.Contents(
            "http://<servidor>/libro-mayor/ledger/lines.csv",
            [
                Query = [date_from = "2026-01-01", date_to = "2026-09-30", accounts = "95*,97*"],
                Headers = [#"X-API-Key" = "<clave>"]
            ]
        ),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    Tipos = Table.TransformColumnTypes(Encabezados, {
        {"posting_date", type date}, {"amount_local", type number}, {"amount_foreign", type number}
    }, "en-US")
in
    Tipos
```

Separar la URL base de `Query` permite que Power BI Service actualice el
reporte programado. Una API key no vence por tiempo (salvo que se le ponga
fecha), pero deja de funcionar si se revoca o el usuario pierde el permiso.

## 9. Homologar centros de costo a áreas

Solo hace falta para usuarios con `ledger.view` de alcance `area`: un
contador master (alcance `company`) ve todo aunque no haya homologaciones.

| Usuario | Permiso en auth | Ve |
| --- | --- | --- |
| Contador master | `ledger.view` alcance `company` | Todo |
| Vendedor o contador asignado a ventas | `ledger.view` alcance `area`, área VENTAS | Solo VENTAS |
| Usuario con puestos en VENTAS y ADMINISTRACION | `ledger.view` alcance `area`, ambas | Solo esas dos |

1. En auth: las áreas (`GET /auth/areas`) y los puestos de cada usuario ya
   definen qué áreas tiene. El rol del puesto lleva `ledger.view`.
2. Ver qué centros faltan homologar (lo que ya se sincronizó):

```http
GET /libro-mayor/cost-centers?unmapped=true
```

```json
[
  {"cost_center_code": "V1141177", "sap_name": "T65 REAL PLAZA PURUCHUCO I", "lines": 12,
   "last_posting_date": "2026-09-29", "area_id": null, "area_name": null},
  {"cost_center_code": null, "sap_name": null, "lines": 450, "last_posting_date": "2026-09-29",
   "area_id": null, "area_name": null}
]
```

   La fila `null` son las líneas sin centro de costo: solo las ve el master.

3. Homologar uno (por código del área en auth, sin distinguir mayúsculas, o por
   `area_id`). Igual que las cuentas, `match_mode` es `exact` (por defecto, el
   código completo) o `prefix` (todo centro que empiece así):

```http
POST /libro-mayor/cost-center-mappings
{"cost_center_code": "V114", "match_mode": "prefix", "area_code": "VENTAS"}
```

```http
POST /libro-mayor/cost-center-mappings
{"cost_center_code": "V1141061", "area_code": "ADMIN"}
```

   Si varias coinciden gana la exacta y, entre prefijos, el más largo. En el
   ejemplo todas las tiendas `V114…` son de VENTAS salvo `V1141061`, que es de
   ADMIN. `GET /cost-centers` muestra para cada centro qué homologación le
   aplicó (`match_mode`, `mapping_code`).

4. O todos juntos (una transacción: si una fila falla, no se guarda nada y el
   error dice cuál). Probar primero con `dry_run: true`:

```http
POST /libro-mayor/cost-center-mappings/import
{
  "mode": "append",
  "dry_run": true,
  "mappings": [
    {"cost_center_code": "V", "match_mode": "prefix", "area_code": "VENTAS"},
    {"cost_center_code": "V1140001", "area_code": "ADMIN"},
    {"cost_center_code": "A0404000", "area_code": "VENTAS"},
    {"cost_center_code": "A0106000", "area_code": "ADMIN"},
    {"cost_center_code": "A0110003", "area_code": "LOG"}
  ]
}
```

```json
{"mode": "append", "dry_run": true, "created": 5, "updated": 0, "unchanged": 0, "deactivated": 0}
```

   La clave de cada fila es código + `match_mode`: `V114` exacto y `V114`
   prefijo son filas distintas; repetir la misma clave es 422.

   RASH Perú: propuesta armada desde la tabla `#TMP_REPARTO` del SP antiguo
   (332 centros con 29 homologaciones) en
   `data/import/homologacion_rash_peru.json` (`replace`, `dry_run: true`), con
   la planilla `homologacion_rash_peru_revision.csv` (centro, nombre SAP, área
   resultante y columna `revisar`). Antes de cargarla deben existir en auth las
   áreas que usa (`POST /auth/areas`); si no, responde 422 indicando la fila.

   `append` agrega y mueve de área los que cambian; `replace` además da de baja
   las homologaciones activas que no vengan en la lista (la lista pasa a ser el
   mapa completo). Máximo 5000 filas.

5. Mover un centro o prefijo a otra área: `PATCH /cost-center-mappings/{id}`
   con `{"area_code": "ADMIN"}`. Código y modo no se editan: `DELETE` (baja
   lógica) y alta nueva. Rige en la consulta siguiente, sin reprocesar.

Las líneas devueltas por `/ledger/*` y `/live-queries` traen `area_id` y
`area_name`. Un filtro `cost_center_code` de otra área no amplía lo visible:
devuelve 0 líneas.

## Errores frecuentes

| Respuesta | Causa típica |
| --- | --- |
| 401 | Token vencido o ausente: volver a `POST /auth/login` |
| 403 "No tienes acceso a esta empresa" | `X-Company-Id` de otra empresa |
| 403 "No tienes permiso" | Falta el nivel: ver = `ledger.view`, modificar reglas = `ledger.update`, cuentas y sincronización manual = `ledger.admin` (una API key, solo lo que sus scopes permitan) |
| 409 "no tiene compañía SAP" | Falta el paso 1 |
| 409 "se superpone" | Cuenta cubierta por otra activa (paso 2) |
| 409 "ya está homologado" | Ese código con ese `match_mode` ya tiene área: PATCH para moverlo (paso 9) |
| 422 "área … no existe" | `area_code` que no está activo en auth para esa empresa (paso 9) |
| Usuario de área recibe 0 líneas | Sus áreas no tienen centros homologados (paso 9) o sus puestos en auth no tienen esas áreas |
| 409 "Ya existe una categoría activa con ese nombre" | Nombre repetido en el mismo nivel |
| 422 | Dato inválido o campo no permitido (el body no acepta campos extra; p. ej. `report_name` o `category` se llaman `nombre_cuenta` y `codigo`) |
| 502 "…código -10709" | No conecta a SAP: host/puerto/VPN o `SAP_ENCRYPT` (ver readme) |
| 502 "auth no está disponible" | `AUTH_URL` mal (sin `/auth` al final) o auth caído |
