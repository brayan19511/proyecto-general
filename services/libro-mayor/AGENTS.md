# Libro mayor y gastos

Lee las instrucciones raíz (`AGENTS.md`), `docs/arquitectura.md` y, de este
servicio, `docs/requisitos.md`, `docs/modelo-datos.md` y
`docs/referencia-proyecto-05.md` antes de proponer o revisar cambios.

## Estado

Base técnica copiada de `services/base-fastapi` (config, conexión PostgreSQL,
audit, `/libro-mayor/health` y `/ready`, Dockerfile) y Alembic limitado al
schema `libro_mayor` (acuerdo), con versión en `libro_mayor.alembic_version`.
Modelos: `Actor` + `AuditMixin`, `SapCompany`, `Account` y `ChangeHistory`.
CRUD de compañía SAP y cuentas, logs, seed (`SEED_ENABLED`) y sincronización
manual (`POST /sync-runs`) y programada con delta (worker `python -m app.worker`,
fases A, B y C);
identidad vía auth (`app/api/dependencies.py`). Conexión HANA de solo lectura
y lector de la vista en `app/sap/`. Pendiente de probar contra HANA real
(`scripts/check_sap.py`). Categorías, reglas, motor (`classifier.py`),
reclasificación y consultas en vivo en una llamada (`live_query_service.py`). Sin
centros de costo/homologación, filtro por áreas ni consultas sobre
`ledger_lines`.
Ver readme.md.

Convenciones del código existente (seguirlas):
- Servicios en `app/services/`: abren su transacción (`with db.begin()`),
  registran el actor (`user_actor_id`) y el historial (`record_change`) dentro
  de ella, y lanzan errores de `app/services/errors.py`; nunca `HTTPException`.
  `main.py` los traduce a HTTP.
- Rutas en `app/api/routes/`: solo dependencias de permiso, schema y llamada al
  servicio. La empresa sale de `ctx.company_id` (validada por auth).
- Unicidad "activa" con `unique_active()` (índice filtrado). Validaciones que
  la base no expresa de forma portable (superposición de cuentas) van en el
  servicio, serializadas bloqueando la fila de `sap_companies` de la empresa.
- Pasos de logs con `step("recurso.accion")` en operaciones que cambian datos.
- Todo SQL hacia SAP vive en `app/sap/` (acuerdo: lector SAP aparte; sin capa
  de repositorios para las tablas propias). Columnas explícitas
  (`SAP_COLUMNS`), identificadores validados con `validate_identifier` y
  valores como parámetros. Nunca escribir en SAP ni interpolar valores.
- Trabajo pesado solo en el worker: una ruta HTTP registra la ejecución
  (`sync_runs`, 202) y nunca consulta SAP. Única excepción (decisión del
  usuario, 2026-09-30): `POST /live-queries` consulta SAP en la misma solicitud,
  por tramos en un pool de hilos compartido (`LIVE_QUERY_PARALLEL`), con tope
  de líneas y de tiempo, y sin guardar resultados. El worker guarda cada día (datos +
  avance) en una transacción y registra solo mensajes seguros (tipo y código
  del error, nunca el texto crudo).
- Clasificación: una sola función (`classifier.classify`) para sync,
  reclasificación y consultas en vivo. Cambiar una regla nunca reclasifica en
  el HTTP: registra un `classification_runs` en la misma transacción.
- Filas que el worker vuelve a leer con bloqueo: `db.get(..., with_for_update=True,
  populate_existing=True)`. Sin `populate_existing`, SQLAlchemy devuelve el
  objeto en memoria sin releer ni bloquear (se perdían sumas con 2 workers).
- Marca de agua = `date_to` del último `initial`/`delta` correcto; nunca la
  mueve un `sync` manual. El delta relee desde ese día inclusive (el upsert
  hace segura la repetición). No leer la marca de agua de las líneas locales.
- Campos que definen el origen de datos ya sincronizados (`code`/`match_mode`
  de una cuenta, `sap_schema` de la compañía) no se editan si hay líneas:
  baja y alta. El resto se edita con PATCH (solo campos enviados + historial).
