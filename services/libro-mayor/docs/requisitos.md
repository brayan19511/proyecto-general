# Requisitos del servicio libro-mayor

Estado (2026-09-30): implementado lo acordado (ver el orden de construcción
al final); falta probar contra HANA real y publicar en la central. Se distinguen
**acuerdos** (lo que el usuario ha pedido) de **propuestas** del asistente y
**pendientes**. Una propuesta no se implementa sin confirmación.

## Alcance

Incluido:
- Conexión de solo lectura a SAP Business One sobre HANA por empresa.
- Registro administrable de cuentas a sincronizar.
- Sincronización programada (acuerdo: unas 4 veces al día) y manual.
- Clasificación de líneas con reglas de gasto por prioridad.
- Administración de reglas y reproceso de lo ya sincronizado.
- Consultas, resumen y exportación con filtro obligatorio por alcance de áreas.

Fuera de alcance por ahora:
- Escribir o contabilizar en SAP.
- Presupuestos, aprobaciones o flujos de gasto.
- Interfaz web (la futura app React consumirá vía la central).
- Otras fuentes distintas de SAP.

## Actores y permisos

Los permisos viven en el catálogo de auth y se heredan por puestos. Acuerdo
del usuario (2026-09-30): tres niveles, cada uno incluye al anterior.

| Permiso | Alcances | Uso |
| --- | --- | --- |
| `ledger.view` | company o area | Consultar líneas, resumen, CSV y en vivo; ver reglas, categorías, cuentas y sincronizaciones |
| `ledger.update` | company | Además crear, editar y dar de baja reglas y categorías, importarlas y reclasificar |
| `ledger.admin` | company | Además registrar cuentas y lanzar sincronizaciones manuales |

- "Contador master" (acuerdo del usuario) = `ledger.view` con alcance `company`:
  filtra cualquier área de la empresa.
- Usuario de área = `ledger.view` con alcance `area`: solo ve las líneas de
  centros homologados a sus áreas (acuerdo del usuario, 2026-09-30):

| Usuario | Permiso en auth | Ve |
| --- | --- | --- |
| Contador master | `ledger.view` alcance `company` | Todo, incluso líneas sin centro o con centro sin homologar |
| Vendedor (puesto en VENTAS) | `ledger.view` alcance `area`, área VENTAS | Solo centros homologados a VENTAS |
| Contador asignado a ventas | `ledger.view` alcance `area`, área VENTAS | Igual que el anterior: solo VENTAS |
| Usuario con puestos en VENTAS y ADMINISTRACION | `ledger.view` alcance `area`, ambas áreas | Solo centros de esas dos áreas |
- El administrador de plataforma (`is_platform_admin`) no necesita puestos, pero
  sigue limitado a la empresa activa de la solicitud. Compañía SAP, seed y logs
  son solo suyos.

## Empresas y conexión SAP

- Acuerdo: mismo servidor HANA; cada compañía/país es otra base (schema SBO),
  p. ej. `SBO_RASH_PRODUCCION`.
- Propuesta: tabla o configuración `company_id (auth) → schema SAP` cerrada.
  Una empresa sin schema configurado no sincroniza ni consulta SAP.
- Propuesta: la vista SAP a consultar (`VW_LIBRO_MAYOR_PERSONALIZADO_2` en
  proyecto-05) también se configura; es un contrato con el equipo SAP y se
  documentan sus columnas.
- Driver: `hdbcli` + `sqlalchemy-hana` (usados en proyecto-05). Se incorporan
  solo en el paso de conexión, con explicación.
- Credenciales SAP en variables de entorno/secretos; nunca en logs ni historial.
- Pendiente: un usuario HANA por schema o uno con acceso a ambos.

## Cuentas

- Acuerdo inicial: todo lo que empiece por `95` y `97`. Luego llegaron cuentas
  completas (más de dos dígitos). En la muestra de septiembre 2026 las cuentas
  son de 9 dígitos (p. ej. `959005993`), 59 distintas solo en la 95.
