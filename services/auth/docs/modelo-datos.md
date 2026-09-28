# Modelo de datos de auth

Python + FastAPI. Identificadores UUID v7 como texto de 36 caracteres y fechas UTC. Tablas creadas en PostgreSQL (schema auth) mediante Alembic.

## Estado del código

Las secciones numeradas describen el objetivo funcional, no una equivalencia exacta con entities.py.

Diferencias entre el objetivo y el código, a revisar juntos:
- Company añade code como identificador de seed. Role conserva solo code; Permission solo code. Descripciones y catálogo completo quedan pendientes.
- Profile implementa solo nombres/apellidos. Países y documentos siguen como propuesta documental, sin clases implementadas.
- Assignment no incluye starts_at/ends_at y usa unicidad permanente de la pareja; el diseño de períodos/reactivación debe acordarse antes de avanzar.
- Las relaciones PositionRole y RolePermission también usan unicidad permanente en el código; este documento describe unicidad activa como objetivo por revisar.
- No existe tabla actors (ver sección 1). Los campos de actor de AuditMixin son FK nullable a users.id, sin restricciones diferidas.
- Los defaults del mixin calculan created_at y updated_at por separado. UserService asigna explícitamente el mismo instante (`now`) a ambos; cada nueva operación debe hacer lo mismo.
- Los constraints no tienen nombres explícitos; ver la propuesta de naming_convention en base-de-datos.md.

Consulta [desarrollo-guiado.md](desarrollo-guiado.md) para la explicación y pendientes. No cambiar silenciosamente el modelo para resolver estas diferencias.

## Campos comunes en todas las tablas

| Campo | Uso |
| --- | --- |
| id | Identificador estable |
| is_active | Habilitación lógica; no sustituye validación de vencimiento o revocación |
| created_at / created_by | Fecha y actor creador |
| updated_at / updated_by | Fecha y actor de última actualización |
| deleted_at / deleted_by | Baja lógica opcional |

En el alta updated_at=created_at y updated_by=created_by. DELETE fija is_active=false y los campos de baja; no se ejecuta DELETE SQL. Los campos comunes se aplican también a tablas de relación, políticas y catálogos.

Un registro utilizable tiene is_active=true y deleted_at=null, además de cumplir sus reglas específicas. Una suspensión puede poner is_active=false sin deleted_at. Las restauraciones generan eventos y revalidan restricciones.

Las tablas históricas activity_events y change_history conservan los campos comunes pero son de solo anexado: se insertan activas, no se actualizan, no se dan de baja. Correcciones mediante nuevos eventos.

## 1. Atribución (decisión: sin tabla actors)

Se descartó el catálogo actors. created_by, updated_by y deleted_by son FK nullable a users.id.

| Caso | created_by / updated_by |
| --- | --- |
| Autorregistro | El propio usuario: se inserta, el flush genera su id y se asigna created_by = updated_by = user.id en la misma transacción |
| Operación de usuario autenticado | El usuario autenticado, obtenido en el servidor |
| Seed de bootstrap | NULL; sus eventos usan acciones `seed.*` |
| Contadores de login (`rate_buckets`) | NULL: la solicitud es anónima (aún no hay identidad validada). Es estado operativo, no historial de negocio |

Un NULL fuera de estos dos casos es un error de código, no una atribución válida. Si auth necesita atribuir procesos automáticos, servicios o intentos anónimos, se revisará esta decisión (no inventar un usuario para ello).

## 2. users

Campos específicos: email (único, incluye cuentas dadas de baja), password_hash, max_sessions opcional, is_platform_admin (master admin; default false, solo lo activa el seed; revisión b902cd601f20).

El service normaliza el email con `strip().lower()` antes de consultar y guardar. La columna normalized_email se eliminó (revisión 05514603cf38): email ya almacena el valor normalizado. El perfil y la autenticación no dependen de tener empresa. No hay verificación de email en esta entrega ni atributo que declare el correo verificado falsamente.

## 3. user_profiles

user_id (único), first_names, last_names, birth_date, phone, residence_country_code, nationality_country_code opcionales.

Si más adelante se requieren múltiples nacionalidades, se modelará una relación específica. Ningún campo del perfil concede autorización.

Implementado (revisión 28950766fbb9): first_names, last_names, birth_date y nationality_country_code (FK a countries.code). phone y residencia quedan pendientes.

## 4. countries

code (código de país estable, único), name. El despliegue no fija una nacionalidad del usuario.

## 5. identity_document_types

issuing_country_code, code, display_name, category, validation_config opcional, validation_version.

Único (issuing_country_code, code), incluyendo bajas. Categorías: national_identity, residence, passport, other. Ejemplos: PE/DNI y ES/DNI. La configuración de validación es administrada y validada; no ejecuta código arbitrario.

## 6. user_identity_documents

user_id, document_type_id, document_number, normalized_number, expires_at opcional, is_primary opcional.

El país emisor se obtiene del tipo documental para evitar discrepancias. Número de texto, normalización según tipo. Como restricción inicial se evita duplicar el mismo documento activo para el mismo usuario. No se impone unicidad global entre personas sin decidir antes el proceso de verificación y posibles números reutilizados.

Si se utiliza is_primary, máximo uno activo por usuario y país emisor. No obligatorio al registrarse.

