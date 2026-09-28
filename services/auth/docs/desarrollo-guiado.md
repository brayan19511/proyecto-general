# Desarrollo guiado de auth

> **Prefijo de rutas**: todo el servicio vive bajo `/auth`. Las rutas de este
> documento se escriben sin él por brevedad: `/areas` es `/auth/areas`, `/me` es
> `/auth/me`, `/admin/logs` es `/auth/admin/logs`. Swagger: `/auth/docs`.

## Acuerdo de colaboración

El usuario escribe el código. El asistente explica y revisa, y pide conformidad antes de cambiar modelos, reglas de negocio o decisiones técnicas. Una consulta no autoriza a implementar. Cada paso debe ser pequeño, verificable y entendible antes de avanzar.

Las instrucciones permanentes están en AGENTS.md raíz y en el de auth. Este documento explica el código y las opciones; no autoriza su implementación.

## Estado actual

Hecho por el usuario: configuración (BD y CORS), conexión PostgreSQL, CORS en main.py, Alembic con migraciones aplicadas ([base-de-datos.md](base-de-datos.md)), hash Argon2 en app/core/security.py y registro en UserService/UserRepository (sin ruta HTTP todavía).

Antes, el asistente había añadido una implementación anticipada (HTTP, JWT, seed, business, logs, rate limiting, Docker) que se retiró. El .env del usuario se conservó. El entorno local puede tener paquetes instalados que no figuran en requirements.txt.

## Registro: pendientes detectados en revisión

- Carrera de email duplicado: `get_user_by_email` + `add` no son atómicos. Dos solicitudes simultáneas pasan la consulta, y la segunda falla en el `flush()` de `UserRepository.add` con `sqlalchemy.exc.IntegrityError` por `users.email` UNIQUE. Hoy esa excepción no se captura y produciría 500. Propuesta: capturarla en `UserService.register_user` y convertirla en `EmailAlreadyExistsError`. La transacción ya queda revertida por el `with session.begin()`.
- Longitud de contraseña: `UserCreate.password` no tiene mínimo ni máximo. El máximo evita gastar CPU de Argon2 con entradas enormes. Valores por decidir.
- Normalización de email: el service aplica `strip().lower()` a todo el correo, incluida la parte local. Es la política vigente: `Ana@x.com` y `ana@x.com` son la misma cuenta.
- El historial del registro guarda solo `{"is_active": True}`; no copia email ni hash.

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

## Login, refresh y logout (implementado)

Archivos y responsabilidad de cada uno:

| Archivo | Qué hace |
| --- | --- |
| app/core/tokens.py | Firma y verifica el access token (JWT RS256); genera refresh tokens y su hash |
| app/core/security.py | Hash y verificación de contraseñas; `DUMMY_PASSWORD_HASH` para igualar tiempos |
| app/schemas/auth.py | `LoginRequest`, `RefreshRequest`, `TokenResponse` |
| app/repositories/auth_repository.py | Consultas con bloqueo (`lock_*`) y conteo de sesiones activas |
| app/services/auth_service.py | Reglas: credenciales, límite de sesiones, rotación, revocación |
| app/api/routes/auth_router.py | Traduce errores a HTTP: 401, 409, 204 |

### Rutas

| Ruta | Body | Respuesta |
| --- | --- | --- |
| POST /auth/login | `{email, password}` | 200 tokens · 401 credenciales · 409 máximo de sesiones |
| POST /auth/refresh | `{refresh_token}` | 200 tokens nuevos · 401 inválido/consumido/sesión cerrada |
| POST /auth/logout | `{refresh_token}` | 204 siempre |

El cliente envía el access token como `Authorization: Bearer <token>` y guarda el refresh para renovarlo antes de que venza (`expires_in` en segundos).

### Qué contiene cada token

- Access token (JWT): `iss`, `aud`, `sub` (id del usuario), `sid` (id de la sesión), `iat`, `exp`. Vence a los 15 minutos o al fin de la sesión, lo primero. No lleva empresa, puestos ni roles: se consultan en la base en cada solicitud.
- Refresh token: 256 bits aleatorios sin estructura. En la base solo queda su SHA-256 (no Argon2: el token no se puede adivinar y hay que buscarlo por hash).

### Login paso a paso (AuthService.login)

1. Normaliza el email igual que el registro.
2. Lee el usuario en una transacción corta.
3. Verifica la contraseña fuera de la transacción (Argon2 es lento). Si el email no existe, verifica contra `DUMMY_PASSWORD_HASH`: el tiempo es el mismo y no revela qué cuentas existen.
4. Email inexistente, contraseña incorrecta o cuenta inhabilitada → el mismo `InvalidCredentialsError` → 401 "Credenciales inválidas.".
5. Abre la transacción de escritura y bloquea la fila del usuario (`SELECT ... FOR UPDATE`). Dos logins simultáneos esperan uno al otro: ninguno puede superar el límite.
6. Límite = `users.max_sessions` o, si es NULL, `MAX_SESSIONS`. Si ya se alcanzó → 409.
7. Crea la sesión (expira en SESSION_HOURS, absoluto), el primer refresh y el evento `session.created`.

### Refresh (rotación)

- El refresh usado se marca `consumed_at` y se entrega uno nuevo.
- Si llega un refresh ya consumido, alguien tiene una copia: se revoca la sesión entera (`session.revoked`, reason `refresh_reused`) y se responde 401. La revocación se confirma antes de lanzar el error; si se lanzara dentro de la transacción, el rollback la desharía.
- Dos refresh simultáneos con el mismo token: el bloqueo hace que el segundo vea el token consumido y se trate como reutilización. Es el comportamiento acordado; el cliente debe evitar renovar dos veces en paralelo.
- Actualiza `last_seen_at` y `last_ip` sin crear eventos de historial (actividad operativa).