- Tabla de cuentas por empresa con modo `prefix` | `exact`, para soportar
  ambos casos sin cambiar código (ver modelo-datos.md).
- Nueva solicitud (2026-09-28), cuentas explícitas:
  - `979005400`, `979005610`, `979005620`, `979005911`, `979005921`,
    `979005998`, `979005999`, `979008610` (gastos diversos, dentro de la 97).
  - `701110002` … `701110030`, 18 cuentas de ventas por línea de producto
    (POWERZONE, celulares, cómputo, video, etc.).
- Acuerdo: las `70…` usan el mismo modelo y columnas; solo cambia la cuenta.
  Se registran explícitas (las 18) o como prefijo `70`, según se decida por
  configuración, sin cambiar código. Son cuentas de ventas: su volumen puede
  superar en mucho las ~2 300 líneas/mes de la 95; medir un mes antes de
  cerrar el tamaño de las partes del job.
- Acuerdo: se prohíben registros superpuestos (una exacta cubierta por un
  prefijo activo o un prefijo que cubre exactas activas). Para pasar de `97`
  a las 8 explícitas se da de baja el prefijo.
- `tipo_cuenta = cuenta[:2]` de proyecto-05 se reemplaza por la cuenta
  registrada que trajo la línea.
- Dar de baja una cuenta detiene su sincronización; no borra líneas ya traídas.

## Sincronización

Flujo acordado: un job periódico (≈4 veces al día) extrae de SAP las líneas de
las cuentas registradas, inserta las nuevas / actualiza las modificadas y las
clasifica con las reglas activas.

- Delta por marca de agua: por empresa y cuenta, desde la última
  `fecha_actualizacion` confirmada, con solapamiento pequeño (upsert
  idempotente por `transaccion_id + linea`).
- Primera carga: fecha inicial configurable por empresa (proyecto-05 fijaba
  2026-01-01 en código).
- Cada ejecución queda persistida: quién/qué la lanzó (actor de sistema o
  usuario), parámetros, estado, contadores, error saneado, inicio/fin. La marca
  de agua solo avanza si la ejecución termina bien.
- No lanzar dos ejecuciones simultáneas para la misma empresa+cuenta
  (bloqueo o unicidad de ejecución en curso).
- La respuesta HTTP de una sincronización manual devuelve el id de ejecución
  (202); el final HTTP no es el final del trabajo.
- Acuerdo: la sincronización programada es un proceso interno de este
  servicio, atribuido al actor de sistema `libro-mayor.scheduler`. No usa API
  key ni usuario de auth, ni pasa por la central.
- Acuerdo — forma del proceso: worker/scheduler propio del servicio, en la
  misma imagen con otro comando, separado de la API para que la carga no la
  frene. Guarda cada ejecución en `sync_runs`, procesa por partes
  (cuenta × día) con commit y progreso por parte, y no permite dos ejecuciones
  simultáneas para la misma empresa+cuenta. Programación con una librería
  pequeña o bucle propio (sin RabbitMQ para esto). Si otro proyecto necesita
  jobs, lo genérico se extrae a `packages/platform-jobs` (código compartido,
  tablas propias de cada servicio). No hay servicio de jobs central.
- Acuerdo: las líneas se guardan tal como vienen de SAP (centro de costo vacío
  sigue vacío, textos y signos sin corregir). El servicio solo extrae y aplica
  la configuración (reglas, homologación); nunca borra ni corrige datos de
  origen. Una línea desaparecida de SAP no se borra aquí (SAP B1 anula con
  asiento de reversa, que llega como línea nueva).
- Zona horaria de SAP: `SAP_TIMEZONE` (default America/Lima, por confirmar).
  Las fechas de SAP se guardan tal como vienen (sin zona); la marca de agua
  es un día SAP, así que no hace falta convertirlas a UTC.

## Reglas de gasto

**Implementado** (2026-09-30). Categorías de dos niveles, reglas con las
condiciones de proyecto-05 sin `tipo_regla`, motor puro
(`app/services/classifier.py`). Ver readme, "Clasificación".

