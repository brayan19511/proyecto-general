# Requisitos de identidad y acceso

Estado: requisitos objetivo. Solo se conservan los modelos y un esqueleto mínimo; no hay flujos implementados. El usuario codifica por pasos con guía del asistente. Recomendaciones pendientes no se convierten en requisitos definitivos sin confirmación.

## Alcance

Identidad global y acceso multiempresa mediante usuarios, perfiles, organización, roles heredados, sesiones y API keys. Implementación prevista: Python + FastAPI.

## Registro y acceso

- Registro y login públicos; sin invitaciones ni verificación de email en la primera versión.
- Email único según política de normalización documentada; password almacenado como hash.
- No conceder membresías por dominio del email ni tratar el correo como verificado.
- La cuenta sin empresa puede iniciar sesión y gestionar su perfil; no accede a recursos empresariales.
- Un administrador autorizado añade al usuario ya registrado a su empresa y le asigna puestos.
- La búsqueda de usuarios para incorporación debe ser acotada a administradores autorizados; no se ofrece un directorio público.
- Registro público no incluye creación pública de empresas. Bootstrap y alta inicial se hacen mediante procedimiento administrativo controlado.
- La recuperación de cuenta queda pendiente; no se simula enviando claves ni confiando solo en documentos personales.

## Empresas y permisos

- Usuario → membresía → puestos → roles → permisos.
- Cada puesto pertenece a un área de una empresa; los roles son de esa empresa.
- Un usuario puede ocupar varios puestos y pertenecer a varias empresas.
- La unión de permisos conserva alcance propio/área/empresa; no se mezclan empresas.
- Sin roles directos a usuarios inicialmente.
- El administrador solo delega permisos que está autorizado a conceder.
- Evitar que una operación ordinaria deje una empresa habilitada sin administrador efectivo; procedimiento extraordinario de recuperación separado.
- Desactivar usuario, empresa, membresía, área, puesto o rol impide utilizar los accesos dependientes. Desactivar un padre no borra ni altera automáticamente todas las filas hijas.

## Perfiles y documentos

- Datos personales opcionales separados de las credenciales.
- País de residencia, nacionalidad y país emisor son conceptos distintos.
- Tipos documentales en catálogo por país emisor, con etiqueta local y código estable.
- DNI puede existir para Perú y España como entradas distintas; no hay documento ni país obligatorio universal.
- Números como texto, preservando ceros; reglas específicas por tipo, nunca una validación global de ocho dígitos.
- Documento opcional en el registro; formato válido no equivale a identidad verificada.

## Sesiones

- Máximo predeterminado de 3 sesiones, configurable por usuario. Quién lo modifica y mediante qué interfaz se acordará. Rechazar el cuarto login es una propuesta pendiente, frente a revocar la sesión más antigua.
- El conteo excluye sesiones vencidas, revocadas y dadas de baja; la creación debe protegerse frente a logins concurrentes.
- Antes de permitir reducir el límite se decidirá cómo reconciliar sesiones existentes y auditarlo; no revocar sesiones silenciosamente por una configuración nueva.
- Registrar IP inicial, IP observada más reciente, descripción del cliente y última actividad.
- IP detrás de proxy solo desde proxies confiables; cambio de IP no revoca por sí mismo una sesión.
- Duración acordada de 5 horas; confirmar si absoluta o por inactividad. Quince minutos de JWT es una propuesta pendiente. Mantener duración finita de credenciales.
- Logout/revocación debe invalidar renovaciones; se decidirá la comprobación de JWT ya emitidos y su ventana de propagación. Consulta persistente sin caché es una propuesta inicial.
- La futura rotación de refresh debe ser atómica; la política ante reutilización se explicará y acordará.

## API keys

- Hasta cinco activas y vigentes por usuario en total inicialmente; límite configurable por administración de plataforma.
- Vinculadas a una membresía y empresa; scopes nunca superiores a permisos actuales.
- Creación con expires_at, duración relativa o ninguna: convertir duración a fecha; ausencia de ambas representa expires_at=null. Rechazar fecha y duración simultáneas o fechas pasadas.
- Sin vencimiento no significa irrevocable. Baja del usuario o membresía y pérdida de permisos siguen siendo efectivas.
- Se muestra secreto una sola vez; guardar hash y prefijo identificable.
- Revocación irreversible de esa credencial: para reemplazarla se crea otra clave.
- No se permite exceder el límite mediante solicitudes concurrentes.
- Cambiar defaults no modifica silenciosamente las expiraciones de claves existentes.

## Rate limit

- Auth protege registro, login y renovación aunque se exponga sin central.
- La API central aplicará límites agregados distintos; otros servicios sus límites propios.
- Utilidad propia por ruta y contadores compartidos; algoritmo portable entre PostgreSQL y SQL Server por diseñar. Redis es futuro. SQLite queda excluido.
- Distinguir namespaces para evitar doble conteo de la misma política.
- 429 para exceso; registrar evento contextual sin secretos y sin crear un evento histórico por cada incremento de contador.
- Bloqueo tras 5 contraseñas fallidas acordado; ventana y duración pendientes. Quince minutos fue una recomendación. Límites por IP, protección del identificador almacenado y política ante fallos se decidirán con el usuario antes de implementarlos.