### Logout

Revoca la sesión del refresh presentado (`session.revoked`, reason `logout`). Responde 204 incluso si el token no es válido, para no revelar nada. Un refresh ya consumido no permite cerrar la sesión: una copia antigua robada no sirve para desconectar al usuario.

### Atribución

Sesiones, refresh y eventos se atribuyen al dueño de la sesión (la operación llega con su credencial). La IP es la de la conexión directa: detrás de un proxy habrá que leer `X-Forwarded-For` solo desde proxies confiables.

### Pendiente

Listar y cerrar sesiones propias; revocación por admin; bloqueo tras 5 fallos (RateBucket).

## Rutas protegidas: get_current_user (implementado)

`app/api/dependencies.py` define la dependencia que usa toda ruta protegida:

```python
@router.get("/algo")
def algo(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    current.user      # User validado
    current.session   # AuthSession vigente
```

Qué comprueba (`AuthService.authenticate`):

1. Header `Authorization: Bearer <token>` presente (`HTTPBearer`; además habilita el botón Authorize de /docs).
2. Firma RS256, `iss`, `aud` y `exp` del token.
3. En la base: la sesión `sid` existe, pertenece a `sub`, está activa, sin revocar y vigente; el usuario está activo y sin baja.

El paso 3 hace que logout, revocación o baja del usuario tengan efecto inmediato, sin esperar a que venza el token (decisión: consultar la base sin caché).

Cualquier fallo → 401 "No autenticado." con `WWW-Authenticate: Bearer`, sin detallar la causa.

La validación usa una transacción corta de lectura. Al terminar, la sesión ORM queda libre para que la ruta abra la suya con `session.begin()`.

## GET /me (implementado)

Devuelve el usuario, su perfil, la sesión actual (`id`, `expires_at`) y sus membresías activas con puestos, área y roles heredados. No recibe empresa.

- `is_platform_admin: true` indica master admin: accede a todas las empresas aunque `memberships` esté vacío.
- Solo aparecen cadenas completamente utilizables: si la empresa, la membresía, la asignación, el puesto, el área, la relación puesto-rol o el rol está inhabilitado o dado de baja, lo que depende de él no se muestra.
- Implementación: `UserService.get_me` hace tres consultas simples (membresías, puestos, roles) en `UserRepository` y las agrupa en Python.

Para probar en /docs: `POST /auth/login`, copiar `access_token`, botón **Authorize**, pegar el token y ejecutar `GET /me`.

## Contexto de empresa y permisos (implementado)

### Catálogo

`app/core/permissions.py` define `PERMISSIONS` (código → scopes admitidos); `app/seeds/data.py` define por empresa `role_permissions` (rol → [(permiso, scope)]). El seed valida que cada scope esté admitido y los carga. AccessService también lo aplica en cada solicitud: un rol-permiso con un scope que el catálogo ya no admite no concede nada. No hay CRUD de permisos: un permiso representa una capacidad del código.

| Permiso | Scopes | ADMIN_TI / ADMIN_CONT |
| --- | --- | --- |
| areas.manage | company | — (decisión: el área la gestiona la empresa) |
| positions.manage | company, area | area |
| roles.manage | company | — (los roles son de la empresa) |
| memberships.manage | company, area | area |
| users.read | company, area | area |

Nadie tiene hoy scope company salvo el master admin. Un rol de administrador de empresa se agrega en data.py cuando haga falta.

### Cómo se usa en una ruta

```python
@router.get("/areas")
def list_areas(ctx: CompanyContext = Depends(require_permission("areas.manage"))):
    ...
    if not ctx.can("areas.manage", area_id=area.id):
        raise HTTPException(403)
```

| Pieza | Archivo | Qué hace |
| --- | --- | --- |
| `get_company_context` | app/api/dependencies.py | Lee `X-Company-Id`, exige login y construye el contexto. 403 si la empresa no existe, está inhabilitada o no hay membresía activa (mismo mensaje en ambos casos) |
| `require_permission(code)` | app/api/dependencies.py | 403 si el usuario no tiene el permiso con ningún alcance. Decide si la ruta se puede usar |
| `CompanyContext.can(code, area_id, owner_id)` | app/services/access_service.py | Decide sobre un recurso concreto: company vale siempre, area solo si coincide el área, own solo si es el dueño |
| `AccessService.build_context` | app/services/access_service.py | Calcula los permisos efectivos |
| `AccessRepository.get_grants` | app/repositories/access_repository.py | Una consulta con toda la cadena membresía → asignación → puesto → área → puesto-rol → rol → rol-permiso → permiso, exigiendo cada eslabón utilizable |

Dos niveles de comprobación: `require_permission` filtra la ruta; `ctx.can` filtra cada recurso. Con alcance area, la ruta debe además limitar los listados a `grant.area_ids`.

El master admin (`is_platform_admin`) obtiene todos los permisos activos con alcance company en cualquier empresa activa, con o sin membresía.

Sin caché: cada solicitud recalcula los permisos, así retirar un permiso, puesto o rol tiene efecto inmediato.

### GET /me/permissions

Con `X-Company-Id`, devuelve los permisos efectivos del usuario en esa empresa (`code`, `company`, `area_ids`, `own`). El frontend lo usa para decidir qué mostrar; el backend vuelve a comprobar en cada operación.

### Pendiente

- Regla de delegación: implementada (ver "Regla de delegación (común)").
- Protección del último admin efectivo de una empresa.
- Permission solo guarda `code`; descripción y servicio dueño quedan para cuando se necesiten.
- En la base quedan dos rol-permiso `areas.manage` con scope `area` (ADMIN_TI y ADMIN_CONT) del seed anterior al cambio. No conceden nada porque el catálogo ya no admite ese scope; se retiran con `DELETE /roles/{id}/permissions/{grant_id}`.

