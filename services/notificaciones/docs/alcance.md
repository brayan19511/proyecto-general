# Alcance del servicio notificaciones

Estado (2026-10-01): borrador, nada implementado. Se distinguen **acuerdos**
(lo que el usuario ha decidido) de **propuestas** del asistente y
**pendientes**. Una propuesta no se implementa sin confirmación.

## Propósito

Servicio independiente para enviar notificaciones de la plataforma, pensado
para reutilizarse en otros servicios y proyectos sin rehacer el envío, el
seguimiento ni los reintentos. Primer consumidor: `payment_provider`, que
replicará el flujo de proyecto-05 (`app/api/finance/payment_provider`).

Incluido en v1:
- Canal email por SMTP.
- Cuentas SMTP por empresa con prioridad.
- Envío siempre por trabajo (asíncrono) con seguimiento por mensaje.
- Reintentos automáticos limitados, reproceso y cancelación manuales.
- Permisos propios en el catálogo de auth.

Fuera de alcance por ahora:
- Otros canales (SMS, WhatsApp, push).
- Plantillas administrables en este servicio en la primera entrega (llegan
  en la segunda, acuerdo 12).
- Envíos programados, rebotes por webhook, límites de envío por cuenta.
- Cola externa (RabbitMQ) y servicio central de trabajos.
- Interfaz web (el front la consumirá vía la central).

## Acuerdos del usuario (2026-10-01)

1. Es un servicio propio (`notificaciones`), no un módulo de `payment_provider`.
2. La configuración SMTP es por empresa: varias cuentas con prioridad; para
   dejar de usar una se da de baja o se cambia su prioridad.
3. El envío es siempre por trabajo.
4. Asunto y cuerpo llegan ya armados por el consumidor, que resuelve sus
   parámetros dinámicos (datos del proveedor, montos, etc.). Este servicio no
   conoce plantillas en v1.
5. Retención de adjuntos: solo se conservan mientras puedan reintentarse.
   Tras 3 reintentos fallidos el mensaje queda fallido para decisión manual;
   si pasan 3 días sin reproceso, se cancela y se elimina el contenido de sus
   adjuntos. Es una decisión explícita de purga, distinta del DELETE
   ordinario.
6. Registrar envíos requiere un permiso de envío o de administración; la
   lectura solo lista y consulta.
7. Permisos: los cuatro niveles de la sección Permisos, cada uno incluye al
   anterior. El detalle técnico (intentos, cuenta usada, códigos SMTP,
   payload, headers) es solo para `notifications.admin`; en el futuro podría
   pasar a un permiso de TI separado.
8. En v1 el consumidor crea el envío con el token del usuario: quien envía
   necesita el permiso del consumidor y `notifications.send`.
9. Aviso previo: a los 2 días de quedar fallido sin reproceso se envía un
   correo de aviso indicando que al día siguiente se cancelará y ya no podrá
   reprocesarse.
10. Límite de tamaño por mensaje: 25 MB.
11. El email del solicitante se guarda al crear el envío (tomado de
    `/auth/me` con su token), para el aviso previo. Un email registrado no
    está verificado.
12. Plantillas: primero el envío con cuerpo armado por el consumidor (A);
    después, plantillas generales en este servicio (B): tabla por empresa,
    el consumidor envía `template_code` y parámetros. Es un campo opcional
    nuevo, compatible con A. Los destinatarios de negocio (p. ej. correos de
    proveedores) siguen en el consumidor. La plantilla general reemplaza a
    `mailing_parameters` de proyecto-05: nombre, asunto, cuerpo HTML/texto y
    destinatarios fijos (to, cc, bcc) que se suman a los del consumidor.

Propuesta de orden: 1) envío con cuerpo armado, 2) plantillas generales,
3) integrar `payment_provider` usando `template_code`. Así `payment_provider`
no crea una tabla de plantillas propia que luego habría que migrar.

## Cuentas SMTP

- Datos: nombre, host, puerto, modo TLS (STARTTLS o TLS implícito), usuario,
  contraseña, remitente (`from` y nombre visible), `priority`, `is_active`.
- La contraseña se guarda cifrada con una librería mantenida y una clave del
  entorno. La API nunca la devuelve; no aparece en logs ni en el historial.
- Cambios (alta, edición, prioridad, baja, restauración) con historial de
  negocio en la misma transacción.
- Propuesta: comprobar conexión y autenticación de una cuenta sin enviar
  correo (`POST .../test`).

Failover (propuesta):
- Se usan las cuentas activas por prioridad ascendente.
- Se pasa a la siguiente solo si el fallo ocurre **antes** de que el servidor
  acepte el mensaje: sin conexión, TLS, autenticación o rechazo temporal 4xx.
- Rechazo permanente 5xx de un destinatario: el mensaje falla sin probar otra
  cuenta (otra cuenta no lo arregla).
- Corte después de transmitir el contenido (timeout al final de `DATA`): el
  mensaje queda **incierto**, sin reenvío automático, para evitar duplicados.

## Envíos, mensajes e intentos

- **Envío**: el trabajo. Una solicitud con N mensajes, `Idempotency-Key`
  única por empresa, referencia opcional del consumidor (p. ej. id de lote de
  `payment_provider`) y progreso agregado.
- **Mensaje**: destinatarios (to, cc, bcc), reply-to, asunto, cuerpo HTML o
  texto, adjuntos. Cada mensaje tiene su propio contenido.
- Estados del mensaje: `pendiente → enviando → enviado`, o `reintentando`,
  `fallido`, `incierto`, `cancelado`.
- Estado del envío (derivado): `pendiente`, `en_proceso`, `completado`,
  `completado_con_errores`.
