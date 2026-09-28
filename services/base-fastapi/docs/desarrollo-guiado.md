# Desarrollo guiado de auth

## Acuerdo de colaboración

El usuario escribe el código. El asistente explica y revisa, y pide conformidad antes de cambiar modelos, reglas de negocio o decisiones técnicas. Una consulta no autoriza a implementar. Cada paso debe ser pequeño, verificable y entendible antes de avanzar.

Las instrucciones permanentes están en AGENTS.md raíz y en el de auth. Este documento explica el código y las opciones; no autoriza su implementación.

## Estado actual y limpieza

Actualización posterior: el usuario añadió parámetros de BD/CORS en config.py
y app/core/db/connection.py. La descripción de la limpieza y la configuración
mínima siguiente documenta la etapa anterior. Para el estado vigente y los pasos
de comprobación/migraciones consultar [base-de-datos.md](base-de-datos.md).

Se conservan modelos SQLAlchemy, campos comunes, main.py mínimo y config.py mínimo. Se retiró la implementación anticipada de HTTP, autenticación, seed, business, logs, rate limiting, conexión, migraciones y Docker. No hay conexión, migraciones ejecutadas ni servicio de autenticación funcional.

Se conservó el archivo .env del usuario sin leerlo ni modificarlo durante la limpieza. La configuración actual ignora campos desconocidos. requirements.txt declara solo las dependencias del esqueleto; el entorno local puede conservar paquetes instalados anteriormente. No se desinstalaron.

## AuthSession

Representa un inicio de sesión de un usuario, por ejemplo en un navegador. Una sesión no equivale a cada petición ni a cada pestaña; el cliente suele compartirla entre pestañas.

- user_id: dueño de la sesión.
- expires_at: instante en que deja de ser válida.
- revoked_at: cierre anticipado explícito, por logout o revocación.
- csrf_hash: propuesta de comprobación para renovaciones autenticadas con cookie. Se conserva el campo del modelo, pero el transporte aún debe decidirse.
- initial_ip / last_ip: IP inicial y última observada. No identifican de forma fiable un dispositivo.
- client_description: descripción del navegador/cliente, declarada por este y no confiable para autorizar.
- last_seen_at: última actividad registrada; no modifica por sí sola la expiración.
- Campos heredados: actor, fechas, habilitación y baja lógica.

Ejemplo: el usuario entra a las 09:00 y la sesión vence a las 14:00 si acordamos cinco horas absolutas. Tener esa fila permite contar sesiones, consultar cuáles existen y revocar una. Debemos confirmar si las cinco horas son absolutas o por inactividad.

is_active, deleted_at, expires_at y revoked_at no son equivalentes. Un registro activo puede estar vencido; la autorización futura deberá comprobar todos los estados pertinentes.

## RefreshToken

Es una credencial para obtener otro access token sin volver a introducir contraseña. No concede una sesión nueva ni más horas automáticamente.

- session_id: sesión a la que pertenece.
- token_hash: resumen criptográfico del secreto; no el secreto utilizable.
- consumed_at: indica si ya se utilizó para renovar.

Ejemplo de rotación: se entrega R1; al usar R1 se marca consumido y se entrega R2. Se conserva R1 para detectar su reutilización. La revocación de la sesión inutiliza sus renovaciones.

Una sesión puede tener muchos registros de renovación a lo largo de su vida, pero no deben aceptarse simultáneamente tokens consumidos. La implementación deberá resolver concurrencia, expiración y política frente a reutilización; el modelo por sí solo no lo garantiza.

## RateBucket

Un contador compartido para una política y una ventana temporal. Evita que cada réplica mantenga una cuenta diferente en memoria.

- key: identifica la política y el sujeto, por ejemplo login de un identificador normalizado.
- count: cantidad contada.
- window_start: inicio del período.
- blocked_until: fin de un bloqueo temporal, si corresponde.

No todos los contadores cuentan lo mismo: uno puede contar contraseñas fallidas y otro todas las solicitudes por IP. Usarán claves distintas.

El usuario fijó cinco fallos; la ventana y duración del bloqueo siguen pendientes. Un hash simple de email no hace anónimo ese dato frente a ataques de diccionario; la identificación del contador y su protección se decidirán al implementarlo.