## CRUD de áreas (implementado) — plantilla para los demás

| Ruta | Permiso | Respuestas |
| --- | --- | --- |
| GET /areas | Miembro de la empresa o master admin | 200 (activas y suspendidas; no las dadas de baja) |
| GET /areas/{id} | Ídem | 200 · 404 |
| POST /areas `{code, name}` | areas.manage, alcance company | 201 · 409 código usado · 422 datos |
| PATCH /areas/{id} `{name}` | ídem | 200 · 404 |
| DELETE /areas/{id} | ídem | 204 · 404 · 409 si tiene puestos |

Todas exigen `Authorization: Bearer` y `X-Company-Id`.

Capas, igual que en el resto del servicio:

| Archivo | Responsabilidad |
| --- | --- |
| app/schemas/area.py | Entrada con `extra="forbid"` (rechaza company_id, is_active, created_by…) y salida |
| app/schemas/common.py | Tipos `Code` (`^[A-Z0-9_]+$`, máx. 50) y `Name` (máx. 150), reutilizables |
| app/repositories/area_repository.py | Consultas; todas filtran por `company_id` |
| app/services/area_service.py | Autorización del recurso, transacción, historial |
| app/services/common.py | `audit_create`, `touch`, `soft_delete`, `history_event`: compartidos por todos los CRUD |
| app/api/routes/areas_router.py | Dependencias y traducción de errores (`ERRORS`) a HTTP |

Reglas aplicadas:

- **Aislamiento**: la empresa sale del contexto validado, nunca del body. Un id de área de otra empresa da 404, igual que uno inexistente.
- **Código estable**: se valida el formato y no se puede cambiar con PATCH (lo usa data.py). Queda reservado aunque el área se dé de baja.
- **Baja lógica**: `soft_delete` pone `is_active=false`, `deleted_at` y `deleted_by`; la fila se conserva. Luego el área no aparece en GET y su código no se reutiliza.
- **Área con puestos**: no se puede dar de baja (409). Si se permitiera, los usuarios de esos puestos perderían su acceso sin aviso.
- **Historial**: `area.created`, `area.updated` (before/after del nombre) y `area.deleted`, en la misma transacción del cambio. Un PATCH sin cambios no escribe nada.
- **Carrera en la creación**: un `IntegrityError` por código duplicado se traduce a 409.

Pendiente: reactivar un área suspendida o restaurar una dada de baja (operación explícita con su historial).

## CRUD de puestos (implementado)

Primer recurso donde el alcance `area` se aplica de verdad. Misma estructura de capas que áreas: `schemas/position.py`, `repositories/position_repository.py`, `services/position_service.py`, `api/routes/positions_router.py`.

| Ruta | Permiso | Respuestas |
| --- | --- | --- |
| GET /positions | Miembro de la empresa o master admin | 200, con el área de cada puesto |
| GET /positions/{id} | Ídem | 200 · 404 |
| POST /positions `{code, name, area_id}` | positions.manage en esa área (o company) | 201 · 404 área · 409 código usado |
| PATCH /positions/{id} `{name?, area_id?}` | positions.manage en el área actual; mover exige alcance company | 200 · 403 · 404 |
| DELETE /positions/{id} | positions.manage en el área del puesto | 204 · 409 si tiene personas asignadas |

Decisiones del usuario aplicadas:

- **Mover de área solo con alcance company.** Un admin de área que sacara un puesto de su área dejaría de controlarlo y le pasaría el control a otra área.
- **No se da de baja un puesto con personas asignadas** (409): nadie pierde acceso sin aviso.

Cómo se aplica el alcance en el service: se busca el puesto (siempre filtrado por empresa) y luego `ctx.can("positions.manage", area_id=puesto.area_id)`. Para mover se llama además `ctx.can(...)` sin área, que solo acepta alcance company.

Ver puestos no exige permiso, igual que las áreas: es estructura de la organización.

## Vistas generales del master admin (implementado)

Rutas de solo lectura en `/admin`, protegidas por `require_platform_admin`. No usan `X-Company-Id`: listan todas las empresas en un solo llamado, o filtran con `?company_id=`. Evitan que el panel consulte empresa por empresa.

| Ruta | Devuelve |
| --- | --- |
| GET /admin/companies | Empresas sin baja lógica |
| GET /admin/areas?company_id= | Áreas, cada una con su empresa |
| GET /admin/positions?company_id= | Puestos, cada uno con su área y empresa |

Las modificaciones siguen pasando por las rutas por empresa (`X-Company-Id`), donde el master admin tiene todos los permisos: así las reglas y el historial se aplican en un solo lugar. Archivos: `schemas/admin.py`, `repositories/admin_repository.py`, `services/admin_service.py`, `api/routes/admin_router.py`.

Pendiente: paginación cuando los listados crezcan.

CORS: `X-Company-Id` se agregó a `allow_headers`; sin él, el navegador rechazaría las rutas empresariales en el preflight.

## CRUD de roles y sus permisos (implementado)

`roles.name` se agregó con la revisión 37ba63fd1552: los roles existentes tomaron su código como nombre (renombrables con PATCH). data.py declara ahora `{"code", "name"}` por rol. El seed no actualiza nombres de roles que ya existen.

| Ruta | Permiso | Respuestas |
| --- | --- | --- |
| GET /roles | Miembro o master admin | 200, cada rol con sus concesiones vigentes |
| GET /roles/{id} | Ídem | 200 · 404 |
| POST /roles `{code, name}` | roles.manage (company) | 201 · 409 código usado |
| PATCH /roles/{id} `{name}` | ídem | 200 · 404 |
| DELETE /roles/{id} | ídem | 204 · 409 si está asignado a puestos |
| POST /roles/{id}/permissions `{permission, scope}` | roles.manage + delegación | 201 · 409 ya otorgado · 422 permiso o scope no admitido |
| DELETE /roles/{id}/permissions/{grant_id} | roles.manage + delegación | 204 · 404 |
| GET /admin/roles?company_id= | Solo master admin | Roles de todas las empresas, con permisos |

