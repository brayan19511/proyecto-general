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
`actors`, `sap_settings`, `sap_databases`, `jobs`, `job_items`, `job_events` (historial de cada
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

## Configuración

Ver `.env.example`: `SAP_SERVICE_LAYER_URL`, `SAP_VERIFY_TLS` / `SAP_CA_FILE`,
timeouts, `CREDENTIALS_ENCRYPTION_KEYS`, `JOB_MAX_ITEMS`, `WORKER_*`.

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
- [ ] Probar contra el Service Layer real (prueba del usuario).
- [ ] Escenario de producción (al terminar los módulos).
