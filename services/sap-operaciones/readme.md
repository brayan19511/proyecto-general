# sap-operaciones

Trabajos masivos en SAP Business One por Service Layer (Python + FastAPI, API y
worker). Prefijo `/sap-operaciones`. Origen: `app/api/sap` de proyecto-05. Lee
`docs/arquitectura.md` y el `AGENTS.md` raíz antes de modificarlo.

## Qué hace

- **Acción sobre documentos:** `POST {Entidad}({DocEntry})/{Acción}` por cada
  documento (p. ej. `Invoices(1520)/Cancel`).
- **Conciliación interna:** Excel → un `POST InternalReconciliations` por
  `ReconNum`; cada grupo debe sumar 0 (el signo define débito o crédito).

Flujo: vista previa (crea el trabajo en **borrador**, no toca SAP) → **ejecutar**
con usuario y clave SAP del operador (se prueba el login y queda en cola) →
el **worker** ejecuta los ítems de a uno → consulta, cancelación y reanudación.

## Decisiones (usuario, 2026-10-04)

- Credenciales del operador (SAP aplica sus permisos y registra los cambios a
  su nombre). La clave se guarda cifrada (Fernet, `CREDENTIALS_ENCRYPTION_KEYS`)
  y se conserva; solo el administrador de plataforma puede verla
  (`GET /jobs/{id}/credentials`); cada consulta queda en el historial. El usuario SAP
  lo ve cualquiera que vea el trabajo. `jobs.credentials_by` registra quién la ingresó.
  Regla general de la plataforma: ver `docs/arquitectura.md`.
- Base SAP (CompanyDB): lista sugerida por empresa (`/databases`) o texto libre
  validado (letras, números y `_`).
- URL del Service Layer editable por empresa (`/settings`), solo por el
  administrador de plataforma: las claves de los operadores viajan a esa URL.
  Sin URL propia se usa `SAP_SERVICE_LAYER_URL`. Cada trabajo guarda la URL con
  que se ejecuta (`jobs.service_layer_url`), fijada al encolar o reanudar.
- `SAP_VERIFY_TLS=false` en desarrollo (decisión del usuario): no instalar la CA
  en cada máquina.
- Entidad y acción libres, validadas como segmentos de ruta (nunca una URL libre).
- Permisos acumulativos con alcance company: `sap_operations.view` y
  `sap_operations.execute`.
- Módulo SAP propio en el front (lo usa el administrador de SAP); las
  conciliaciones podrían pasar a Contabilidad más adelante.
- **Sin reintentos automáticos** de llamadas que modifican SAP:
  - SAP responde error → ítem `failed` con el mensaje de SAP; se sigue.
  - Se cortó después de enviar → ítem `uncertain` (revisar en SAP); se sigue.
  - No hubo conexión o el login falló → el ítem vuelve a `pending` y el trabajo
    queda `failed` (detenido); se puede **reanudar** (los inciertos no se repiten).
  - Única excepción: 401 por sesión vencida (SAP no ejecutó nada) → nuevo login
    y un reintento de esa solicitud.

## Estados

Trabajo: `draft` → `queued` → `running` → `completed` / `completed_with_errors`
/ `failed` (detenido, reanudable) / `cancelled`. Ítem: `pending`, `running`,
`succeeded`, `failed`, `uncertain`, `cancelled`.

Worker: toma trabajos con `SKIP LOCKED` y renueva su bloqueo
(`WORKER_LOCK_SECONDS`) en cada ítem. Si cae, otro worker retoma el trabajo al
vencer el bloqueo y el ítem que estaba en curso queda `uncertain`. Con SIGTERM
termina el ítem en curso y devuelve el trabajo a la cola.

## Bases de datos

Propia (PostgreSQL, schema `sap_operaciones`, Alembic en `migrations/`):
`actors`, `sap_settings`, `sap_databases`, `jobs`, `job_items`, `document_downloads`, `document_download_files`, `job_events` (historial de cada
trabajo, solo anexado) y `change_history` (historial de la lista de bases).
SAP solo se usa por Service Layer (`app/sap/service_layer.py`).

