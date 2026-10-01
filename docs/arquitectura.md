# Arquitectura general

## Estado y colaboración

Este documento describe el objetivo de la plataforma, no funciones implementadas. El estado real de cada servicio está en readme.md (raíz) y en el readme de cada servicio. El usuario escribirá el código; el asistente explica/revisa y consulta antes de implementar o modificar el diseño. Avanzar un paso pequeño por vez según AGENTS.md.

## Estado y componentes

Plataforma multiempresa con servicios y despliegues independientes. Auth, la API central y libro-mayor utilizan Python + FastAPI. El lenguaje de los servicios futuros se decidirá por proyecto.

Componentes previstos:
- Identidad y acceso: usuarios, empresas, organización, autorización, sesiones y API keys.
- API central: entrada de clientes, límites generales, enrutamiento y coordinación.
- Libro mayor / gastos (`services/libro-mayor`, Python + FastAPI): lee SAP Business One HANA en solo lectura, sincroniza y clasifica gastos con reglas, y los consulta filtrados por área. Implementado y publicado en la central (`LIBRO_MAYOR_ENABLED`).
- Documentos e IA: extracción, validación y análisis de PDFs e imágenes mediante herramientas y proveedores como Gemini u OpenAI.
- Seguimiento propio: logs, logs_detail y logs_steps locales a cada servicio, con correlación entre llamadas. Sin OpenTelemetry ni plataforma de logs externa obligatoria.

PostgreSQL está previsto para persistencia, Redis para contadores/caché compartidos y RabbitMQ para trabajos cuando se incorporen. No todos deben instalarse en la primera entrega.

PostgreSQL se ejecutará en un contenedor separado. Se busca permitir SQL Server mediante configuración por despliegue, sujeto a revisión de tipos, restricciones, drivers y pruebas en ambos motores. No usar SQLite. No se promete que cambiar una URL migre datos ni resuelva diferencias del motor. Bases distintas por empresa dentro de una misma instalación requieren una decisión adicional. Auth ya no usa restricciones diferidas; sus tablas se crearon en PostgreSQL y siguen sin validarse en SQL Server.

La documentación de esta carpeta es la fuente vigente. general.txt es un antecedente descartado. Se mantiene un repositorio con proyectos independientes bajo services/; no es necesario otro chat ni otro repositorio por servicio. Se priorizan soluciones sencillas y dependencias justificadas: framework HTTP, persistencia, migraciones y criptografía mantenida. El comportamiento de negocio, seguimiento y límites se controla desde el código propio.

## Comunicación y versiones

HTTP y OpenAPI para operaciones rápidas; mensajes para procesos largos. Cada servicio es propietario de sus tablas. Compartir instancia de base de datos no autoriza acceso cruzado a tablas.

Las tablas de negocio, catálogos y logs de auth pertenecen al schema SQL `auth`.
Se declara una sola vez en Base.metadata; los modelos lo heredan. Alembic limita
la comparación a ese schema y a las tablas declaradas para evitar incluir datos
de otros servicios. No se crea un schema master ni uno por empresa. Declarar el
schema en Python no lo crea en la base: la primera migración de auth lo crea
antes de las tablas. No se modifica el search_path del servidor.

Las versiones de despliegue son independientes de las versiones de API. Los cambios compatibles no requieren migrar consumidores. Los incompatibles requieren contratos y transición explícitos. Se identifican consumidores afectados, se prueban contratos y se contemplan migraciones compatibles durante despliegues.

## Identidad y acceso empresarial

Registro y login públicos, sin invitaciones ni verificación de correo en la primera versión. Un email registrado no demuestra su titularidad y no se utilizará como prueba de pertenencia empresarial ni para vincular automáticamente cuentas externas.

Un usuario puede existir sin empresas. Un administrador autorizado concede acceso a una empresa y asigna puestos. La autenticación por sí sola no permite consultar recursos empresariales.

```text
Usuario → Perfil
Usuario → Membresías en empresas
Empresa → Áreas → Puestos
Membresía → Asignaciones a puestos
Puesto → Roles → Permisos
```

Los permisos se combinan dentro de la empresa activa y conservan su alcance propio/área/empresa. No se asignan roles directamente al usuario en la primera versión, con una excepción acordada: el master admin (`users.is_platform_admin` en auth), que accede a todas las empresas sin puestos. Solo lo otorga el seed y sigue requiriendo login y sesión válida. Un administrador solo gestiona dentro de su alcance y no concede privilegios superiores a los que está autorizado a delegar.

