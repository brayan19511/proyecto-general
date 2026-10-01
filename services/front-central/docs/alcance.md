# Alcance del front central

Aplicación web de administración para los servicios de la plataforma. Consume
todo a través de la central (API Gateway). Este documento fija qué pantallas
entran, qué endpoint usa cada una y qué falta en el backend.

## Topología

```
navegador ──> front (nginx, build estático)
          └─> central (/auth/*, /libro-mayor/*, /gateway/*) ──> auth, libro-mayor
```

- El front es un contenedor propio en el compose de la central
  (`services/apigateway/docker-compose.yml`), red `edge`.
- Variable de configuración `VITE_API_URL`: URL base de la central.
  Default en desarrollo: `http://localhost:8001`. Se fija en el build (Vite);
  si se necesita cambiarla sin reconstruir, se evaluará un `config.json`
  servido por nginx.
- La central debe incluir el origen del front en `CORS_ORIGINS` y tener
  `LIBRO_MAYOR_ENABLED=true` para que Contabilidad funcione.

## Sesión (acuerdo, fase 1)

- `POST /auth/login` → access en memoria, refresh en `sessionStorage`.
- Al recargar: `POST /auth/refresh` con el refresh guardado; si falla, login.
- Access vence en ~15 min: el cliente HTTP refresca ante 401 (una vez).
- `POST /auth/logout` borra la sesión en el servidor y en el navegador.
- Pestañas (acuerdo, 2026-09-30): comparten una sola sesión. Una pestaña nueva
  o recargada toma la sesión de las abiertas; solo una renueva a la vez (Web
  Locks) y avisa a las demás; cerrar sesión en una la cierra en todas. Así no
  se acumulan sesiones hasta el máximo (`MAX_SESSIONS`).
- La sesión dura como máximo `SESSION_HOURS` (5 h) desde el login: al vencer,
  vuelve al login con el mensaje "Tu sesión terminó".
- Errores de login: 401 credenciales, 429 bloqueo (mostrar `Retry-After`),
  409 máximo de sesiones (sugerir cerrar otra sesión).

## Visibilidad de módulos (sin tabla nueva)

Lo cubre lo que ya existe: `GET /auth/me` da `is_platform_admin` y
`GET /auth/me/permissions` (con `X-Company-Id`) da los permisos efectivos del
usuario en la empresa activa. El front tiene una tabla fija en código
(`shared/auth/access.ts`):

| Módulo | Visible si |
|---|---|
| Mi perfil | cualquier usuario autenticado |
| Contabilidad | `ledger.view`, `ledger.update` o `ledger.admin` en la empresa activa |
| Contabilidad › acciones de edición | `ledger.update` (reglas, categorías); `ledger.admin` (cuentas, sync manual, homologación) |
| Empresa (áreas, puestos, roles, permisos, miembros) | fase 1: solo `is_platform_admin` (acuerdo: limitarlo por ahora) |
| Monitoreo | `is_platform_admin` (los endpoints de logs lo exigen) |
| Plataforma | `is_platform_admin` |

El platform admin ve todos los módulos sin necesitar permisos (acuerdo,
2026-09-30); su selector lista todas las empresas activas
(`GET /auth/admin/companies`), aunque no tenga membresía en ellas.

Ocultar un módulo es experiencia de usuario, no seguridad: el backend valida
cada solicitud. Nota: hoy `GET /auth/roles`, `/areas` y `/positions` responden
a cualquier miembro de la empresa; restringirlos es un cambio en auth pendiente
de decidir.

## Módulos de la fase 1

### 1. Login
`/login`. Tarjeta centrada, email y contraseña (mostrar/ocultar), mensajes de
401/409/429. Enlace a registro: fuera de la fase 1.

### 2. Layout
Sidebar agrupada por módulo (colapsable), topbar con migas, selector de empresa
(lista de `me.memberships`) y menú de usuario con "Cerrar sesión". Página
inicial: `/perfil`.