## Rutas

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| POST | `/jobs/document-actions/preview` | execute | `company_db`, `entity`, `action`, `documents` (texto) → borrador o errores |
| POST | `/jobs/reconciliations/preview` | execute | multipart `company_db`, `recon_date`, `file` → borrador o errores |
| POST | `/jobs/{id}/enqueue` | execute | `sap_user`, `sap_password`: prueba el login y encola |
| POST | `/jobs/{id}/cancel` | execute | Cancela (en proceso: se detiene antes del próximo ítem) |
| POST | `/jobs/{id}/resume` | execute | Reanuda un trabajo detenido (credenciales nuevas opcionales) |
| GET | `/jobs/{id}/credentials` | platform admin | Usuario y clave guardados (deja evento) |
| GET | `/jobs`, `/jobs/{id}`, `/jobs/{id}/items`, `/jobs/{id}/events` | view | Consultas |
| GET | `/jobs/{id}/items/{seq}` | view | Ítem con el JSON enviado a SAP y la respuesta (20 KB máx.) |
| GET | `/jobs/{id}/items/export` | view | CSV con todos los ítems (estado y respuesta de SAP; fechas con `EXPORT_UTC_OFFSET_HOURS`) |
| GET / POST / DELETE | `/databases` | view / execute | Bases SAP sugeridas (DELETE = baja lógica) |
| GET / PATCH | `/settings` | view / platform admin | URL del Service Layer de la empresa (null = la del despliegue) |
| GET | `/admin/logs` y `/{log_id}` | platform admin | Logs técnicos propios |
| GET | `/documents/types` | documents | Tipos de documento (FV, OC, ...) y criterios de cada uno |
| GET | `/documents/search` | documents | `company_db`, `type` y un criterio exacto (`doc_entry`, `doc_num`, `num_at_card`, `folio`) o `card_code`/`card_name` con `date_from`/`date_to` |
| GET | `/documents/{type}/{doc_entry}/attachments` | documents | Anexos del documento (`line`, nombre, fecha) |
| POST | `/documents/downloads` | documents | `company_db`, `mode` (`single`/`sequential`/`zip`) y `files` (`type_code`, `doc_entry`, `line`): valida en SAP y registra la descarga |
| GET | `/documents/downloads/{id}/files/{seq}` | documents | Un archivo de una descarga `single`/`sequential` (solo quien la pidió, una vez, 60 min) |
| GET | `/documents/downloads/{id}/zip` | documents | El ZIP de una descarga `zip`, armado mientras se envía |
| GET | `/documents/downloads`, `/documents/downloads/{id}` | documents | Registro: las propias; el administrador de plataforma, las de la empresa |

## Documentos y anexos (en desarrollo)

Buscar documentos SAP y descargar sus anexos (origen: notebook
`obtener_documentos.ipynb`). Decisiones del usuario (2026-10-27):

- Permiso `sap_documents.view` (alcance company), independiente de `sap_operations.*`.
- Por Service Layer: `{Entidad}?$filter=...` para buscar y `Attachments2({AttachmentEntry})`
  para listar los anexos.
- El archivo (decisión del usuario, 2026-10-28): el servidor Linux del SL no
  tiene montada `\10.0.0.13\Anexo` ("Fail to get the LINUX mount point"), así
  que sap-operaciones lo lee de esa carpeta, montada en solo lectura en
  `SAP_ATTACHMENTS_DIR` (`app/sap/attachment_folder.py`): abre
  `<carpeta>/<FileName>.<FileExtension>`, nunca lista la carpeta y rechaza nombres
  que salgan de ella. El `SourcePath` del SL es la PC de quien lo subió: no sirve.
  Sin `SAP_ATTACHMENTS_DIR` se usa `Attachments2({id})/$value` (necesita el montaje
  en el servidor del SL). Montaje en Docker: `desarrollo/plataforma-completa/compose.anexos.yml`.
- Un solo usuario SAP por ahora (`SAP_DOCUMENTS_USER` / `SAP_DOCUMENTS_PASSWORD`);
  a futuro, credenciales por usuario. Solo se cambia `_sap_credentials` en
  `app/services/document_service.py`.
