# canales-venta

Servicio de canales de venta de la empresa (Python + FastAPI). Prefijo `/canales-venta`.
Origen: `app/api/sales_channel` de proyecto-05. Lee `docs/arquitectura.md` y el
`AGENTS.md` raíz antes de modificarlo.

## Alcance

Hoy solo **lastmiller**: SKU de Rappi Perú, Rappi México y PedidosYa Perú (una
sola empresa de la plataforma): listado, alta, on/off, baja y promoción (PeYa)
de un SKU; cargas masivas con vista previa; historial de cambios.

## Decisiones (usuario, 2026-10-03)

- Rutas de lastmiller bajo `/canales-venta/lastmiller/...`.
- Permisos en el catálogo de auth, acumulativos y compartidos por SKU y promociones:

  | Permiso             | Puede                                                     |
  | ------------------- | --------------------------------------------------------- |
  | `lastmiller.view`   | Consultar SKU, promociones, historial y cargas            |
  | `lastmiller.edit`   | Además, alta, on/off, baja y promoción de un SKU          |
  | `lastmiller.import` | Además, cargas masivas (on/off y promociones)             |

- Las tablas de Ofisis son estado externo que lee lastmiller: se aceptan altas y
  bajas reales allí (opción a). Cada cambio queda como evento en el historial
  propio del servicio (schema `canales_venta`). Un SKU con promoción no se
  elimina (409): primero se quita la promoción.

## Decisiones (usuario, 2026-10-04)

- El id externo (`id_rappi` / `id_peya`) es el mismo sku: no se pide ni se edita.
- Cargas masivas (.xlsx, columnas `sku` y on/off; mismo formato que proyecto-05),
  siempre en dos pasos: vista previa (no toca Ofisis y queda registrada) y aplicar.
  - **On/off completa** (`sku_full`, los tres canales): cada SKU listado queda
    on/off según el archivo; los existentes que no están quedan off. Sin columna
    on/off, lo listado queda on.
  - **On/off parcial** (`sku_partial`): solo cambian los SKU del archivo.
  - En ambas, `create_missing` crea los SKU que no existen (si no, se informan y omiten).
  - **Promociones** (`promotions`, solo PeYa): el archivo es la lista completa.
    Todos los SKU deben existir (si falta uno, no se aplica nada). El resultado
    es exactamente esa lista: se quitan las que no están y se agregan las nuevas
    (mismo resultado que borrar todo y recargar, sin dejar el canal vacío a medias).
- Al aplicar se recalcula el plan contra Ofisis: si cambió desde la vista previa, 409.
- Escritura por lotes de `LASTMILLER_WRITE_BATCH_SIZE` (200), una transacción por
  lote: bloqueos cortos. Si un lote falla, los anteriores quedan aplicados (con su
  historial) y la carga queda `failed` con su avance. Una sola carga en curso por canal.
- Ofisis y la base propia no comparten transacción: los eventos se agregan antes de
  escribir en Ofisis y se confirman después (ver `app/lastmiller/sku_service.py`).

## Bases de datos

- Propia (PostgreSQL, schema `canales_venta`, Alembic en `migrations/`): `actors`,
  `sku_events` (historial, solo anexado) y `sku_imports` (cargas y su vista previa).
- Ofisis (SQL Server externo, EcommDB): `app/external/ofisis.py`. Sin pool
  (NullPool), lecturas en AUTOCOMMIT, escrituras en transacciones cortas por lote,
  `SET LOCK_TIMEOUT` y timeouts de login y consulta, para no dejar conexiones
  abiertas ni retener bloqueos. Variables `OFISIS_*` en `.env.example`.
- ICG (SQL Server externo, nombres de artículos): pendiente.

`/ready` solo comprueba la base propia: no consulta Ofisis ni ICG, para que los
healthchecks no abran conexiones a bases externas.

Entorno local: Python 3.14 (como la imagen; `uuid.uuid7`).

## Autorización

Cada ruta pregunta a auth (`GET /auth/me/permissions`, Bearer + `X-Company-Id`)
igual que libro-mayor (`app/api/dependencies.py`). Además, solo la empresa de
`LASTMILLER_COMPANY_CODE` (RASH) puede usar lastmiller: las tablas de Ofisis no
distinguen empresas. Otra empresa recibe 404 aunque tenga el permiso.

## Rutas

Prefijo de canal: `/canales-venta/lastmiller/{pais}/{proveedor}` (`pe/rappi`,
`mx/rappi`, `pe/peya`).

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| GET | `/canales-venta/lastmiller/channels` | view | Canales configurados (no consulta Ofisis) |
| GET | `.../skus` | view | SKU paginados: `search`, `active`, `promotion` (solo PeYa), `limit` (≤500), `offset` |
| GET | `.../skus/export` | view | Consolidado en CSV con los mismos filtros (sin paginar) |
| POST | `.../skus` | edit | Alta (`sku`, `is_active`); id externo = sku |
| PATCH | `.../skus/{sku}` | edit | On/off (`is_active`) |
| DELETE | `.../skus/{sku}` | edit | Elimina de Ofisis (409 si tiene promoción) |
| POST / DELETE | `.../skus/{sku}/promotion` | edit | Agrega / quita la promoción (solo PeYa) |
| POST | `.../imports/preview` | import | multipart `kind`, `create_missing`, `file` → vista previa |
| POST | `.../imports/{id}/apply` | import | Aplica la vista previa (409 si el canal cambió) |
| GET | `.../imports` y `.../imports/{id}` | view | Cargas del canal y su detalle |
| GET | `.../history` | view | Historial de cambios: `sku`, `import_id` |
| GET | `/canales-venta/admin/logs` y `/{log_id}` | platform admin | Logs técnicos propios; en el front, Monitoreo › Actividad y logs |

Las fechas de los SKU son las de Ofisis (hora del servidor, sin zona), no UTC.

## Estado

- [x] Esqueleto desde `base-fastapi` (`/health`, `/ready`, logs `audit`).
- [x] Conexión a Ofisis (driver ODBC 18 en la imagen).
- [x] Listado de SKU con autorización contra auth.
- [x] Publicación en la central (`CANALES_VENTA_ENABLED`), en Caddy y en el Compose de desarrollo.
- [x] Logs en Monitoreo.
- [x] Alta, on/off, baja y promoción individual con historial.
- [x] Cargas masivas con vista previa (on/off completa y parcial; promociones PeYa).
- [x] Front: Canales de venta › Rappi Perú / Rappi México / PedidosYa Perú.
- [ ] Probar las escrituras reales contra Ofisis.
- [ ] Nombres de artículo desde ICG.
- [ ] Escenario de producción (al terminar los módulos).
