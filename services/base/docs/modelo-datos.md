# Modelo de datos de auth

Propuesta de diseño; pendiente de migraciones. Python + FastAPI. Identificadores UUID y fechas UTC como convención propuesta.

## Estado del código conservado

Las secciones numeradas originales describen el objetivo funcional, no una equivalencia exacta con entities.py. Se conservaron los modelos solicitados por el usuario; aún no hay conexión ni tablas creadas.

Diferencias que deben revisarse juntos antes de implementar:
- Company añade code como identificador de seed. Role conserva solo code; Permission solo code. Descripciones y catálogo completo quedan pendientes.
- Profile implementa solo nombres/apellidos. Países y documentos siguen como propuesta documental, sin clases implementadas.
- Assignment no incluye starts_at/ends_at y usa unicidad permanente de la pareja; el diseño de períodos/reactivación debe acordarse antes de avanzar.
- Las relaciones PositionRole y RolePermission también usan unicidad permanente en el código; este documento describe unicidad activa como objetivo por revisar.
- AuditMixin conserva restricciones diferidas en actores, incompatibles con el objetivo de SQL Server sin revisión. No ejecutar creación de tablas suponiendo portabilidad.
- Los defaults de fecha se calculan separadamente; todavía no hay lógica que asigne el mismo instante/actor al alta como exige la convención siguiente.

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

## 1. actors

Identifica quién realizó una acción: kind (user/service/system/anonymous), subject_ref y label mínimo.

created_by/updated_by/deleted_by de otras tablas apuntan a actors. El bootstrap crea un actor de sistema con atribución autorreferente resuelta en la transacción inicial. El autorregistro crea un actor de usuario con el UUID de usuario preasignado y crea la cuenta/perfil en la misma transacción. Un login fallido desconocido usa actor anónimo, no la identidad afirmada en el formulario.

La referencia subject_ref evita depender de una FK circular hacia users. No guardar email ni datos personales redundantes en este catálogo si no son necesarios.

## 2. users

Campos específicos: email, normalized_email, password_hash, actor_id (único).

normalized_email es único incluyendo cuentas dadas de baja. El perfil y la autenticación no dependen de tener empresa. No hay verificación de email en esta entrega ni atributo que declare el correo verificado falsamente.

## 3. user_profiles

user_id (único), first_names, last_names, birth_date, phone, residence_country_code, nationality_country_code opcionales.

Si más adelante se requieren múltiples nacionalidades, se modelará una relación específica. Ningún campo del perfil concede autorización.

## 4. countries

code (código de país estable, único), name. El despliegue no fija una nacionalidad del usuario.

## 5. identity_document_types

issuing_country_code, code, display_name, category, validation_config opcional, validation_version.

Único (issuing_country_code, code), incluyendo bajas. Categorías: national_identity, residence, passport, other. Ejemplos: PE/DNI y ES/DNI. La configuración de validación es administrada y validada; no ejecuta código arbitrario.

## 6. user_identity_documents

user_id, document_type_id, document_number, normalized_number, expires_at opcional, is_primary opcional.

El país emisor se obtiene del tipo documental para evitar discrepancias. Número de texto, normalización según tipo. Como restricción inicial se evita duplicar el mismo documento activo para el mismo usuario. No se impone unicidad global entre personas sin decidir antes el proceso de verificación y posibles números reutilizados.

Si se utiliza is_primary, máximo uno activo por usuario y país emisor. No obligatorio al registrarse.

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

## 13. permissions

code global único, service_code, description. Ejemplos users.read, users.manage, documents.read. Catálogo de capacidades reales; crear un código no crea implementación.

## 14. role_permissions

role_id, permission_id, scope (own/area/company según permiso). Campos comunes incluidos. Único activo (role_id, permission_id, scope). Un scope solo se acepta si el permiso lo admite.

## 15. position_roles

company_id, position_id, role_id. FKs compuestas aseguran empresa común. Único activo (position_id, role_id). Revocar asignación realiza baja lógica y registra historial.

## 16. AuthSession / sessions

Sesión de usuario con user_id, expires_at, revoked_at, csrf_hash, initial_ip, last_ip, client_description y last_seen_at. Cuenta para el máximo de sesiones solo si está activa, no dada de baja, no revocada y no vencida. El campo CSRF corresponde a una propuesta de transporte web por decidir. El modelo no impone el límite de tres por sí mismo.

## 17. RefreshToken / refresh_tokens

session_id, token_hash único y consumed_at. Varias renovaciones históricas por sesión; el secreto nunca se almacena en claro. Rotación y revocación requieren lógica transaccional posterior.

## 18. RateBucket / rate_buckets

key única, count, window_start y blocked_until. Estado operativo de un contador, no historial inmutable. Ventanas, actualización atómica y política de bloqueo todavía por implementar y comprobar en cada motor.

## 19. ChangeHistory / change_history

action, resource_id, company_id opcional, trace_id opcional, before y after JSON con campos permitidos. Actor y fecha heredados. Solo anexado. La clase actual protege modificaciones de objetos ORM mediante eventos; no bloquea SQL directo ni garantiza sola el registro transaccional.

## 20. Log / logs

Cabecera técnica con id como identificador de operación, trace_id, parent_operation_id, service, version, action, status, finished_at, duration_ms, http_status, actor_id y company_id opcionales. created_at es el inicio. Puede cerrarse actualizando estado/tiempos. El actor de infraestructura que escribe y el usuario validado son conceptos diferentes.

## 21. LogDetail / logs_detail

log_id y data JSON limitado a campos permitidos. No captura automática de bodies o secretos. Solo anexado.

## 22. LogStep / logs_steps

log_id, step_id, name, phase y duration_ms opcional. Inicio y fin de un paso son filas distintas con el mismo step_id. Un inicio sin cierre solo informa que no se registró el cierre, no que el proceso siga vivo.

## Pendiente de modelar

API keys y scopes, catálogos/documentos y políticas más allá de User.max_sessions. activity_events se menciona como objetivo histórico, pero por ahora la única clase de historial de negocio es ChangeHistory; debemos decidir si basta antes de añadir otra tabla. No crear estos modelos hasta llegar al paso acordado.