- Sesión del Service Layer reutilizada (pedido del usuario, 2026-10-28,
  `app/sap/session_pool.py`): una por URL, base y usuario en la memoria del
  proceso; dura lo que SAP indica en el login (`SessionTimeout`, hoy 30 min) y se
  renueva con cada uso. Si SAP responde 401, un solo login nuevo aunque haya
  varias solicitudes a la vez. Al apagar se cierran. Los trabajos masivos siguen
  con su propia sesión por trabajo.
- Búsqueda por cliente/proveedor: código y/o nombre (ambos "contiene", mín. 3
  caracteres: el código lleva prefijo, p. ej. P20610983970, y se busca por RUC), con rango de fechas de hasta 366 días; máximo 100 por página.
- La base debe estar en las Bases SAP sugeridas de la empresa (`GET /databases`
  también se puede leer con `sap_documents.view`).
- Toda descarga se registra (`document_downloads` + `document_download_files`):
  quién, base, modo y cada archivo (documento, anexo, nombre) con su entrega
  (`pending` → `delivered` / `failed` con el motivo). La cabecera es de solo
  anexado; de cada archivo solo cambia la entrega. Un corte a mitad deja el
  archivo `failed` ("Descarga interrumpida"). En un ZIP, el anexo que SAP no
  entrega se lista en `NO_DESCARGADOS.txt` y los demás siguen.
- Solo quien pidió la descarga baja sus archivos, una vez y dentro de 60 minutos
  (después, una descarga nueva = otro registro). Máximo 50 archivos por descarga.

Estructura (patrón repository, para poder cambiar a HANA + carpeta compartida):
`app/documents/catalog.py` (tipos: código propio → entidad SL / tabla HANA),
`app/documents/models.py` (validación de la búsqueda, filas propias),
`app/documents/repository.py` (interfaz `DocumentRepository`),
`app/sap/sl_document_repository.py` (implementación Service Layer) y
`app/services/document_service.py` (empresa, base, credencial; único lugar que
elige la implementación) y `app/services/download_service.py` (registro y entrega).

Seguridad: textos en `$filter` como literales OData escapados; el cliente
nunca envía rutas (el anexo se resuelve desde el documento); nombres de archivo
de SAP saneados.

Front: SAP › Documentos (búsqueda y anexos) y SAP › Descargas (registro).

Pendiente: probar la lectura desde la carpeta montada (usuario con lectura en
`\10.0.0.13\Anexo`), el montaje en las plantillas de producción,
`contains` y mayúsculas, campos de `StockTransfers` / `InventoryGenExits`).

## Configuración

Ver `sap-operaciones.env.example` (copiar a `sap-operaciones.env`): `SAP_SERVICE_LAYER_URL`, `SAP_VERIFY_TLS` / `SAP_CA_FILE`,
timeouts, `CREDENTIALS_ENCRYPTION_KEYS`, `JOB_MAX_ITEMS`, `WORKER_*`,
`SAP_DOCUMENTS_USER` / `SAP_DOCUMENTS_PASSWORD` (usuario SAP de `/documents`;
vacío = 409; conviene uno de solo lectura).
`SAP_ATTACHMENTS_DIR` (carpeta de anexos montada en el contenedor; vacío = por el
Service Layer).

El Service Layer de desarrollo usa un certificado **autofirmado**: el usuario
decidió `SAP_VERIFY_TLS=false` (la conexión sigue cifrada, sin validar el
certificado). La alternativa es instalar su CA (`SAP_CA_FILE`).

Entorno local: Python 3.14 (como la imagen; `uuid.uuid7`).

## Estado

- [x] API, worker, tablas y migración.
- [x] Publicado en la central, Caddy y el Compose de desarrollo (API + worker).
- [x] Front: SAP › Operaciones masivas y Bases SAP; logs en Monitoreo.
- [x] Probado con un Service Layer simulado (éxitos, error de SAP, timeout,
      sin conexión, reanudar, cancelar, credenciales).
- [x] Permisos cargados en auth (2026-10-04).
- [x] Documentos y anexos: API, registro de descargas, migración y front (2026-10-28; probado con SL simulado).
- [ ] Probar contra el Service Layer real (prueba del usuario).
- [ ] Escenario de producción (al terminar los módulos).
