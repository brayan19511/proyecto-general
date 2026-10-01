# Alcance del servicio pagos-proveedores

Estado (2026-10-01): **implementado** (maestro, lector, lotes y envío; dockerizado y publicado en la central). Se distinguen **acuerdos**
(lo que el usuario ha decidido) de **propuestas** del asistente y
**pendientes**. Una propuesta no se implementa sin confirmación.

## Propósito

Replicar el flujo de proyecto-05 (`app/api/finance/payment_provider`) en un
servicio propio: leer constancias de pago en PDF, identificar a qué proveedor
corresponde cada una y enviarle por correo sus constancias, usando el servicio
`notificaciones` (paso 3 del orden acordado en `services/notificaciones/docs/alcance.md`).
Carpeta `services/pagos-proveedores`, prefijo `/pagos-proveedores`.

Incluido en v1:
- Maestro de proveedores por empresa.
- Lotes: subir constancias, leerlas, agruparlas por proveedor, corregir y enviar.
- Lectura de PDFs con texto y OCR opcional para escaneados.
- ZIP con las constancias renombradas.
- Envío por `notificaciones` con la plantilla `payment_provider_summary`.

Fuera de alcance por ahora:
- Otros bancos o formatos de constancia distintos de los que ya lee proyecto-05.
- Registrar o validar pagos en SAP u otro sistema.
- Interfaz web (el front la consumirá vía la central).

## Acuerdos del usuario (2026-10-01)

1. Flujo **con lote** (opción B): las constancias se suben una vez y quedan en
   la base de este servicio con el resultado de la lectura. Es la evidencia de
   lo enviado (notificaciones purga sus copias al enviar).
2. **OCR con interruptor** (`OCR_ENABLED`), como en proyecto-05; requiere
   tesseract y poppler en la imagen.
3. Prefijo **`/pagos-proveedores`**.
4. Se mantiene el **ZIP renombrado**.
5. Los datos de proveedores (correos de pago, cuentas) son de este servicio; otro
   servicio que los necesite los consulta por API, nunca por sus tablas.
6. Debe existir un permiso para **ver** proveedores y otro para **editarlos**:
   los cuatro permisos de la sección Permisos, con dos ramas independientes.
7. Carpeta `services/pagos-proveedores` (antes `services/payment_provider`) y
   schema SQL `pagos_proveedores`.
8. Retención **indefinida** de lotes y PDFs: son la evidencia de lo pagado y
   enviado. Una purga futura requiere una decisión explícita aparte.

## Qué se replica de proyecto-05

| proyecto-05 | Aquí |
| --- | --- |
| `PaymentProvider` (`tax_id`, `legal_name`, `commercial_names`, `emails_payments`) | Tabla de proveedores con `company_id`; `tax_id` único entre los activos de la empresa (no global) |
| `pdf_parser.py` (pdfplumber + OCR, formatos BBVA, transferencias, pago de servicios) | Se porta casi tal cual: es la lógica propia del servicio |
| `processor.py` (agrupar por RUC y luego por nombre; READY / MISSING_PROVIDER / MISSING_PAYMENT_EMAIL; totales por moneda) | Se porta casi tal cual |
| `/payments/preview` | Crear un lote (subida) y consultar su resultado |
| `/payments/renamed-zip` | ZIP del lote con nombres `titular + fecha` |
| `/payments/send` y `/send-async` (EmailService, jobs, archivado en disco) | **Se reemplaza** por un `POST /notificaciones/dispatches` |
| `mailing_parameters` `payment_provider_summary` | Plantilla en notificaciones con el mismo código |

## Flujo con lote (propuesta)

1. `POST /pagos-proveedores/batches` (multipart con los PDFs): guarda los
   archivos, los lee y agrupa. Responde el lote con sus grupos y errores (lo
   que antes era la vista previa).
2. El usuario corrige: da de alta o edita proveedores, agrega correos.
   Consultar el borrador (`GET /batches/{id}`) lo vuelve a agrupar con el
   maestro actual, sin volver a subir ni leer los PDFs (no hay `refresh`).