### 3. Mi perfil (`/perfil/...`)
| Pestaña | Endpoints |
|---|---|
| Información | `GET /auth/me`, `GET/PATCH /auth/me/profile`, `GET /auth/catalog/countries` |
| Empresas y puestos | `GET /auth/me` (memberships → positions → área y roles). Sin códigos de permiso para no admin |
| Seguridad | `PATCH /auth/me/password` (cierra las otras sesiones) |
| Sesiones | `GET /auth/me/sessions`, `DELETE /auth/me/sessions/{id}`, `POST /auth/me/sessions/revoke-others` |

Documentos del perfil (`/auth/me/documents`): fuera de la fase 1.

## Estado (2026-09-30)

Fase 1 completa: login, layout, Mi perfil, Contabilidad (libro mayor, consulta
en SAP, sincronización, reglas y categorías, centros de costo, cuentas),
Empresa (miembros, áreas y puestos, roles y permisos, historial), Monitoreo
(logs por servicio y trazas) y Plataforma (empresas con compañía SAP,
usuarios, servicios de la central e IPs bloqueadas).

## Fases siguientes (contexto, no implementar aún)

- **Contabilidad** (`/contabilidad/...`): líneas y resumen
  (`/libro-mayor/ledger/*`, CSV), consultas en vivo, estado de sincronización
  (`/sync-status`, `/sync-runs`), cuentas, categorías, reglas,
  reclasificaciones y homologación de centros de costo.
- **Empresa**: miembros (`/auth/members`, agregar por email), áreas, puestos
  (asignar roles), roles (asignar permisos con alcance), historial
  (`/auth/history`).
- **Monitoreo**: logs por servicio (`/auth/admin/logs`,
  `/libro-mayor/admin/logs`, `/gateway/admin/logs`) con filtros y detalle
  (payload enmascarado y pasos), cruzados por `trace_id`; sincronizaciones
  fallidas.
- **Plataforma**: empresas (`/auth/admin/companies`), usuarios (buscar,
  revocar sesiones, restablecer contraseña), servicios e IPs bloqueadas de la
  central.

## Libro mayor: pedidos del usuario (2026-09-30)

Hechos:
1. Tercer nivel Proveedor: libro-mayor `GET /ledger/summary?by_supplier=true`.
2. Nada se omite: nodos "Sin categoría / subcategoría / proveedor asignado"
   con filtros propios (`unclassified`, `no_subcodigo`, `no_supplier`); las
   hojas suman el total general.
3. Descarga en CSV (acuerdo).
4. Filtro de cuentas con selector (`/libro-mayor/accounts`).
5. Detalle de un mes completo (pie de la tabla) y atajo "Mes" en filtros.
6. Consulta en SAP (`/contabilidad/consulta-sap`, `POST /libro-mayor/live-queries`):
   mismo árbol y detalle; con "resumen y detalle" el árbol y el detalle salen de
   las líneas en memoria; "solo resumen" llega hasta subcategoría y sin detalle.
7. Libro mayor no consulta al entrar: solo al pulsar "Consultar".
8. Reglas y categorías: CRUD con bajas lógicas y reclasificaciones.
   Pendiente: carga masiva de reglas (`POST /rules/import`, con `dry_run`) y,
   si se decide en libro-mayor, restaurar categorías y reglas dadas de baja.
9. Centros de costo y homologación (centro → área de auth). No requiere
   reproceso: libro-mayor resuelve el área al consultar.
   Pendiente: carga masiva (`POST /cost-center-mappings/import`).

## Pendientes del backend (no los resuelve el front)

- Crear usuarios desde administración: el front registra la cuenta con la ruta
  pública (`POST /auth/users`) y luego la agrega a la empresa. Pendiente en
  auth: alta por administrador con cambio de contraseña obligatorio en el
  primer ingreso (hoy la temporal la conoce el admin) y sin el límite por IP
  del registro público (`REGISTER_IP_LIMIT`).
- Métricas de uso (logins por día, uso por servicio, usuarios por IP): cada
  servicio solo lista sus logs; faltan endpoints de resumen.
- Historial de cambios de libro-mayor (`ChangeHistory`) sin endpoint.
- Puertos locales de ejemplo inconsistentes entre los `.env` de la central y
  libro-mayor (8001/8002/8003).
- Refresh en cookie HttpOnly (propuesta pendiente en `docs/arquitectura.md`).