**Regla de delegación**: para otorgar o retirar el permiso P, quien actúa debe tener P con alcance company (`ctx.can(P)` sin área). Tenerlo solo en un área no alcanza, porque el rol puede vincularse a puestos de cualquier área. El master admin la cumple siempre.

**Volver a otorgar un permiso retirado**: la tabla role_permissions tiene unicidad permanente (rol, permiso, scope), así que no se crea otra fila: se restaura la existente con `restore()` y el evento `role_permission.restored`. Es una acción explícita de un usuario autorizado; el seed nunca restaura.

**Concesiones que el catálogo ya no admite** (como `areas.manage` con scope `area`) aparecen en GET /roles para poder retirarlas con DELETE, pero no conceden nada.

Historial: `role.created`, `role.updated`, `role.deleted`, `role_permission.created`, `role_permission.deleted`, `role_permission.restored`.

Archivos: `schemas/role.py`, `repositories/role_repository.py`, `services/role_service.py`, `api/routes/roles_router.py`; `restore()` en `services/common.py`.

## Granularidad de permisos (decisión)

Un permiso `.manage` por recurso (crear, editar y dar de baja), y lectura abierta a los miembros de la empresa, salvo miembros (`users.read`). Separar en `.create`/`.update`/`.delete` se hará solo cuando exista alguien que deba poder una cosa y no otra; el catálogo se amplía sin cambiar la arquitectura. Las empresas no tienen permiso de empresa: las gestiona el master admin.

## Regla de delegación (común)

Dar exige delegación; quitar solo exige el permiso de gestión, porque reduce privilegios.

| Operación | Quién actúa necesita |
| --- | --- |
| Dar un permiso a un rol | Ese permiso con alcance company (el rol puede vincularse a cualquier área) |
| Vincular un rol a un puesto | Cada permiso del rol con el alcance que otorgará en el área del puesto |
| Asignar un puesto a una persona | Cada permiso que concede el puesto, con ese alcance, en su área |

Las dos últimas usan `ensure_can_delegate(ctx, grants, area_id)` en `services/access_service.py`: un permiso company exige company; uno area exige tenerlo en esa área; uno own, tenerlo con cualquier alcance. Así un admin de TI puede crear otro puesto de admin de TI (mismo poder), pero no uno con permisos de toda la empresa.

## Roles de cada puesto (implementado)

| Ruta | Permiso | Respuestas |
| --- | --- | --- |
| GET /positions/{id}/roles | Miembro | 200 |
| POST /positions/{id}/roles `{role_id}` | positions.manage en el área del puesto + delegación | 201 · 404 · 409 ya vinculado |
| DELETE /positions/{id}/roles/{role_id} | positions.manage en el área del puesto | 204 · 404 |

Volver a vincular un rol retirado restaura la misma fila (`position_role.restored`). Archivo: `services/position_role_service.py`; rutas en `positions_router.py`.

## Miembros y sus puestos (implementado)

| Ruta | Permiso | Respuestas |
| --- | --- | --- |
| GET /members | users.read | 200 (ver visibilidad) |
| GET /members/{id} | users.read | 200 · 404 (también si no es visible) |
| POST /members `{email}` | memberships.manage, alcance company | 201 · 404 email no registrado · 409 ya es miembro |
| PATCH /members/{id} `{is_active}` | ídem | 200: suspende (false) o reactiva (true) conservando sus puestos |
| DELETE /members/{id} | ídem | 204: retira la membresía y todos sus puestos |
| POST /members/{id}/positions `{position_id}` | memberships.manage en el área del puesto + delegación | 201 · 404 · 409 ya lo tiene |
| DELETE /members/{id}/positions/{position_id} | memberships.manage en el área del puesto | 204 · 404 |

- Se agrega a un usuario ya registrado y habilitado por su email exacto; no se crean cuentas ni hay búsqueda abierta.
- Visibilidad con `users.read` de alcance area: los miembros con un puesto en sus áreas, y los que no tienen ningún puesto (para poder asignarlos).
- **Suspender** (vacaciones, licencia): pierde el acceso a la empresa de inmediato y conserva sus puestos; al reactivarlo vuelve igual. Eventos `membership.suspended` / `membership.reactivated`.
- **Retirar** (dejó la empresa): una sola operación da de baja la membresía y todos sus puestos, cada uno con su evento (`assignment.deleted` con `reason: membership_removed`). Si se reincorpora, se restaura su membresía (`membership.restored`) sin puestos: no recupera privilegios en silencio. Es una acción explícita del admin, no una cascada automática.
- Una membresía sola no concede permisos, pero da acceso a la empresa; por eso agregar o retirar exige alcance company.

Archivos: `schemas/member.py`, `repositories/member_repository.py`, `services/member_service.py`, `api/routes/members_router.py`.

## Perfil y sesiones propias (implementado)

| Ruta | Qué hace |
| --- | --- |
| PATCH /me/profile `{first_names?, last_names?}` | Edita solo los campos enviados (null borra); evento `profile.updated` |
| GET /me/sessions | Sesiones vigentes con IP, navegador, fechas y `current` |
| DELETE /me/sessions/{id} | Cierra una sesión propia (puede ser la actual) |
| POST /me/sessions/revoke-others | Cierra todas menos la actual; devuelve cuántas |

No exigen permisos: cada uno gestiona lo suyo. La lógica está en `AuthService.list_sessions`, `revoke_own_session` y `revoke_user_sessions`.