Se prevé un seed administrativo explícito para la primera empresa y su administrador, con membresía, área, puesto, rol y permisos mínimos. Debe ser transaccional e idempotente; una repetición no cambia contraseñas, no reactiva cuentas ni restituye privilegios retirados. Cada servicio conserva su seed y solo modifica sus propias tablas. Decisión del usuario: en auth el seed será una ruta API `/seed` idempotente. Su autorización inicial, habilitación y cierre tras el bootstrap deben acordarse antes de implementarla. No habrá credenciales fijas ni creación pública de administradores.

## Documentos personales internacionales

Catálogo de países y tipos documentales por país emisor. Un tipo tiene código estable, nombre local y categoría genérica: identidad nacional, residencia, pasaporte u otra.

Ejemplos de catálogo, no defaults: PE/DNI, ES/DNI. El identificador interno del usuario es independiente de sus documentos. El despliegue en otro país no exige cambiar modelos, solo catálogo y validaciones aplicables.

El número es texto; la validación y normalización son específicas del tipo. No se asume longitud universal, no se eliminan ceros iniciales y un formato válido no implica verificación oficial. Los documentos son opcionales para registrarse en esta entrega.

## Credenciales y sesiones

Acuerdos: cliente web, sesiones de 5 horas y máximo predeterminado de 3 configurable por usuario. La arquitectura contempla JWT de firma asimétrica, refresh tokens almacenados como hash y sesiones revocables. Pendiente de confirmar: duración absoluta o por inactividad, vida del access token, comportamiento al alcanzar el máximo y política de reutilización. Propuestas anteriores del asistente: 5 horas absolutas, access de 15 minutos, rechazar el cuarto login y revocar sesión ante reutilización de refresh. No se implementan sin revisarlas con el usuario.

La opción de duración infinita solicitada se aplica a API keys: expires_at=null. No significa permiso permanente: revocación, baja o pérdida de membresía/roles siguen anulando el acceso.

Propuesta de transporte pendiente: access Bearer en memoria y refresh en cookie HttpOnly/Secure, con política SameSite, Origin y CSRF según topología web. Se explicará antes de elegirlo. Los campos del modelo relativos a CSRF no representan un flujo ya implementado.

La revocación requiere comprobar estado persistente o definir una ventana de caché; verificar solo un JWT no garantiza revocación inmediata. Se propone comenzar consultando usuario/sesión y relaciones actuales sin caché, y confirmar esta política con el usuario al implementar. Los consumidores futuros también deberán validar emisor, destinatario, firma y vencimiento, además del estado necesario.

HTTPS protege el transporte; no concede permisos al llamante. Las operaciones de usuario propagan una credencial validable. Las operaciones automáticas requieren identidad de servicio y permisos propios, separados de las API keys personales. No se confía en headers de usuario/empresa sin autenticar su origen. El mecanismo de credenciales máquina se implementará al integrar el primer consumidor.

Las API keys se vinculan a usuario, membresía y empresa, con hasta cinco activas y vigentes por usuario inicialmente. Reciben scopes limitados, fecha de expiración opcional y revocación. Los permisos efectivos siempre se intersectan con los actuales de la membresía.

## Rate limit y consumo

- API central: límites generales por IP antes de autenticación y por usuario/API key/empresa después de validarla.
- Auth: límites propios de registro, login y renovación, incluso mientras no exista central. Para login combina IP e identificador normalizado sin usar el email como etiqueta pública.
- Otros servicios: límites específicos de operación, tamaño, coste y concurrencia.

Se prevé una utilidad propia pequeña por lenguaje con políticas por ruta. Los contadores compartidos pueden persistirse en la base relacional; el algoritmo transaccional debe revisarse para PostgreSQL y SQL Server. No depender solo de memoria de proceso. Redis es futuro, no requisito. Los límites central y local tendrán namespaces diferentes; un rechazo por límite devolverá 429 y política de reintento aplicable.

Login: el usuario acordó bloquear tras cinco fallos. Ventana, duración y desbloqueo permanecen pendientes; quince minutos de ventana/bloqueo fue una recomendación, no una decisión confirmada. El bloqueo no equivale a baja lógica de la cuenta. Los valores por IP y comportamiento ante caída del almacenamiento se explicarán y acordarán al implementar.

La falta de Redis tiene una política explícita por ruta antes de producción. Los límites de sesión y de cinco API keys son restricciones persistentes y transaccionales, no simples contadores de rate limit.

Cuotas y consumo exacto se guardan aparte, deduplicados por operación. Las cuotas estrictas reservan capacidad antes de ejecutar y la confirman o liberan al finalizar.

## Persistencia, atribución e historial