- **Intento**: solo anexado. Fecha, cuenta usada, resultado, código SMTP y
  tipo de error (sin detalles sensibles).
- La API responde `202` con el id del envío; el estado se consulta después.
  Fin HTTP y fin del trabajo son distintos.

Procesamiento (propuesta):
- PostgreSQL como cola: los mensajes se guardan antes de procesarse y un
  worker los toma con `SELECT … FOR UPDATE SKIP LOCKED`.
- El worker es otro proceso del mismo servicio (misma imagen, otro comando).
- Cada mensaje tomado tiene un bloqueo con vencimiento. Si vence mientras
  está enviándose, pasa a incierto en vez de volver a la cola: el worker pudo
  morir después de transmitirlo (ver modelo-datos.md).
- `SKIP LOCKED` es de PostgreSQL; el equivalente en SQL Server requiere
  revisión y pruebas.

Reintentos:
- Acuerdo: 3 reintentos automáticos (4 intentos en total) solo ante errores
  transitorios.
- Propuesta: espera creciente configurable (p. ej. 1, 5 y 15 minutos).
- Reproceso manual de mensajes fallidos o inciertos y cancelación manual.

## Adjuntos y retención

- Se guardan en la base del servicio (no en filesystem ni en memoria de una
  réplica), con límite de 25 MB por mensaje (acuerdo). Propuesta: medirlo
  sobre el mensaje MIME final, porque los adjuntos crecen ~33 % al
  codificarse en base64 y el servidor SMTP mide el mensaje completo.
  Configurable por entorno.
- Aviso previo (acuerdo): a los 2 días de quedar fallido o incierto, un correo
  avisa que al día siguiente se cancelará. Propuesta: el plazo cuenta desde el
  último intento y un reproceso lo reinicia; un solo aviso por envío
  (agrupa sus mensajes), dirigido a quien lo solicitó; el aviso lo emite el
  proceso de sistema y no genera a su vez otro aviso si falla.
- Al enviarse el mensaje se elimina el contenido de sus adjuntos y se
  conservan los metadatos (nombre, tipo, tamaño, hash).
- Mensaje fallido o incierto sin reproceso durante el plazo: pasa a
  `cancelado` por el proceso de sistema (actor explícito, no un usuario) y se
  elimina el contenido de sus adjuntos.
- El registro del mensaje, su cuerpo y sus intentos se conservan.
- Evidencia: el consumidor conserva sus documentos originales
  (`payment_provider` guarda sus PDFs).

## Permisos

Catálogo en auth; se heredan por puestos. Acuerdo (2026-10-01), cada nivel
incluye al anterior:

| Permiso | Alcances | Uso |
| --- | --- | --- |
| `notifications.view` | own o company | Listar envíos y mensajes; ver destinatarios, asunto, cuerpo, adjuntos y estado |
| `notifications.send` | own o company | Además crear envíos |
| `notifications.retry` | own o company | Además reprocesar y cancelar mensajes fallidos o inciertos |
| `notifications.admin` | company | Además administrar cuentas SMTP y ver el detalle técnico (intentos, cuenta usada, códigos SMTP) |

- Alcance `own`: solo los envíos que solicitó el usuario. `company`: todos los
  de la empresa.
- Todas las consultas se filtran por la empresa validada.

## Autenticación de llamadas

- Usuarios: Bearer de auth y `X-Company-Id`, validados con
  `GET /auth/me/permissions`, igual que libro-mayor.
- Propuesta v1: el consumidor crea el envío **durante la solicitud del
  usuario**, reenviando su token. El trabajo asíncrono vive en notificaciones,
  así no hace falta que un worker del consumidor se autentique sin usuario.
- Las API keys de auth pertenecen a un usuario y su membresía: usarlas para un
  servicio haría actuar al servicio como esa persona. Tampoco se crea un
  usuario técnico (AGENTS.md).
- Pendiente: credenciales máquina en auth (actor de tipo servicio) cuando un
  consumidor necesite enviar sin usuario (procesos programados).

## Flujo con payment_provider (propuesta)

1. El usuario sube PDFs y revisa la vista previa en `payment_provider`.
2. Al confirmar, `payment_provider` arma cada correo con su plantilla y sus
   parámetros y llama a `POST /notificaciones/...` con el token del usuario,
   los mensajes y los adjuntos.
3. `payment_provider` guarda el id del envío junto a su lote.
4. El usuario consulta el progreso desde notificaciones (o vía
   `payment_provider`, si se decide).

Implica que quien envía necesita el permiso de `payment_provider` y
`notifications.send`.

## Caso mapeado: mensajes que superan el límite

Hoy (acuerdo): un mensaje de más de 25 MB se rechaza con 422 y el consumidor
decide (dividir, comprimir, enlazar). Referencia: `payment_provider` suele
enviar unos 11 PDFs ligeros por proveedor.

Futuro, si un consumidor lo necesita: división opcional **en este servicio**,
porque es una regla genérica y reutilizable. Se pediría por mensaje (p. ej.
`split: "by_size"`); el servicio repartiría los adjuntos en N mensajes con
los mismos destinatarios y asunto con sufijo `(1/N)`. Sin la opción, el
comportamiento sigue siendo el rechazo (cambio compatible). A definir
entonces: un adjunto solo de más de 25 MB (no se puede dividir), cómo se
agrupan los mensajes en el seguimiento y cómo se reprocesa una parte.

## Pendientes

- Orden de construcción de las plantillas (propuesta abajo).
- Esperas entre reintentos.
- Prefijo de rutas (`/notificaciones`) y nombre del schema SQL.
- Registrar `notifications.*` en el catálogo de auth (cambio en otro
  servicio, paso aparte).
- Credenciales máquina en auth.