## Empresas y usuarios del master admin (implementado)

| Ruta | Qué hace |
| --- | --- |
| POST /admin/companies `{code, name}` | Crea una empresa (201 · 409 código usado) |
| PATCH /admin/companies/{id} `{name}` | Renombra |
| POST /admin/companies/{id}/deactivate | Congela la empresa: `X-Company-Id` la rechaza para todos (incluido el master) y desaparece de /me. Miembros, puestos y roles se conservan |
| POST /admin/companies/{id}/activate | La devuelve tal como estaba |
| GET /admin/history | Historial de negocio con filtros (ver abajo) |
| GET /admin/users?email=&limit= | Lista usuarios (coincidencia parcial de email, máx. 200) |
| POST /admin/users/{id}/revoke-sessions | Cierra todas sus sesiones (cuenta comprometida); el historial registra al admin como actor |

Una empresa creada por la API no necesita el seed; su estructura se arma con las rutas empresariales usando `X-Company-Id`.

Las empresas no se eliminan (decisión del usuario): se desactivan. Así no hay que retirar miembro por miembro.

## Niveles de administración

| Nivel | Alcance | Cómo se otorga |
| --- | --- | --- |
| Master admin | Toda la plataforma | Solo el seed (`is_platform_admin`) |
| Admin de empresa | Toda su empresa | Puesto `ADMIN_EMPRESA` (área GER) con el rol del mismo nombre: los 5 permisos con alcance company. Puede haber varios |
| Admin de área | Su área | Puestos `ADMIN_TI`, `ADMIN_CONT` (alcance area) |

Por la regla de delegación, el puesto `ADMIN_EMPRESA` solo lo asigna el master u otro admin de empresa.

## Consulta del historial (implementado)

`GET /admin/history` (solo master admin), más recientes primero. Filtros opcionales: `company_id`, `resource_id` (historial de un recurso), `actor_id` (qué hizo un usuario), `action` (prefijo, p. ej. `membership.`), `limit` (máx. 200). Cada evento trae acción, recurso, empresa, actor con su email, before/after y fecha.

Pendiente: una vista por empresa para su admin (exigiría un permiso como `history.read`).

## Bloqueo de login (implementado)

5 contraseñas fallidas del mismo email desde la misma IP en 15 minutos bloquean esa combinación 15 minutos: responde 429 con `Retry-After` en segundos. Configurable: `LOGIN_MAX_FAILURES`, `LOGIN_WINDOW_MINUTES`, `LOGIN_BLOCK_MINUTES`.

- **Por qué en auth y no en el gateway**: el gateway no sabe si una contraseña fue incorrecta; auth sí. Además auth queda protegido si alguien llega sin pasar por el gateway. El gateway limitará el volumen por IP (otra capa, otro contador).
- **Por qué email + IP**: con solo email, cualquiera bloquearía a otra persona fallando a propósito. Desde otra IP el usuario sigue pudiendo entrar.
- Durante el bloqueo no se verifica la contraseña, ni siquiera la correcta.
- Se cuenta igual si el email no existe: el bloqueo no revela qué cuentas existen.
- Un login correcto reinicia el contador. Sesiones llenas (409) no cuentan como fallo.
- El contador vive en `rate_buckets` (compartido por todas las réplicas), en su propia transacción: queda guardado aunque el login falle. Sin eventos de historial.

Archivo: `app/services/login_throttle.py`; se usa en `AuthService.login`.

## Contraseñas (implementado)

| Ruta | Quién | Qué hace |
| --- | --- | --- |
| PATCH /me/password `{current_password, new_password}` | El propio usuario | Exige la actual; cierra las demás sesiones (la actual sigue). Fallos de la actual cuentan en el bloqueo del login (email + IP). 403 actual incorrecta · 422 igual a la actual · 429 bloqueado |
| POST /admin/users/{id}/password `{new_password}` | Solo master admin | Recuperación asistida: asigna una contraseña y cierra todas sus sesiones. Comunicarla por un canal seguro fuera de la API |

Historial `user.password_changed` / `user.password_reset` con `{"password_changed": true}`: nunca la contraseña ni su hash. Archivo: `services/password_service.py`.

La recuperación autónoma (el usuario sin ayuda) necesita un canal propio (correo o SMS) y verificar que el usuario lo controla; queda pendiente de decisión.

## Perfil, catálogo y documentos de identidad (implementado)

Los documentos no son una columna "dni": cada documento tiene un tipo, y cada tipo pertenece a un país emisor (PE/DNI, CL/RUT, ES/DNI, PE/PASAPORTE…). Admitir otro país es agregar datos a `data.py` (`COUNTRIES`, `DOCUMENT_TYPES`) y volver a ejecutar el seed.

| Ruta | Qué hace |
| --- | --- |
| GET /me/profile | Datos personales y documentos vigentes del usuario |
| PATCH /me/profile | Además de nombres: `birth_date` (no futura) y `nationality_country_code` (debe existir en el catálogo; se guarda en mayúsculas) |
| GET /admin/users/{id} | Solo master admin: cuenta, perfil, documentos, empresas (con puestos y roles) y sesiones activas de cualquier usuario, incluso inhabilitado |
| GET /catalog/countries | Países del catálogo (cualquier usuario autenticado) |
| GET /catalog/document-types?country=PE | Tipos de documento, opcionalmente de un país emisor |
| GET /me/documents | Documentos propios |
| POST /me/documents `{document_type_id, document_number, expires_at?}` | Registra uno por tipo. 422 formato inválido o vencimiento pasado · 409 ya tiene ese tipo |
| DELETE /me/documents/{id} | Baja lógica; volver a registrar el tipo restaura la fila con el número nuevo |