- Seed (acuerdo: ruta como auth): `app/seeds/data.py` por código de empresa;
  reutiliza `add_sap_company`/`add_account` en una transacción; no reactiva
  bajas ni modifica lo existente. Python 3.14 (uuid7). No declarar otro
`Base`; los modelos heredan el schema de `app/models/entities.py`. Ver readme.md. El usuario escribe el código;
el asistente guía un paso pequeño por vez según el AGENTS.md raíz. No crear
automáticamente modelos, migraciones, rutas, jobs ni dependencias.
No copiar `models/` ni `migrations_example/` de la plantilla: son de auth.

## Qué hace

1. Sincroniza desde SAP Business One sobre HANA (solo lectura) las líneas del
   libro mayor de las cuentas registradas, por empresa.
2. Clasifica cada línea como gasto aplicando reglas por prioridad.
3. Permite consultar, resumir y exportar gastos limitados al alcance del usuario
   (sus áreas o toda la empresa).
4. Administra cuentas y reglas; un cambio de regla reprocesa la clasificación.

## Reglas del servicio

- SAP es la fuente de las líneas contables. Este servicio no escribe en SAP.
  Usuario de base de datos SAP de solo lectura.
- Toda tabla propia lleva `company_id` (empresa de auth). Ninguna consulta ni
  proceso mezcla empresas. Las reglas y cuentas son por empresa.
- La base/schema SAP de cada empresa sale de configuración o de una tabla
  administrada, nunca del cliente. Un identificador SQL (schema SAP) solo se usa
  si está en esa lista cerrada; los valores siempre como parámetros.
- No fijar en código hosts, schemas SAP, cuentas (`95`, `97`) ni fechas de
  inicio: son configuración o datos administrados.
- Autorización en el backend con los permisos y alcances de auth. Estar
  autenticado o venir desde la central no concede acceso. Alcance `company` ve
  todas las áreas; alcance `area` solo las suyas (filtro aplicado en el
  servidor aunque el cliente pida otras).
- El área de una línea no es el "Area" de SAP (que es el nombre del centro de
  costo): se obtiene de la homologación propia centro de costo → área de auth
  (acuerdo del usuario). Un centro, una sola área. Coincidencia `exact` ahora,
  `prefix` previsto. Centro sin homologar o vacío: solo alcance `company`.
- Reglas: DELETE es baja lógica. Crear, editar o dar de baja una regla genera
  historial (antes/después) en la misma transacción.
- Las líneas se guardan tal como vienen de SAP (acuerdo): sin corregir textos,
  signos ni centros vacíos, y sin borrarlas. Todo ajuste se hace por
  configuración (reglas, homologación), nunca modificando el dato de origen.
- Importes con signo tal como SAP; la presentación es del front.
- Actores (acuerdo): catálogo local `libro_mayor.actors` (user/system/service);
  `created_by`/`updated_by`/`deleted_by` apuntan ahí. La sincronización
  programada es un proceso interno atribuido a `libro-mayor.scheduler`; no usa
  API key ni un usuario inventado en auth.
- Sin pandas/numpy (acuerdo): motor de reglas en Python simple. Sin
  `tipo_regla`; categorías en catálogo propio.
- Trabajos largos con estado persistente propio (ejecución, progreso, errores,
  marca de agua), idempotentes y separados de los logs técnicos.
- Importes con `Numeric`/`Decimal` de extremo a extremo; no convertir a `float`.
- Logs con `packages/platform-audit` (schema `audit`, columna `service`). No
  registrar credenciales SAP ni cadenas de conexión.
- Rutas bajo el prefijo `/libro-mayor/...` para que la central enrute sin
  reescribir. La publicación en la central es un paso posterior y explícito.
- PostgreSQL primero; SQL Server por validar; sin SQLite. HANA es solo origen.

## Verificación

Aislamiento entre empresas (reglas, cuentas, líneas, historial y ejecuciones),
filtro por área frente a un usuario con alcance `area` que pide otra área,
reproceso determinista (mismo resultado en sincronización y en reproceso),
bajas lógicas de reglas con reproceso, idempotencia de ejecuciones repetidas o
solapadas, y que un fallo a mitad de sincronización no deje una ejecución
marcada como completada.