- Evaluación por `priority, id`; gana la primera que cumple. Condición vacía =
  no filtra. Sin regla = sin clasificar (`rule_id` NULL); el nombre de reporte
  cae al de la cuenta SAP.
- Acuerdo (2026-09-30): en la API se usan los nombres de proyecto-05:
  `codigo` (categoría), `subcodigo` (subcategoría), `nombre_cuenta`. Las
  categorías se identifican por nombre (sin código generado).
- `nombre_cuenta` (columna `report_name`): etiqueta de la línea en
  reportes, distinta de categoría y subcategoría (en septiembre 2026,
  "DIFERENCIA POR REDONDEO" y "DIFERENCIA DE INVENTARIO" dentro de la misma
  subcategoría). Se mantiene, opcional.
- Texto: sin distinguir mayúsculas en proveedor, descripción y referencias 1–3.
- Acuerdo: los importes se guardan y devuelven con signo, tal como SAP
  (433 de 2 343 líneas negativas en septiembre 2026). Las reglas con monto
  comparan el valor con signo (interpretación implementada; confirmar).
- Textos con caracteres dañados (`Nota Cr�dito`): vienen de SAP. Se guardan
  tal cual; una regla de texto debe escribirse como aparece en el origen.
- Pendiente: si las cuentas 70 (ventas) usan las mismas categorías y reglas o
  un catálogo propio. Hoy el motor no distingue: aplica las reglas de la
  empresa a toda línea.

## Carga masiva de reglas

**Implementado** (2026-09-30, pedido del usuario). `POST /rules/import` en vez
de SQL directo en la base: el SQL se saltaría validaciones, historial, actor y
reclasificación, y el `DELETE` de proyecto-05 borraba filas. Todo o nada,
`dry_run`, `mode=replace` con baja lógica, categorías por nombre (se crean si
faltan) y una reclasificación al final. Conversor del SQL de proyecto-05:
`scripts/convert_legacy_rules.py`; reglas de RASH Perú en
`data/import/reglas_rash_peru.json` (225 activas, 21 categorías).

Avisos en los datos de RASH para revisar con contabilidad (el import no los
corrige: se cargan tal cual):
- Categorías casi iguales que quedan separadas: `OPERACIONES` /
  `OPERACIONES GV08`, `OTROS GASTOS E-COMMERCE` / `OTROS GASTOS E-COMMERCE GV09`,
  `GASTOS EXTRAORDINARIOS` / `GASTOS EXTRAORDINARIOS GV11`.
- Subcategoría con doble espacio: `UTILES  DE ESCRITORIO` frente a
  `UTILES DE ESCRITORIO`.
- `959003132`: con centro `A0000001` va a `OPERACIONES GV08` y sin centro a
  `CORPORATIVO`; en las demás cuentas el patrón es el inverso (A0000001 →
  CORPORATIVO). Posible inversión en el origen.

## Reproceso

**Implementado.** Crear, editar o dar de baja una regla registra una
reclasificación en la misma transacción; la hace el worker con las líneas
candidatas (las que tenían la regla + las que podrían cumplirla). También
manual (`POST /classification-runs`) para todo o un rango. La clasificación es
un dato derivado: sin historial por línea; el registro es la ejecución.

## Consultas en vivo

**Implementado** (2026-09-30, pedido y diseño del usuario). Una sola llamada:
consulta SAP de una o varias cuentas (`["95*", "97*", "701110002"]`), parte el
rango en tramos (mes por defecto, o día), los consulta en paralelo, clasifica
al vuelo y devuelve la respuesta completa según `view` (acuerdo, en el body):
`lines` (solo líneas, default a pedido del usuario), `summary` (solo resumen)
o `full` (ambos).
No guarda resultados ni toca `ledger_lines`.

- Primera versión asíncrona (202 + consultar después, resultados en tablas)
  reemplazada por decisión del usuario: preocupaba acumular resultados con
  miles de consultas.