No hay borrado físico de registros de aplicación mediante operaciones ordinarias, purgas automáticas o cascadas. DELETE es baja lógica. Se conservan relaciones y referencias históricas.

Las entidades mutables y tablas de relación incluyen id, is_active, created_at, created_by, updated_at, updated_by, deleted_at y deleted_by. Fechas UTC; actores obtenidos del servidor. is_active=false deshabilita; deleted_at distingue baja lógica de suspensión. La baja también fija is_active=false.

Cada servicio puede resolver actores mediante un catálogo local de referencias a usuarios, servicios y sistema; no necesita una clave foránea a la base de datos de auth.

Decisión en auth: no hay catálogo de actores. created_by, updated_by y deleted_by son claves foráneas nullable a auth.users. Toda operación queda atribuida a un usuario: el autorregistro se atribuye al usuario creado y las operaciones administrativas al usuario autenticado. Solo hay NULL en los registros creados por el seed de bootstrap y en los contadores anónimos de intentos de login (estado operativo, sin identidad validada). Si en el futuro auth necesita atribuir procesos automáticos o servicios, se revisará esta decisión.

Los eventos históricos son solo anexado. Por convención incluyen los campos comunes: al insertarse updated_at=created_at, updated_by=created_by, is_active=true y deleted_at/deleted_by nulos. No se modifican posteriormente. Una corrección es otro evento.

Un registro de cambios conserva acción, actor, entidad, fecha y valores anteriores/nuevos permitidos. Esto es adicional a updated_by, que solo identifica la última actualización. Se excluyen secretos y hashes de credenciales de snapshots. Para rotación de credenciales se registra el cambio, no el secreto.

Las relaciones dadas de baja no se eliminan. Al restaurarlas se valida autorización y unicidad y se genera historial. Rehabilitar un padre no restaura automáticamente credenciales revocadas ni relaciones dadas de baja.

La política de no eliminación cubre las tablas persistentes de aplicación. Cachés, contadores con TTL y telemetría no sustituyen el historial y tienen retención propia. No se implementa un proceso de borrado o anonimización de datos personales sin decisión explícita posterior.

## Observabilidad y actividad

Plan detallado y decisiones pendientes: [plan-observabilidad.md](plan-observabilidad.md).

Implementado en auth con el paquete compartido `packages/platform-audit`: tablas técnicas en el schema `audit` (propiedad del paquete, no de un servicio): logs (cabecera de la operación y tiempos), logs_detail (request, response, error y mensajes) y logs_steps (eventos manuales de inicio/fin de pasos). Cada servicio escribe y consulta solo sus filas (columna service). Una solicitud a la central y cada llamada a un servicio son operaciones distintas relacionadas por trace_id, operation_id y parent_operation_id. Ninguna fila es actualizada por varios servicios.

El middleware genera identificadores en el borde público; solo acepta identificadores entrantes tras autenticar un servicio confiable. Correlación nunca equivale a autorización. Las futuras llamadas HTTP propagarán X-Trace-Id y X-Parent-Operation-Id; la integración autenticada se implementará con su primer consumidor. El tiempo de pared UTC permite ordenar eventos; la duración se mide con reloj monotónico. Las horas de distintos servidores requieren sincronización y no permiten por sí solas inferir duraciones.

La cabecera puede cerrarse actualizando estado, fin y duración; detalles y pasos son de solo anexado. Un paso abierto significa ausencia de cierre registrado, no prueba que siga ejecutándose. Una caída puede dejar operaciones abiertas; los trabajos largos tendrán su propio estado/heartbeat, separado de estos logs.

Por decisión del usuario se guardan parámetros, headers y bodies, siempre enmascarados y con límite de tamaño: tokens, cookies, passwords, keys, emails y números de documento se reemplazan por `***`; los headers siguen una lista positiva; bodies de más de 4 KB o no JSON solo registran tipo y tamaño; de las excepciones, solo el tipo. Un fallo de logging técnico emite aviso saneado y no deshace negocios confirmados. Las tablas técnicas persistentes no se purgan automáticamente; cualquier retención/purga futura se decide explícitamente.

El historial de negocio es independiente: los cambios críticos y su evento se confirman en la misma transacción, con actor y snapshots permitidos. Si posteriormente se publican, se incorporarán outbox y deduplicación. No se crea ahora un servicio central de auditoría. La vista conjunta futura consultará APIs internas autorizadas o una ingesta diseñada para tolerar fallos; nunca tablas ajenas.

## Documentos y trabajos futuros

