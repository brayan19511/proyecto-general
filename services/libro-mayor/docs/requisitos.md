# Requisitos del servicio libro-mayor

Estado: requisitos objetivo, sin implementación. Se distinguen **acuerdos** (lo
que el usuario ha pedido) de **propuestas** del asistente y **pendientes**. Una
propuesta no se implementa sin confirmación.

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

Los permisos viven en el catálogo de auth y se heredan por puestos. Nombres
propuestos (pendientes de confirmar):

| Permiso | Alcances | Uso |
| --- | --- | --- |
| `ledger.view` | area, company | Consultar líneas, resumen y detalle |
| `ledger.export` | area, company | Exportar a Excel |
| `ledger.rules.manage` | company | Crear, editar y dar de baja reglas; reprocesar |
| `ledger.accounts.manage` | company | Registrar cuentas a sincronizar |
| `ledger.sync` | company | Lanzar sincronización o reproceso manual |

- "Contador master" (acuerdo del usuario) = `ledger.view` con alcance `company`:
  filtra cualquier área de la empresa.
- Usuario de área = `ledger.view` con alcance `area`: solo ve sus áreas y puede
  filtrar entre ellas. Si pide un área ajena, se responde 403 o se ignora
  (pendiente: elegir comportamiento).
- El administrador de plataforma (`is_platform_admin`) no necesita puestos, pero
  sigue limitado a la empresa activa de la solicitud.

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

Campos (heredados de proyecto-05): prioridad, tipo (`CUENTA`, `MIXTA`, `TEXTO`),
cuenta, cuenta contrapartida, centro de costo, texto incluido, texto excluido,
monto mínimo/máximo, y resultado: código, subcódigo y nombre de reporte.

- Evaluación: reglas activas de la empresa ordenadas por `prioridad, id`; la
  primera que cumple todas sus condiciones gana. Condición vacía = no filtra.
- Texto: búsqueda sin distinguir mayúsculas en proveedor, descripción y
  referencias 1–3 (lista cerrada).
- Sin regla: `SIN_CLASIFICAR` / `OTROS` y nombre de la cuenta SAP.
- El mismo motor se usa en sincronización y en reproceso (determinismo).
- Pendiente: si `tipo_regla` restringe qué campos se admiten o es solo
  informativo; validar que una regla tenga al menos una condición.
- Acuerdo: los importes se guardan y devuelven con signo, tal como SAP
  (433 de 2 343 líneas negativas en septiembre 2026); la presentación la
  resuelve el front. Interpretación: las reglas con monto comparan el valor con
  signo, como en proyecto-05 (confirmar al implementar el motor).
- Textos con caracteres dañados (`Nota Cr�dito`): según el usuario vienen de
  SAP. Se guardan tal cual; una regla de texto debe escribirse como aparece en
  el origen. Corregirlo corresponde al equipo SAP (vista o datos).

## Reproceso

- Crear/editar una regla reprocesa las líneas candidatas (las que ya tenía esa
  regla + las que ahora podrían cumplirla) con el conjunto completo de reglas.
- Baja lógica de una regla reprocesa las líneas que la tenían.
- Reproceso manual por cuenta y rango de fechas.
- Propuesta: ejecutar el reproceso como trabajo persistido (igual que la
  sincronización) cuando el volumen lo requiera; el guardado de la regla y su
  historial es transaccional, el reproceso posterior puede ser asíncrono.
- Propuesta: la clasificación es un dato derivado; no se guarda historial por
  línea, sino un registro por ejecución de reproceso (regla, actor, conteos).
  Pendiente de confirmar.

## Consultas

- Líneas por rango de fechas y cuenta/tipo, con filtros por área, código,
  subcódigo, proveedor, año y mes.
- Resumen agregado (año, mes, código, subcódigo, nombre, proveedor, conteo,
  importes ML y ME) y su detalle.
- Exportación Excel (`openpyxl`, cuando llegue el paso).
- El filtro de áreas autorizadas se aplica siempre en el servidor, a través
  de la homologación de centros de costo (sección siguiente).
- Rangos acotados y paginación en listados (límites a definir).

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
  consultar (propuesta; evita reprocesos masivos). Pendiente confirmar si
  además se guarda el área resuelta en la línea por rendimiento.
- Propuesta: catálogo local de centros de costo (código y nombre), alimentado
  al sincronizar y, si SAP lo permite, desde su tabla de centros de costo
  (`OPRC` en SAP B1, por confirmar con el equipo SAP), para homologar centros
  antes de que tengan movimientos.
- Acuerdo: la tabla de homologación lleva una columna de modo de coincidencia
  (`exact` | `prefix`). Se implementa primero `exact`; `prefix`
  (`V114*` → Ventas) queda previsto para el futuro y, al activarlo, exacto
  tiene prioridad sobre prefijo y el prefijo más largo sobre el más corto.
- Acuerdo: un centro de costo pertenece a una sola área (único activo por
  empresa y centro).
- Líneas sin centro de costo o con centro no homologado: se guardan igual
  (acuerdo) y solo las ve el alcance `company` hasta que se configure su
  homologación (propuesta; coherente con "extraer y luego configurar").
  Reporte de centros sin homologar para el administrador.
- Pendiente: consultar SAP en directo (`get-by-sap` de proyecto-05) o solo la
  copia local. Recomendación: solo copia local para usuarios; SAP directo, si
  se mantiene, solo para administración.

## Identidad hacia auth

- Implementado (2026-09-28), mismo criterio que la central: libro-mayor no
  valida tokens; pregunta a auth `GET /auth/me` (usuario) y
  `GET /auth/me/permissions` con `X-Company-Id` (empresa validada y permisos
  con alcance). Refleja revocaciones al instante; cuesta dos llamadas por
  solicitud (una si auth agrega el id de usuario a `/me/permissions`). Solo
  Bearer por ahora; `X-API-Key` pendiente.
- Pendiente en auth: agregar los códigos `ledger.*` a su catálogo de permisos
  y asignarlos a roles. Hoy solo el administrador de plataforma opera cuentas.
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
4. Modelos de cuentas, reglas e historial. Hecho: actores, compañía SAP y
   cuentas con CRUD completo (alta, consulta, edición, baja lógica),
   validación de superposición e historial genérico. Falta: reglas y
   categorías.
5. Motor de reglas (función pura, probada aisladamente).
6. ~~Sincronización manual de una cuenta y un día, con registro de ejecución
   (fase B).~~ Hecho en código (2026-09-28): `sync_runs`, `ledger_lines`,
   `POST /sync-runs` y worker; sin clasificar (acuerdo). Falta probar contra
   HANA real.
7. ~~Delta, marca de agua y programación (fase C, worker interno).~~ Hecho
   en código (2026-09-28). Por confirmar: horas de `SYNC_SCHEDULE` y
   `SAP_TIMEZONE` (defaults 06:00, 10:00, 14:00, 18:00 en America/Lima), y
   que `fecha_creacion`/`fecha_actualizacion` de la vista reflejen todo
   cambio de una línea (el delta depende de ellas).
8. Autenticación contra auth (hecha) y filtro por áreas (pendiente).
9. Consultas, resumen y exportación.
10. Reproceso y administración de reglas.
11. Publicación de rutas en la central.