- Límites (del asistente, ajustables): 4 consultas a SAP a la vez por proceso,
  100 000 líneas con detalle, 120 s, 366 días, 20 cuentas.
- Filtro por áreas: implementado (homologación de centros de costo). En la
  central esta ruta tiene su propio timeout (130 s).
- Futuro posible (no ahora): una cuenta por consulta si el volumen lo exige.

## Consultas

- Líneas por rango de fechas y cuenta/tipo, con filtros por área, código,
  subcódigo, proveedor, año y mes.
- Resumen agregado (año, mes, código, subcódigo, nombre, proveedor, conteo,
  importes ML y ME) y su detalle.
- Exportación para Excel / Power BI: `GET /ledger/lines.csv` en streaming
  (implementado; reemplaza la idea de generar `.xlsx` con `openpyxl`).
- El filtro de áreas autorizadas se aplica siempre en el servidor, a través
  de la homologación de centros de costo (sección siguiente).
- Rangos acotados y paginación en listados: implementado (`limit` ≤ 5000 en
  `/ledger/lines`; límites de la consulta en vivo en la sección anterior).

## Centros de costo y homologación

Observado en la exportación de septiembre 2026 (RadioShack, cuenta 95,
2 343 líneas):

- Centro de costo SAP de 8 caracteres. `A…` administrativos
  (`A0106000 GESTION HUMANA`, `A0404000 VENTAS`); `V…` ventas, casi todos
  tiendas (`V1141177 T65 REAL PLAZA PURUCHUCO I`), además de `V0000001 VENTAS
  360`, `V1140001 TIENDA CENTRAL`.
- La columna "Area" de SAP es el nombre del centro de costo (relación 1:1 en
  el mes: 195 centros, 195 nombres). No es un área de negocio.
- 450 líneas (19 %) sin centro de costo (diferencias de inventario,
  redondeos, etc.).

Acuerdo del usuario: una tabla propia homologa cada centro de costo a un área
de negocio, aunque SAP lo nombre como tienda. Ejemplo: todas las tiendas `V…`
→ área Ventas u Operaciones; `A0110003 ALMACEN CENTRAL` → Logística.

- El destino de la homologación es un área de auth (`area_id` de la empresa),
  porque los permisos con alcance `area` usan esos ids. Se valida contra auth
  al crear/editar la homologación; no se acepta un `area_id` sin comprobar.
- La homologación es por empresa, administrable, con baja lógica e historial.
- El filtro de un usuario con alcance `area` = líneas cuyo centro de costo esté
  homologado a alguna de sus áreas.
- Cambiar una homologación no reescribe las líneas: el área se resuelve al
  consultar (implementado; evita reprocesos masivos). Guardar el área resuelta
  en la línea por rendimiento queda para si hiciera falta.
- Implementado: `GET /cost-centers` lista los centros vistos en las líneas
  sincronizadas (`unmapped=true` = los que faltan homologar).
- Idea futura, abierta (decisión del usuario, 2026-09-30: no implementar
  todavía, pero no descartar): leer la tabla de centros de costo de SAP
  (`OPRC` en SAP B1, por confirmar con el equipo SAP) para listar y homologar
  centros antes de que tengan movimientos.
- Acuerdo: modo de coincidencia `exact` | `prefix`, como las cuentas
  (implementado 2026-09-30; `V114` prefijo → Ventas). Exacto tiene prioridad
  sobre prefijo y el prefijo más largo sobre el más corto, para poder
  exceptuar centros concretos.
- Acuerdo: un centro de costo resuelve a una sola área (único activo por
  empresa, código y modo).
- Líneas sin centro de costo o con centro no homologado: se guardan igual
  (acuerdo) y solo las ve el alcance `company` hasta que se configure su
  homologación (implementado; coherente con "extraer y luego configurar").
- Resuelto (decisión del usuario): las dos opciones, con las reglas
  aplicadas y el mismo filtro por áreas: en tiempo real (`POST /live-queries`,
  no guarda nada) y sobre la copia sincronizada (`/ledger/*`).