- El número se guarda como se escribió y normalizado (sin espacios, puntos ni guiones, en mayúsculas); se valida con el `pattern` del tipo. Conserva ceros iniciales. Formato válido no es identidad verificada.
- Nacionalidad, país de residencia y país emisor son conceptos distintos.
- El historial registra tipo y vencimiento, nunca el número.
- Sin unicidad entre personas: requeriría decidir antes un proceso de verificación.

Archivos: el perfil tiene los suyos, `services/profile_service.py` y `api/routes/profile_router.py` (rutas `/me/profile` y `/me/documents`). Catálogo y reglas de documentos: `schemas/identity.py`, `repositories/identity_repository.py`, `services/identity_service.py`, `api/routes/catalog_router.py`.

Ciclo de vida: el perfil es uno por cuenta. Nace con el registro o el seed y vive mientras exista la cuenta: no hay crear ni eliminar. Para vaciar un dato se envía null.

Limitar lo que ve el master: **qué campos** se controla en el schema de respuesta (`AdminUserDetailOut` en `schemas/admin.py`: lo que no está ahí no se devuelve); **quién** puede verlo, en la dependencia de la ruta (hoy `require_platform_admin`). Para que distintos roles vean distinto, se necesitan ambas cosas: un permiso y dos schemas. La consulta queda registrada en `audit.logs` (quién y cuándo).

## Límites por IP y proxies confiables (implementado)

Volumen por IP (todas las solicitudes, correctas o no), con 429 + `Retry-After`:

| Operación | Default | Variables |
| --- | --- | --- |
| Registro | 10 por hora | `REGISTER_IP_LIMIT`, `REGISTER_IP_WINDOW_MINUTES` |
| Login | 30 cada 15 min | `LOGIN_IP_LIMIT`, `LOGIN_IP_WINDOW_MINUTES` |
| Refresh | 120 cada 15 min | `REFRESH_IP_LIMIT`, `REFRESH_IP_WINDOW_MINUTES` |

Los valores son una propuesta inicial; ajústalos según el uso real. Es otra capa distinta del bloqueo por contraseñas fallidas. Contadores en `rate_buckets` con clave `auth:ip:<operación>:<sha256 de la IP>`: espacio de nombres propio, así la API central no cuenta en el mismo contador.

IP real: `app/core/client_ip.py`. Solo si la conexión viene de una IP de `TRUSTED_PROXIES` se lee `X-Forwarded-For` (de derecha a izquierda, el primer salto que no sea proxy confiable). Sin proxies configurados, un cliente no puede falsificar su IP con ese header. Solo IPs exactas (sin rangos CIDR).

Archivos: `services/rate_limit.py` y la dependencia `ip_rate_limit` en `api/dependencies.py`.

## Protección del último admin (implementado)

Administrador efectivo = usuario activo con `memberships.manage` de alcance company por una cadena completamente utilizable. Las operaciones que quitan privilegios responden 409 si dejarían en cero a una empresa que tenía al menos uno:

- quitar un puesto, suspender o retirar a un miembro;
- desvincular un rol de un puesto;
- retirar un permiso de un rol.

`LastAdminGuard` (en `services/access_service.py`) bloquea la fila de la empresa al inicio: dos admins no pueden quitarse el puesto a la vez y dejarla vacía. Si la empresa no tenía admins (la gestiona solo el master), no bloquea. El master admin no cuenta como admin de la empresa: es el procedimiento extraordinario de recuperación.

## Restaurar recursos dados de baja (implementado)

`POST /areas/{id}/restore`, `POST /positions/{id}/restore`, `POST /roles/{id}/restore`, con el mismo permiso que su gestión. `GET /areas`, `/positions` y `/roles` aceptan `?include_deleted=true` para encontrarlos (la respuesta trae `deleted_at`).

- Un puesto no se restaura si su área está dada de baja (409): primero el área.
- Un puesto vuelve con sus roles pero sin personas; un rol vuelve con sus permisos pero sin puestos (la baja exigía que no los tuviera). Nadie recupera privilegios en silencio.
- Eventos `area.restored`, `position.restored`, `role.restored`.

## Paginación (implementado)

`?limit=` (1-500, default 100) y `?offset=` en /areas, /positions, /roles, /members y todas las vistas /admin. Cuando la página trae menos de `limit` elementos, no hay más. En /members se pagina después de aplicar la visibilidad por área.

## Historial por empresa (implementado)

`GET /history` con `X-Company-Id`, para quien tenga `history.read` (solo alcance company; lo tiene ADMIN_EMPRESA). Mismos filtros que /admin/history, pero siempre limitado a la empresa activa: no ve otras empresas ni eventos globales (usuarios, perfiles, sesiones).

## API keys (implementado)

| Ruta | Qué hace |
| --- | --- |
| POST /api-keys `{name, description?, scopes, expires_at? \| expires_in_days?}` | Crea una key propia en la empresa activa. Devuelve el secreto en `key` una sola vez |
| GET /api-keys | Keys propias en la empresa (incluye revocadas y vencidas) |
| DELETE /api-keys/{id} | Revocación irreversible |

Uso: header `X-API-Key: ak_xxxx.secreto` en cualquier ruta empresarial; `X-Company-Id` es opcional (la empresa es la de la key; si se envía otra, 403).