La tabla no incrementa de forma atómica por sí misma. Diseñaremos transacciones compatibles con los motores previstos cuando lleguemos a ese paso. No hay Redis ni SQL específico de PostgreSQL implementado.

## ChangeHistory

Conserva cambios de negocio, independiente de los logs técnicos.

- action: qué ocurrió, por ejemplo membership.deactivated.
- resource_id: registro afectado; se interpreta junto con la acción.
- company_id: empresa afectada, cuando corresponde.
- trace_id: vínculo con el recorrido técnico, cuando existe.
- before / after: valores anteriores y nuevos de campos permitidos.
- created_by y created_at heredados: quién hizo el cambio y cuándo.

Ejemplo: registrar que una membresía cambió de is_active=true a false. Nunca almacenar contraseñas, hashes de credenciales ni tokens en before/after. El cambio y su evento deberán guardarse en la misma transacción.

Los nombres action y resource_id necesitan convenciones claras. No implementamos ahora un sistema genérico que capture automáticamente todas las columnas.

## Protección de eventos históricos

El código conservado es:

```python
def reject_change(*_):
    raise ValueError("Los eventos históricos son de solo anexado")

for immutable in (ChangeHistory, LogDetail, LogStep):
    event.listen(immutable, "before_update", reject_change)
    event.listen(immutable, "before_delete", reject_change)
```

event.listen registra una función que SQLAlchemy llama antes de actualizar o eliminar objetos de esas clases durante su flush. reject_change detiene la operación lanzando una excepción.

*_: recibe los argumentos posicionales del evento (mapper, conexión y objeto), aunque no necesitamos utilizarlos. No es una instrucción SQL.

No se bloquea INSERT: se permiten nuevos eventos. Corregir un historial significa añadir otro evento, no reescribir el anterior. Log no está incluido porque su cabecera puede pasar de iniciada a terminada; LogStep registra inicio y fin como filas distintas.

Límite importante: estos eventos NO protegen escrituras SQL directas ni operaciones masivas que eludan ese ciclo ORM. Tampoco reemplazan permisos de base de datos. No se afirma inmutabilidad total. La protección adicional se acordará antes de persistir historial.

Referencia: [eventos ORM de SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/events.html).

## Seed: ruta o comando

Un seed prepara los datos iniciales; no es lo mismo que una migración, que crea/modifica estructura.

Se desea crear el administrador y la estructura mínima que lo autoriza: empresa, membresía, área, puesto, rol y permisos. Debe poder repetirse sin duplicar ni restituir privilegios retirados.

El usuario prefiere evaluar una API. Es posible, pero hay dos casos:

1. Primera instalación sin administrador: una ruta necesita un mecanismo de bootstrap distinto al login normal, por ejemplo habilitación temporal y secreto de un solo uso entregado fuera de la API. Requiere controlar repeticiones y carreras.
2. Sistema ya iniciado: una operación administrativa puede exigir autenticación y autorización existentes.

Un comando local evita exponer una ruta de bootstrap, pero también debe estar limitado a operadores autorizados. La elección permanece pendiente. No se implementó ninguna opción. Nunca una ruta pública que cree administradores solo porque todavía no hay uno.

## Configuración mínima actual

| Variable | Para qué sirve | Default | ¿Necesaria ahora? |
| --- | --- | --- | --- |
| PROJECT_NAME | Título mostrado por FastAPI en /docs | Auth | Opcional |

SettingsConfigDict permite leer .env. extra="ignore" ignora ajustes adicionales antiguos; no los activa. No se configura aún una conexión, JWT, CORS ni políticas.

## Configuraciones retiradas: explicación para cuando hagan falta

Estas variables NO están activas. Los valores fueron propuestas del asistente, no decisiones que deban conservarse sin revisión.