Implementado (revisión 28950766fbb9):
- countries: code (ISO alfa-2, único) y name.
- identity_document_types: issuing_country_code, code, name, category (CHECK de las 4 categorías) y pattern opcional (regex sobre el número normalizado). Único (issuing_country_code, code). validation_version no se implementó.
- user_identity_documents: user_id, document_type_id, document_number (tal como se escribió), normalized_number (sin espacios, puntos ni guiones, en mayúsculas) y expires_at opcional. Único permanente (user_id, document_type_id): volver a registrarlo restaura la fila. is_primary no se implementó.
- El catálogo inicial (10 países, DNI/CE de Perú, RUT de Chile, CC de Colombia, CI de Ecuador, DNI/NIE de España y un PASAPORTE por país) está en app/seeds/data.py.

## API keys (implementado)

api_keys: user_id, company_id, membership_id (FK compuesta con company_id), name, description opcional, prefix visible, key_hash (SHA-256, único), scopes (JSON con códigos de permiso), expires_at (NULL = sin vencimiento), revoked_at y last_used_at. El secreto nunca se guarda.

## 7. companies

name; atributos fiscales futuros por requisitos. La habilitación se expresa con los campos comunes, evitando duplicar status e is_active sin semántica definida.

## 8. memberships

user_id, company_id, joined_at. Único permanente (user_id, company_id). Reincorporación mediante reactivación auditada de la misma membresía. Sus puestos antiguos no se reactivan automáticamente si fueron dados de baja.

## 9. areas

company_id, code, name. Único (company_id, code). Si un área está deshabilitada no concede acceso mediante sus puestos.

## 10. positions

company_id, area_id, code, name. Único (company_id, code). FK compuesta (area_id, company_id) para impedir vincular un área de otra empresa.

## 11. position_assignments

company_id, membership_id, position_id, starts_at, ends_at opcional.

FKs compuestas verifican que membresía y puesto pertenecen a company_id. Solo una asignación vigente por pareja. Conservar períodos anteriores; la finalización no borra filas. Si se permiten períodos futuros, impedir solapamientos, no solo duplicados is_active=true.

## 12. roles

company_id, code, name, description. Único (company_id, code). Roles reutilizables entre puestos de la empresa.

Implementado: code y name (revisión 37ba63fd1552; los roles existentes tomaron su código como nombre). description queda pendiente.

## 13. permissions

code global único, service_code, description. Ejemplos users.read, users.manage, documents.read. Catálogo de capacidades reales; crear un código no crea implementación.

Implementado: la tabla solo guarda `code`. Los scopes admitidos por cada permiso se declaran en `app/seeds/data.py` (`PERMISSIONS`) y el seed los valida; no hay columna para ellos ni CRUD de permisos.

## 14. role_permissions

role_id, permission_id, scope (own/area/company según permiso). Campos comunes incluidos. Único activo (role_id, permission_id, scope). Un scope solo se acepta si el permiso lo admite.

## 15. position_roles

company_id, position_id, role_id. FKs compuestas aseguran empresa común. Único activo (position_id, role_id). Revocar asignación realiza baja lógica y registra historial.

## 16. AuthSession / sessions

Sesión de usuario con user_id, expires_at (absoluto: login + SESSION_HOURS), revoked_at, initial_ip, last_ip, client_description y last_seen_at. csrf_hash se eliminó (revisión 81b88abef3a5): con Bearer y refresh en el body no hay cookies ni CSRF. Cuenta para el máximo de sesiones solo si está activa, no dada de baja, no revocada y no vencida. El límite lo aplica AuthService bloqueando la fila del usuario; el modelo por sí solo no lo impone.

## 17. RefreshToken / refresh_tokens

session_id, token_hash único (SHA-256 del token) y consumed_at. Una fila por cada refresh emitido; las consumidas se conservan para detectar reutilización. El secreto nunca se almacena en claro. Vale mientras su sesión sea válida; no tiene vencimiento propio.

## 18. RateBucket / rate_buckets

key única, count, window_start y blocked_until. Estado operativo de un contador, no historial inmutable.

Implementado para el bloqueo de login: key = `login_fail:` + SHA-256 de email|IP (el email no se guarda en claro). Se incrementa bloqueando la fila (SELECT ... FOR UPDATE) y se reinicia con un login correcto. Ver `app/services/login_throttle.py`.

## 19. ChangeHistory / change_history

action, resource_id, company_id opcional, trace_id opcional, before y after JSON con campos permitidos. Actor y fecha heredados. Solo anexado. La clase actual protege modificaciones de objetos ORM mediante eventos; no bloquea SQL directo ni garantiza sola el registro transaccional.

## 20-22. Logs técnicos: trasladados al schema audit

Las tablas logs, logs_detail y logs_steps ya no son de auth (retiradas en 8baed1d57096).
Viven en el schema `audit` del paquete compartido `packages/platform-audit`; ver su README.
Lo que sigue describe el diseño original, reemplazado por ese contrato.

## 20. Log / logs (original)

Cabecera técnica con id como identificador de operación, trace_id, parent_operation_id, service, version, action, status, finished_at, duration_ms, http_status, user_id y company_id opcionales. created_at es el inicio. Puede cerrarse actualizando estado/tiempos. El actor de infraestructura que escribe y el usuario validado son conceptos diferentes.

## 21. LogDetail / logs_detail

log_id y data JSON limitado a campos permitidos. No captura automática de bodies o secretos. Solo anexado.

## 22. LogStep / logs_steps

log_id, step_id, name, phase y duration_ms opcional. Inicio y fin de un paso son filas distintas con el mismo step_id. Un inicio sin cierre solo informa que no se registró el cierre, no que el proceso siga vivo.

## Pendiente de modelar

Políticas más allá de User.max_sessions (API keys, catálogos y documentos ya implementados). activity_events se menciona como objetivo histórico, pero por ahora la única clase de historial de negocio es ChangeHistory; debemos decidir si basta antes de añadir otra tabla. No crear estos modelos hasta llegar al paso acordado.