- `name` y `description` (opcional, máx. 500; revisión b920b3502d47) solo sirven para reconocerla. `scopes` es otra cosa: la lista de códigos de permiso que la key podrá usar.
- Sin `expires_at` ni `expires_in_days`, la key no vence (`expires_at` null): vale hasta que se revoque o se pierda la membresía o los permisos.
- Máximo `API_KEYS_MAX` (5) activas y vigentes por usuario entre todas sus empresas; se cuenta bloqueando la fila del usuario.
- Scopes: códigos del catálogo que el usuario tiene al crearla. En cada uso, permisos efectivos = permisos actuales de la membresía ∩ scopes: si el usuario pierde un permiso, la key también.
- Una key nunca actúa como master admin: con key, los permisos salen solo de los puestos, aunque el dueño sea master.
- Una key no puede crear ni revocar keys (esas rutas exigen Bearer).
- Sin vencimiento no significa irrevocable: revocarla, suspender la membresía o dar de baja al usuario la anulan.
- En la base: hash SHA-256 y prefijo visible; nunca el secreto. `last_used_at` se actualiza en cada uso sin generar historial.

Archivos: `schemas/api_key.py`, `repositories/api_key_repository.py`, `services/api_key_service.py`, `api/routes/api_keys_router.py`; autenticación en `get_company_context`.

Pendiente: que un admin vea o revoque las keys de otros; que otros servicios validen keys (requiere un endpoint interno autenticado entre servicios, ver el plan de integración).

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

## Seed: ruta /seed

Un seed prepara los datos iniciales; no es lo mismo que una migración, que crea/modifica estructura.

Se desea crear el administrador y la estructura mínima que lo autoriza: empresa, membresía, área, puesto, rol y permisos. Debe poder repetirse sin duplicar ni restituir privilegios retirados.

Decisión del usuario: ruta API `/seed` idempotente. Atribución: los registros creados por el seed quedan con created_by/updated_by NULL; es el único caso permitido (ver modelo-datos.md). Sus eventos de ChangeHistory usan acciones con prefijo `seed.` para distinguirlos de un NULL accidental.

Pendiente de acordar antes de codificar:

1. Autorización de la primera ejecución: no hay administrador que inicie sesión. Una opción es un secreto de bootstrap configurado por variable de entorno y enviado en un header, comparado en tiempo constante.
2. Habilitación: la ruta existe solo si una variable la activa (por ejemplo SEED_ENABLED=false por defecto), para no exponerla en producción.
3. Cierre: qué ocurre tras el primer bootstrap exitoso (responder 404/409, o solo informar "ya existía").
4. Idempotencia: identificar recursos por código estable; lo existente, aunque esté dado de baja, no se modifica ni se reactiva; no cambiar contraseñas; fallar si el email del admin pertenece a una cuenta pública existente.
5. Datos de entrada: empresa, email del admin y su contraseña en el body (nunca fijos en código).

Implementado: `app/seeds/data.py` declara `COMPANIES`, una lista donde cada empresa trae sus áreas, puestos, roles, relación puesto-rol y el puesto del admin (`admin_position_code`, o None). Para preconfigurar otra empresa se agrega a la lista y se vuelve a ejecutar POST /seed: solo se crea lo nuevo. El admin (email y contraseña en `.env`) recibe membresía y puesto en cada empresa con `admin_position_code`.

Regla del admin existente: si el email ya existe con `created_by` NULL, es el admin del seed y se reutiliza sin cambiar su contraseña. Si tiene `created_by`, es una cuenta registrada públicamente y el seed responde 409 en lugar de promoverla.

Decisión del usuario: la primera versión del seed no crea permisos ni RolePermission. Crea empresa, área, puesto, rol, relación puesto-rol, admin, perfil, membresía y asignación. Consecuencia: el rol admin existe pero no concede capacidades hasta que se incorpore el catálogo de permisos. Cuando se incorpore, el seed los añadirá de forma idempotente: crear solo si no existe ninguna fila, ni siquiera inactiva, para no restituir permisos retirados.

Nunca una ruta pública que cree administradores solo porque todavía no hay uno.

## Configuración mínima actual

| Variable | Para qué sirve | Default | ¿Necesaria ahora? |
| --- | --- | --- | --- |
| PROJECT_NAME | Título mostrado por FastAPI en /docs | Auth | Opcional |
| DB_ENGINE | Motor: postgresql o mssql | postgresql | Sí |
| DB_HOST / DB_PORT | Servidor y puerto | localhost / 5432 | Sí |
| DB_NAME / DB_USER / DB_PASSWORD | Base y credenciales de conexión | Sin default | Obligatorias |
| CORS_ORIGINS | Orígenes web permitidos (lista JSON) | [] | Cuando haya cliente web |

SettingsConfigDict permite leer .env. extra="ignore" ignora ajustes adicionales antiguos; no los activa. Aún no hay configuración de JWT, sesiones ni límites.

## Configuraciones retiradas: explicación para cuando hagan falta

Estas variables NO están activas. Los valores fueron propuestas del asistente, no decisiones que deban conservarse sin revisión.

| Variable anterior | Propósito | Cuándo se evaluará |
| --- | --- | --- |
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

- Resuelto: AuditMixin ya no usa FK diferidas; sus campos de actor son FK nullable a users.id.
- Nombres de constraints generados por cada motor: ver la propuesta de naming_convention en base-de-datos.md.
- DateTime(timezone=True) requiere revisar representación y normalización UTC en cada motor.
- JSON y cadenas Unicode necesitan verificar almacenamiento y consultas en ambos motores.
- Unicidad, aislamiento y bloqueo concurrente requieren pruebas en las dos bases.
- La protección ORM de historial no equivale a protección de base de datos.

Las migraciones existen y se aplicaron en PostgreSQL. No se declara soporte operativo de SQL Server.

También falta distinguir: ¿un motor por instalación del producto, o bases diferentes por empresa dentro de la misma instalación? El segundo caso implica resolución de conexiones y una arquitectura distinta; no se implementará por inferencia.

Referencia: [SQL Server en SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/mssql.html).

## Logs (platform_audit, implementado)