| Variable anterior | Propósito | Cuándo se evaluará |
| --- | --- | --- |
| database_url | Motor, driver y destino de conexión | Al conectar PostgreSQL; no implica migrar datos automáticamente |
| jwt_private_key_file | Ruta a la clave privada con la que auth firma JWT | Si confirmamos firma asimétrica; el secreto no se distribuye a consumidores |
| jwt_public_key_file | Ruta a la clave pública para verificar firmas | Junto con JWT; se deriva del par de claves, no es contraseña |
| jwt_issuer / jwt_audience | Emisor permitido y destinatario del token | Al definir contrato de autenticación entre servicios |
| jwt_key_id | Identificador de la clave, útil para rotación | Al diseñar gestión de claves |
| access_minutes | Vida del access token, distinta de la sesión | Se propusieron 15 minutos; pendiente |
| session_hours | Duración de la sesión | Se acordaron 5 horas; falta definir absoluta/inactividad |
| max_sessions | Máximo predeterminado de sesiones | Se acordaron 3 y override por usuario |
| login_failures | Fallos que disparan bloqueo | Se acordaron 5 |
| login_window_seconds | Período en el que se cuentan esos fallos | Propuesta anterior: 900 segundos; pendiente |
| login_block_seconds | Duración del bloqueo | Propuesta anterior: 900 segundos; pendiente |
| login_ip_limit / register_ip_limit / refresh_ip_limit | Límites por IP y operación | Valores pendientes; no confundir con fallos de contraseña |
| cors_origins | Orígenes web autorizados a usar la API desde navegador | Cuando exista integración web; CORS no autentica |
| cookie_secure | Restringir cookie a HTTPS | Si se confirma transporte por cookie |
| service_name / service_version | Identificar servicio y versión en logs | Cuando se implemente seguimiento |
| http_timeout_seconds | Máximo de espera de llamadas salientes | Default general deseado: 30 segundos; por operación cuando haga falta |
| max_request_bytes | Límite de tamaño de solicitudes | Al definir endpoints y sus entradas |
| environment | Diferenciar entornos de ejecución | Solo si hay comportamiento que lo necesite |

No agregaremos todas estas variables a la vez. Una política configurable por usuario requiere persistencia propia; una variable de entorno solo da el default del despliegue.

## business.py retirado

Agrupaba reglas de negocio: comprobar habilitación/baja, calcular permisos heredados, comprobar delegación y registrar historial. No era una librería ni una obligación arquitectónica.

Se retiró. Cuando aparezca una regla real, se escribirá una función pequeña con nombre claro, explicando entradas, salida y autorización. Solo se separará a otro módulo si mejora la lectura o evita repetición real.

## PostgreSQL y SQL Server

Objetivo: elegir motor por configuración en un despliegue nuevo, con modelos y consultas portables en la medida posible. No usar SQLite. No acceder a tablas de otros servicios.

SQLAlchemy ayuda a adaptar SQL al motor, pero no garantiza que cambiar una URL baste. Cambian drivers, tipos, restricciones y comportamiento transaccional. Cambiar un sistema ya poblado exige migrar sus datos.

Puntos concretos del modelo que debemos revisar juntos:

- AuditMixin conserva ForeignKey(..., deferrable=True, initially="DEFERRED"): no es una base portable a SQL Server; debemos decidir cómo crear actores y sus referencias sin depender de restricciones diferidas.
- DateTime(timezone=True) requiere revisar representación y normalización UTC en cada motor.
- JSON y cadenas Unicode necesitan verificar almacenamiento y consultas en ambos motores.
- Unicidad, aislamiento y bloqueo concurrente requieren pruebas en las dos bases.
- La protección ORM de historial no equivale a protección de base de datos.

Se conservó el esquema solicitado sin rediseñar estas partes unilateralmente. No hay migraciones ni se declara soporte operativo de SQL Server.

También falta distinguir: ¿un motor por instalación del producto, o bases diferentes por empresa dentro de la misma instalación? El segundo caso implica resolución de conexiones y una arquitectura distinta; no se implementará por inferencia.

Referencia: [SQL Server en SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/mssql.html).

## Orden propuesto, sin implementación automática

1. Entender AuditMixin/Actor y acordar los ajustes de portabilidad.
2. Conectar únicamente al contenedor PostgreSQL del usuario.
3. Acordar cómo crear el esquema y sus migraciones.
4. Decidir bootstrap API o comando y escribir el seed mínimo.
5. Construir registro; después login.
6. Incorporar sesiones, renovación y revocación paso a paso.
7. Construir permisos y auditoría sobre operaciones concretas.

Cada paso se explica y se acuerda antes de escribir código.