## Identidad hacia auth

- Implementado (2026-09-28), mismo criterio que la central: libro-mayor no
  valida tokens; pregunta a auth `GET /auth/me` (usuario) y
  `GET /auth/me/permissions` con `X-Company-Id` (empresa validada y permisos
  con alcance). Refleja revocaciones al instante.
- Implementado (2026-09-30): `ledger.view`, `ledger.update` y `ledger.admin`
  están en el catálogo de auth; falta asignarlos a roles en cada empresa.
- Implementado (2026-09-30): auth devuelve `user_id` en `/auth/me/permissions`
  (cambio compatible); libro-mayor hace una sola llamada y acepta X-API-Key para
  Excel / Power BI.
- La sincronización programada usa el actor de sistema local
  `libro-mayor.scheduler` (acuerdo); no usa API keys personales.

## Criterios de aceptación

1. Un usuario con alcance `area` nunca recibe líneas de otra área, ni en
   listado, resumen, detalle ni exportación.
2. Una empresa no ve reglas, cuentas, líneas ni ejecuciones de otra.
3. Repetir una sincronización del mismo rango no duplica líneas.
4. Una sincronización fallida no avanza la marca de agua ni queda "completada".
5. Clasificar en sincronización y en reproceso produce el mismo resultado.
6. Dar de baja una regla conserva la fila, su historial y reclasifica sus líneas.
7. El historial de reglas permite reconstruir quién cambió qué y cuándo.
8. Ningún schema SAP ni cuenta proviene del body sin validación contra la lista
   de la empresa.

## Hoja de ruta orientativa

Cada paso se explica y se acuerda antes de escribir código:

1. ~~Copiar la plantilla base, prefijo `/libro-mayor`, health/ready y audit.~~
   Hecho (2026-09-28).
2. ~~Conexión PostgreSQL + schema propio + Alembic.~~ Hecho (schema
   `libro_mayor`).
3. Conexión HANA de solo lectura y consulta de prueba a la vista. Hecho en
   código (fase A: `app/sap/`, `scripts/check_sap.py`, seed); falta que el
   usuario lo pruebe contra HANA real.
4. ~~Modelos de cuentas, reglas e historial.~~ Hecho: actores, compañía SAP,
   cuentas, categorías y reglas con CRUD completo e historial.
5. ~~Motor de reglas (función pura, probada aisladamente).~~ Hecho
   (2026-09-30), también integrado en la sincronización.
6. ~~Sincronización manual de una cuenta y un día, con registro de ejecución
   (fase B).~~ Hecho en código (2026-09-28): `sync_runs`, `ledger_lines`,
   `POST /sync-runs` y worker; sin clasificar (acuerdo). Falta probar contra
   HANA real.
7. ~~Delta, marca de agua y programación (fase C, worker interno).~~ Hecho
   en código (2026-09-28). Por confirmar: horas de `SYNC_SCHEDULE` y
   `SAP_TIMEZONE` (defaults 06:00, 10:00, 14:00, 18:00 en America/Lima), y
   que `fecha_creacion`/`fecha_actualizacion` de la vista reflejen todo
   cambio de una línea (el delta depende de ellas).
8. ~~Autenticación contra auth y filtro por áreas.~~ Hecho (2026-09-30):
   también con API key; homologación `cost_center_mappings` y filtro en
   líneas, resumen, CSV y consultas en vivo.
9. ~~Consultas, resumen y exportación.~~ Hecho (2026-09-30): `GET /ledger/lines`
   (paginado), `/ledger/lines.csv` (streaming para Excel / Power BI con API key)
   y `/ledger/summary`, con alcance company o area.
10. ~~Reproceso y administración de reglas.~~ Hecho (2026-09-30). Además:
    consultas en vivo en una llamada, por tramos en paralelo.
11. ~~Publicación de rutas en la central.~~ Hecho (2026-09-30): reenvío
    generalizado, timeout por ruta, streaming y gzip tal cual (ver
    `docs/integracion-central.md`).