Los archivos se almacenarán inicialmente en base de datos detrás de una interfaz migrable a almacenamiento compatible con S3. Base64 no es obligatorio; los consumidores usan identificadores, no detalles físicos.

Los trabajos tendrán estado persistente antes de procesarse, progreso, resultado, idempotencia y detección de interrupciones. La coordinación entre persistencia y cola debe evitar trabajos aceptados sin ejecutar. La finalización HTTP es distinta de la del trabajo.

## Pendientes de implementación

- Construcción y validación del servicio auth según su README y requisitos.
- Credenciales máquina y consulta agregada de logs al incorporar consumidores.
- Catálogo inicial de países/tipos realmente soportados.
- Procedimiento de recuperación de cuenta sin presumir verificación de email.

## Integración configurable de servicios

La plataforma permitirá seleccionar versiones de imágenes por servicio
mediante configuración de despliegue.

Se distinguen tres elementos:

- Versión de imagen: identifica el código que se ejecuta.
- Versión de contrato: identifica las operaciones, entradas y respuestas.
- Configuración de integración: indica URL, habilitación y timeouts.

Cambiar una imagen por una versión compatible no debe exigir cambios
en el código de la API central. Los cambios incompatibles requieren
actualizar el consumidor o mantener temporalmente el contrato anterior.

La API central tendrá adaptadores por servicio. Compartirá utilidades
de comunicación, autenticación y observabilidad para evitar duplicación.

Cuando la central utilice o transforme datos, sus clientes consumirán
contratos OpenAPI versionados; generar clientes es opcional si aporta valor.
Descargar una imagen no genera automáticamente tipos ni integraciones.

Una integración nueva requiere configurar explícitamente rutas,
autorización, contrato y comportamiento ante errores. No se expondrán
automáticamente todos los endpoints de un servicio.

Cada servicio deberá proporcionar:
- Rutas bajo un prefijo propio con su nombre (auth: `/auth/...`), para que la central enrute por prefijo sin reescribir rutas.
- Contrato OpenAPI.
- Configuración por entorno.
- Imagen Docker independiente.
- Comprobaciones de disponibilidad y preparación.
- Identificación del nombre y versión del servicio en logs propios.
- Propagación del contexto de trazas.
- Errores públicos documentados, sin detalles internos sensibles.

La configuración de despliegue incluirá imágenes con versiones fijas,
redes, dependencias, secretos y comprobaciones de salud. Las imágenes
deben existir y sus migraciones deben ejecutarse mediante un proceso
definido.

Los servicios deshabilitados no recibirán tráfico desde la central.
Habilitar una integración no concede permisos a usuarios o empresas.
Implementado en la central: `<SERVICIO>_ENABLED` por configuración (hoy
`AUTH_ENABLED` y `LIBRO_MAYOR_ENABLED`), timeout por servicio y por ruta,
respuestas en streaming y estado en su schema `gateway` administrable sin reinicio
(releído cada 5 s). Deshabilitado, sus rutas responden 503 sin contactarlo y el
servicio sigue corriendo. Auth solo se deshabilita por configuración. La
central también mantiene una lista negra de IPs/rangos (`gateway.ip_blocks`,
403 antes de enrutar). Detalle y administración:
services/apigateway/docs/modulos-y-administracion.md.

No se construirá inicialmente un sistema de plugins dinámicos.
Se comenzará con configuración explícita y adaptadores pequeños.

Para enrutamiento simple se prevé un catálogo configurable con nombre, URL interna, rutas/métodos públicos permitidos, autorización, contrato y timeout. Se admite redespliegue para aplicar cambios inicialmente. Incorporar un servicio compatible puede requerir solo imagen y catálogo; combinar operaciones requiere código explícito. No se implementa descubrimiento Docker ni dependencias como Traefik en esta entrega.

Timeout predeterminado de 30 segundos configurable por operación, con presupuesto total para evitar sumar esperas ilimitadas. Cero reintentos automáticos por defecto; solo habilitarlos para operaciones seguras/idempotentes. Contraseña errónea no es un fallo de dependencia. Una dependencia caída produce error controlado; un trabajo largo se acepta con identificador persistente y se consulta después. Bases de datos, colas y archivos no residen exclusivamente en la memoria o filesystem efímero de una réplica.


| Central | Servicios |
|---|---|
| Entrada pública y CORS para su cliente web | Operaciones y reglas propias |
| Límites generales | Protecciones específicas |
| Enrutamiento y combinación de respuestas | Autorización sobre sus recursos |
| Propagación de identificadores de seguimiento | Logs internos e historial propio |
| Coordinación entre servicios | Persistencia de sus datos |