Los logs no son código de auth: vienen del paquete compartido
[packages/platform-audit](../../../packages/platform-audit/README.md), instalado con
`-e ../../packages/platform-audit` en requirements.txt. Un cambio en el paquete
llega a todos los servicios que lo usan. Plan y decisiones:
[docs/plan-observabilidad.md](../../../docs/plan-observabilidad.md).

Qué hace auth para usarlo:

| Dónde | Qué |
| --- | --- |
| app/main.py | `AuditMiddleware` con `SERVICE_NAME`, `SERVICE_VERSION`, `TRUSTED_PROXIES`, `AUDIT_MAX_BODY_BYTES` |
| app/api/dependencies.py | `set_actor(user_id, company_id)` al validar Bearer o API key |
| app/services/auth_service.py | `set_actor` al iniciar sesión; pasos `verificar contraseña` y `crear sesión` |
| app/services/seed_service.py | Un paso por empresa del seed |
| app/api/routes/logs_router.py | `GET /admin/logs` (filtros trace_id, user_id, outcome, path_prefix; paginado) y `GET /admin/logs/{id}` con detalles y pasos. Solo master admin; solo filas de `service = auth` |
| scripts/migrate_audit.py | Aplica las migraciones del schema audit con el engine de auth |

Pasos manuales en cualquier función:

```python
from platform_audit import step, log_message

with step("calcular permisos"):
    ...
log_message("warning", "reintento del proveedor", {"intentos": 2})
```

Qué se ve por solicitud: cabecera (trace_id, usuario, empresa, método, ruta,
estado, resultado, IP, user agent, inicio, fin, duración), el request
(parámetros, headers permitidos y body enmascarado), la respuesta si hubo error
(p. ej. "Credenciales inválidas."), el tipo de excepción en un 500 y los pasos.
La respuesta devuelve `X-Trace-Id`.

`AUDIT_ENABLED=false` apaga los logs sin tocar código (útil en pruebas).

Qué datos se ocultan: constantes en `app/core/audit.py`. `EXTRA_SENSITIVE_KEYS`
(nombres exactos) y `EXTRA_SENSITIVE_KEY_PARTS` (fragmentos que el nombre
contiene) se suman a las listas del paquete; también se puede reemplazarlas.
Mayúsculas y acentos no importan (`Contraseña` = `contrasena`). Hoy auth agrega
seed_token, nombres, apellidos, fecha de nacimiento y pin a lo que ya oculta el
paquete (contraseñas, claves, tokens, secretos, credenciales, emails, DNI, RUT,
pasaporte, número de documento, authorization, cookies, API keys).

## Prefijo, health/ready y Docker (implementado)

- **Prefijo `/auth`**: `main.py` monta todos los routers bajo `PREFIX = "/auth"`,
  incluidos Swagger (`/auth/docs`) y OpenAPI (`/auth/openapi.json`). El API gateway
  reenvía `/auth/*` sin reescribir la ruta: la misma ruta directo y por el gateway,
  y el `path` de los logs coincide en ambos.
- **`GET /auth/health`**: el proceso está vivo; no consulta la base (reiniciarlo no
  arreglaría una base caída). **`GET /auth/ready`**: hace `SELECT 1`; 503 si la base
  no responde, para que el gateway lo saque de rotación. Ninguno se registra en los logs.
- **Dockerfile** (`services/auth/Dockerfile`, build desde la raíz): Python 3.14
  (uuid7 de la biblioteca estándar), dependencias en una capa cacheada, usuario sin
  privilegios, HEALTHCHECK y sin secretos en la imagen. Instrucciones en el readme.
- Al probar la imagen apareció que `email-validator` (necesario para `EmailStr`)
  no estaba en requirements.txt; se agregó.

## Orden propuesto, sin implementación automática

1. ~~Entender AuditMixin y acordar la atribución~~ (hecho: FK a users, NULL solo en seed).
2. ~~Conectar al contenedor PostgreSQL~~ (hecho).
3. ~~Crear el esquema y sus migraciones~~ (hecho; naming_convention pendiente de decidir).
4. ~~Endurecer el registro y exponer su ruta~~ (hecho).
5. ~~Ruta `/seed` idempotente, varias empresas, master admin~~ (hecho).
6. ~~Login, refresh y logout~~ (hecho).
7. ~~`get_current_user` y `GET /me`~~ (hecho).
8. ~~Contexto de empresa (`X-Company-Id`) y cálculo de permisos~~ (hecho).
9. ~~CRUDs de empresa: áreas, puestos, roles, rol-permiso, puesto-rol, membresías y asignaciones~~ (hechos).
10. ~~Perfil propio, sesiones propias, empresas y usuarios del master admin~~ (hechos).
11. ~~Bloqueo tras 5 fallos, admin de empresa, suspender/retirar miembros, desactivar empresas, consulta del historial~~ (hechos).
12. ~~Contraseñas, perfil y documentos, límites por IP, proxies confiables, último admin, restaurar, paginación, historial por empresa, API keys~~ (hechos).
13. Pendientes, por prioridad:
    - **Esenciales**: pruebas automatizadas (pytest contra una base PostgreSQL de pruebas, nunca SQLite).
    - **Logs**: ~~implementados~~ (ver sección "Logs (platform_audit)"); faltan la parte de la API central y la política de retención.
    - **Seguridad**: recuperación de cuenta autónoma (requiere decidir el canal: correo o SMS); política si la base no está disponible para los contadores.
    - **Funcionales**: que un admin vea o revoque keys ajenas; descripción de roles y permisos; teléfono y residencia en el perfil.
    - **Limpieza de datos locales**: puesto `ADMIN` y roles `ADMIN` y `ADMIN CONTABILIDAD` de seeds antiguos; concesiones inertes `areas.manage`/`area`.
    - **Diferidos por decisión**: SQL Server (checklist en base-de-datos.md) y naming_convention.

Cada paso se explica y se acuerda antes de escribir código.