## Bajas, atribución e historial

- No eliminar filas físicamente ni mediante cascadas. DELETE fija is_active=false, deleted_at y deleted_by.
- Todas las tablas y relaciones llevan los campos comunes del modelo; los eventos históricos son inmutables tras insertarse.
- Las fechas/actores los asigna el servidor, no el body del cliente.
- Conservar valores anteriores/nuevos permitidos de cambios de negocio, además de quién creó y quién actualizó por última vez.
- Conservar revocaciones, rotaciones y relaciones dadas de baja. Nunca copiar secretos o hashes de credenciales a snapshots de historial.
- El cambio y su historial se confirman juntos. Si falla el historial de una mutación crítica, la transacción no se confirma.
- Actualizaciones operativas frecuentes como last_seen pueden agruparse; no se promete conservar cada heartbeat ni cada incremento de Redis como evento histórico.
- El email permanece reservado tras una baja: una cuenta nueva no reemplaza a la anterior usando el mismo email.
- Historial consultable solo por actores autorizados y dentro del alcance empresarial aplicable.

## Criterios de aceptación

1. Registrarse no da acceso a ninguna empresa sin asignación administrativa.
2. No hay flujo de invitación ni bloqueo por email sin verificar.
3. Una baja en A no afecta los permisos legítimos en B.
4. El mismo nombre documental en países distintos no genera colisión de catálogo.
5. Dos logins o creaciones de claves concurrentes respetan los máximos.
6. Una API key sin vencimiento funciona mientras esté autorizada; revocarla impide su uso.
7. DELETE conserva filas, referencias, actor y fecha; las consultas ordinarias excluyen bajas.
8. Se puede reconstruir quién cambió un rol y sus valores anteriores/nuevos sin revelar secretos.
9. Ningún usuario puede falsificar created_by, updated_by ni company_id autorizado.
10. Los logs propios incluyen contexto permitido y no sustituyen la persistencia de cambios.

## Pendientes

Recuperación de cuenta, catálogos, credenciales máquina, revocación en consumidores, transporte web, mecanismo de seed y portabilidad de base. También falta confirmar duración absoluta/inactividad, exceso de sesiones y ventana/duración del bloqueo. No implementar estos puntos por inferencia.

## Integración con la plataforma

Auth debe funcionar y probarse independientemente de la API central.

Al implementar su base técnica deberá:
- Exponer un contrato OpenAPI con identificadores de operación estables.
- Documentar solicitudes, respuestas y errores.
- Incorporar Dockerfile y configuración de ejemplo sin secretos.
- Proporcionar comprobaciones de disponibilidad y preparación.
- Mantener separados los endpoints públicos, administrativos e internos.
- Implementar logs, logs_detail y logs_steps propios con nombre y versión del servicio, sin OpenTelemetry.
- Propagar el contexto de trazas en comunicaciones salientes.

La API central consumirá el contrato de auth sin acceder a sus tablas.
No se requiere implementar la central para completar auth.

## Cliente web y seed

- Cliente web acordado; transporte de tokens y protección CSRF a explicar y confirmar. No existe frontend.
- Seed explícito, transaccional e idempotente para administrador y estructura mínima. El usuario desea evaluar una ruta API; autorización del primer acceso, habilitación y cierre del bootstrap pendientes. CLI es alternativa. Sin contraseñas fijas ni elevación automática de cuentas públicas preexistentes.
- Python/FastAPI y modelos SQLAlchemy conservados. PostgreSQL inicial y SQL Server como objetivo de portabilidad; sin SQLite. Drivers, migraciones y librerías de seguridad se incorporarán solo al paso que las necesite y con explicación. Seguimiento y límites propios, sin OpenTelemetry.

## Entrega funcional inicial

Hoja de ruta orientativa, no implementación automática: entender modelos, conectar la base elegida, acordar migraciones y seed, construir registro, login, sesiones y después autorización empresarial. Cada paso requiere explicación y solicitud explícita antes de editar. Los modelos no garantizan las reglas sin lógica y pruebas posteriores.

La API de membresías permite asignar puestos cuyos permisos el administrador puede delegar, sin mezclar empresas. Las consultas empresariales verifican todas las relaciones activas. Se protege al último administrador mediante bloqueo transaccional de la empresa.

## Seguimiento propio

Middleware de operaciones HTTP y pasos manuales. Cabecera logs con operación/trace/padre y duración monotónica. Detalles/pasos anexados en transacciones técnicas independientes; una caída no se interpreta como ejecución activa. No capturar automáticamente JSON de solicitudes/respuestas, headers, query strings ni excepciones crudas. Los pasos iniciales registran exclusivamente metadatos autorizados.

Historial de negocio separado y transaccional. Cambiar datos sin poder anexar el historial provoca rollback. Logs técnicos inaccesibles por endpoints públicos; no se implementa todavía consulta agregada entre servicios.