3. `POST /batches/{id}/send`: solo si está listo (`ready_to_send`). Arma un
   envío a notificaciones con `template_code: payment_provider_summary`, un
   mensaje por proveedor (`consumer_reference` = id del proveedor) con sus
   parámetros (`proveedor`, `pagos`, `totales`) y sus PDFs, reenviando el
   token del usuario. `Idempotency-Key` = id del lote: reintentar no duplica.
4. El lote guarda el id del envío de notificaciones y muestra su estado
   consultándolo (no lo copia).

Lectura de PDFs: hasta decenas de archivos por lote, en la misma solicitud
(proyecto-05 lo hacía así). Si con OCR resulta lento, se pasa a trabajo en
segundo plano: pendiente de medir.

## Permisos (acuerdo 2026-10-01)

Catálogo en auth, alcance company. Acuerdo 6: ver y editar proveedores son
permisos distintos del envío.

| Permiso | Puede |
| --- | --- |
| `payments.view` | Ver proveedores, lotes y su estado |
| `payments.providers.manage` | Además crear, editar, dar de baja y restaurar proveedores |
| `payments.send` | Además crear lotes, descargar el ZIP y enviar (con la plantilla configurada) |
| `payments.admin` | Todo lo anterior |

`providers.manage` y `send` incluyen `view` pero no se incluyen entre sí:
alguien puede mantener el maestro sin enviar, o enviar sin editar proveedores.
Enviar exige además `notifications.send` en notificaciones.

## Lotes y envío (implementado 2026-10-01)

Rutas bajo `/pagos-proveedores/batches`: crear (multipart `files` +
`reference`), listar, ver, descargar una constancia, ZIP, quitar una constancia
y descartar (borrador), `POST /{id}/send` y `GET /{id}/delivery-status`.

- No hay `refresh`: un borrador se agrupa al consultarlo con el maestro actual.
- Elegir `template_code` al enviar exige `payments.admin` (acuerdo 2026-10-01;
  sin él, 403). Sin `template_code` se usa la plantilla por defecto de la
  empresa y, si no eligió ninguna, `DEFAULT_TEMPLATE_CODE`.
- `GET /settings` (payments.view) y `PATCH /settings` (payments.admin, body
  `{"default_template_code": "codigo" | null}`): plantilla por defecto de los
  lotes de la empresa (`company_settings`, cambio en `change_history` como
  `settings.update`). No comprueba que exista en notificaciones: si no
  existe, el envío responde 422 y el lote vuelve a borrador.
- `send` (body opcional `template_code`, `subject`, `message`): fase 1 congela
  las entregas y pasa a `sending`; fase 2 llama a notificaciones con el token del
  usuario e `Idempotency-Key` = id del lote. 4xx de notificaciones → el lote
  vuelve a `draft` (entregas del intento dadas de baja, evento
  `batch.send_rejected`) y se devuelve el mismo error; 409 no revierte.
  Timeout/5xx → queda `sending` y reenviar manda lo mismo (no duplica).
- `subject` y `message` llegan a la plantilla como `asunto` y `mensaje`; la
  plantilla debe usarlos, p. ej. `{{ asunto or 'CONSTANCIA DE PAGO ' ~ proveedor }}`.
- `delivery-status` consulta notificaciones (requiere `notifications.view`).

## Lector de constancias (2026-10-01)

Portado de proyecto-05 casi sin cambios: `app/services/pdf_reader.py` (lectura
y extracción) y `app/services/grouping.py` (agrupamiento). Recibe bytes, valida
la firma PDF, informa `used_ocr` y usa las claves de `text_keys.py`. Verificado:
las 22 pruebas del lector de proyecto-05 pasan contra el código portado, y un
PDF generado pasa por pdfplumber, extracción y agrupamiento. Falta validar con
constancias reales (`muestras/`) y el OCR (tesseract y poppler vienen en la
imagen de Docker; no en el Windows de desarrollo).

## Pendientes

- Tiempo de lectura con OCR y si hace falta un worker.
- Constancias de prueba de cada formato (BBVA consulta de operaciones,
  transferencias, pago de servicios, escaneadas) para validar el parser
  portado. Con datos reales: en una carpeta local fuera de git.
- Registrar los permisos `payments.*` en el catálogo de auth (cambio en otro
  servicio, paso aparte).
