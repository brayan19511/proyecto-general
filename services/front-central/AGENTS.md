# Front central (React + TypeScript)

Lee las instrucciones raíz (`AGENTS.md`), `docs/arquitectura.md` y, de este
servicio, `docs/alcance.md` antes de proponer o revisar cambios. El proyecto
`D:\proyectos\proyecto-08` es solo referencia de estilo: no copiar su código
sin revisarlo (ver "Qué no repetir").

## Estado

Proyecto Vite con Bootstrap, tokens (`src/index.css`) y layout base con datos
de ejemplo: `src/app/layout/` (AppLayout, Sidebar, Topbar, menú en
`navigation.ts`), router en `src/app/router.tsx`, componentes `PageHeader` y
`EmptyState`, tema claro/oscuro (`useTheme`). Sesión: `shared/api/apiClient.ts`
(cliente único, refresh compartido ante 401), `shared/auth/tokens.ts`,
`shared/auth/sessionStore.ts` (zustand), guard `app/RequireAuth.tsx` y
`modules/auth/pages/LoginPage.tsx`. Empresa activa (`X-Company-Id` en el
cliente, selector en la topbar; el platform admin elige entre todas las
empresas activas) y permisos de `/auth/me/permissions` en el store. Reglas de
acceso en `shared/auth/access.ts` (el platform admin pasa todas, acuerdo
2026-09-30), aplicadas al menú (`navigation.ts`) y a las rutas
(`app/RequireAccess.tsx`). Mi perfil (`modules/profile`) con pestañas como
rutas: información (editar perfil), empresas y puestos, seguridad (cambio de
contraseña) y sesiones. Compartidos: `useApi`, `AsyncState`, `ConfirmDialog`
(`<dialog>` nativo), `RouteTabs`, toasts (`shared/stores/toastStore.ts` +
`ToastContainer`) y `shared/utils/format.ts`. Contabilidad › Sincronización
(`modules/ledger/pages/SyncPage.tsx`, solo lectura: `/libro-mayor/sync-status`
y `/sync-runs` con filtros y paginación), con `DataTable`, `Pager`,
`StatusBadge` y `app/RequireCompany.tsx`. Sincronización manual
(`SyncRunModal`, solo `ledger.admin`) con seguimiento cada 5 s mientras haya
ejecuciones abiertas. Diálogos: base `Dialog` (`<dialog>` nativo + card), sobre
ella `ConfirmDialog` y `FormModal`; un modal con formulario se monta solo al
abrirse para empezar limpio. Contabilidad › Libro mayor
(`modules/ledger/pages/LedgerPage.tsx`): resumen tipo tablix desde
`/ledger/summary?by_supplier=true` (categoría › subcategoría › proveedor × mes,
`summaryTree.ts`; cada nodo lleva sus filtros exactos, incluidos los "sin
asignar", y nada se omite), selector de cuentas y atajo de mes, monto
mínimo y moneda en el navegador, detalle por celda (`LineDetailDialog`, líneas
paginadas, columnas elegibles con `CheckboxDropdown`, descarga CSV de lo visible)
y CSV completo de libro-mayor (`apiDownload`). No consulta al entrar (solo con
"Consultar"). Consulta en SAP (`LiveQueryPage`, `POST /live-queries`) reutiliza
`SummaryView` y `LineDetailDialog` (que recibe `loadPage`/`loadAll`: servidor o
memoria con `detailSelection.lineMatches`, mismo criterio que libro-mayor);
tramos a SAP calculados en el front (hasta 31 días por día, si no por mes).
Reglas y categorías (`/contabilidad/reglas`, `RulesLayout` con pestañas
Reglas, Categorías y Reclasificaciones): ver con `ledger.view`, editar con
`ledger.update`; bajas lógicas (libro-mayor no tiene restaurar). Seguimiento
de trabajos del worker con `shared/hooks/useInterval.ts`. Centros de costo
(`/contabilidad/centros-costo`: centros vistos en las líneas y homologaciones a
áreas de auth; editar con `ledger.admin`; sin reproceso, el área se resuelve al
consultar). Empresa › Miembros (`modules/company`, solo platform admin en fase
1): agregar por email, suspender/reactivar, dar de baja y asignar/quitar
puestos, y registrar una cuenta nueva (`POST /auth/users`, contraseña temporal
generada en el navegador) antes de agregarla. Áreas y puestos (`AreasPage`):
crear, renombrar, mover, dar de baja y restaurar; roles del puesto
(`PositionRolesModal`). Códigos de auth con `company/codes.ts`. Desde una
homologación se puede crear un área sin salir del formulario. Roles y permisos
(`RolesLayout`, pestañas Roles y Permisos): roles con búsqueda, crear,
renombrar, dar de baja/restaurar y asignar/desasignar a puestos
(`RolePositionsModal`; auth no tiene "puestos de un rol": se arma con
`listPositionRolesMap`); permisos por catálogo con los roles que los tienen,
conceder, cambiar alcance (concede el nuevo y luego quita el anterior) y quitar
(`GrantModal`). Desasignar es siempre un botón visible (no solo desmarcar).
Historial (`HistoryPage`, `/auth/history`): filtros por recurso, actor y id,
con detalle antes/después. Contabilidad › Cuentas (`AccountsPage`, solo
`ledger.admin`): alta, edición y baja de las cuentas que sincroniza libro-mayor.
Plataforma (`modules/platform`, solo platform admin, sin RequireCompany):
Empresas (crear, renombrar, activar/desactivar; actualiza el selector con
`reloadCompanies`) con su compañía SAP de libro-mayor, pedida con el
`X-Company-Id` de cada empresa (`companyId` del cliente HTTP); Usuarios
(buscar, detalle, restablecer contraseña y cerrar sesiones). Contraseñas
temporales con `shared/utils/password.ts`. Servicios (`/gateway/admin/services`:
habilitar/deshabilitar con motivo; auth solo por configuración) e IPs
bloqueadas (`/gateway/admin/ip-blocks`: IP o CIDR, motivo y vencimiento; la
central impide bloquear la propia IP), ambos con su historial de la central.
Fase 1 completa. Contenedor: `Dockerfile` (node → nginx), `nginx/*.template`
(SPA, caché, gzip, CSP y cabeceras de seguridad con `${API_ORIGIN}`),
`docker/05-check-env.sh` y servicio `front-central` en
`services/apigateway/docker-compose.yml` (`FRONT_PORT`, `FRONT_API_URL`).
El navegador llama directo a la central: nginx no hace de proxy. La CSP no
admite scripts ni estilos en `<style>`/HTML en línea: no agregarlos (los
`style={...}` de React sí funcionan).
Pendiente técnico: el build supera 500 kB en un solo archivo; dividir con
`React.lazy` por módulo cuando convenga. El catálogo es una copia de
`services/auth/app/core/permissions.py` en `company/permissionCatalog.ts`
(auth valida con 422): al agregar un permiso en auth, agregarlo ahí. Importes con BigInt
(`shared/utils/decimal.ts`), nunca float. Monitoreo › Actividad y logs
(`modules/monitoring`, solo platform admin): una pestaña por servicio
(`/monitoreo/logs/:service`, contrato de platform-audit), filtros y atajos,
detalle con datos enmascarados y pasos, y traza completa por `trace_id`
consultando cada servicio (nunca leyendo filas de otro). Pendientes de Libro
mayor en `docs/alcance.md`.
Tras editar archivos, si el front muestra código viejo, reiniciar `npm run dev`
(el watcher de Vite en Windows a veces no detecta cambios).
Se avanza un paso pequeño por vez según el AGENTS.md raíz. El usuario autorizó
(2026-09-30) que el asistente cree y modifique archivos del paso acordado;
borrar algo relevante requiere avisar o pedir permiso. No adelantar páginas,
servicios, dependencias ni configuración de Docker de pasos futuros.

## Stack (acuerdo del usuario, 2026-09-30)

- React + TypeScript + Vite, react-router, zustand solo para la sesión.
- Bootstrap 5 (solo CSS) + bootstrap-icons, con tokens propios en `:root`
  y dark mode con `data-bs-theme`. Sin otra librería de UI.
- Carga de datos con un hook propio sencillo (`useApi`); sin TanStack Query
  por ahora. Formularios controlados con `useState`; sin librería de
  formularios ni de validación hasta que haga falta.
- Contenedor propio: nginx sirve el build estático. Sin SSR.

## Reglas del front

- Toda llamada HTTP va a la central (`/auth/...`, `/libro-mayor/...`); nunca a
  un servicio directo. La URL base viene de configuración, no del código.
- Un solo cliente HTTP (`shared/api/apiClient.ts`): agrega `Authorization`
  y `X-Company-Id`, ante 401 intenta un refresh una vez y, si falla, cierra la
  sesión y vuelve a `/login`. Ningún servicio arma headers por su cuenta.
- Tokens (acuerdo, fase 1): access solo en memoria; refresh en
  `sessionStorage`. Nunca en `localStorage`, en la URL ni en logs de consola.
  Pendiente: refresh en cookie HttpOnly (ver `docs/arquitectura.md`).
- Una sola sesión por navegador (decisión del usuario, 2026-09-30,
  `shared/auth/sessionSync.ts`): las pestañas se pasan los tokens por
  BroadcastChannel (nunca por almacenamiento compartido) y renuevan con un
  candado de Web Locks, adoptando antes la copia más nueva de otra pestaña
  (`issuedAt`). Nunca renovar sin el candado: el refresh es rotativo y auth
  revoca la sesión si se reutiliza. Cerrar sesión en una pestaña la cierra en
  todas.
- El front no decide la autorización: oculta menús y rutas según
  `/auth/me` (`is_platform_admin`) y `/auth/me/permissions` de la empresa
  activa, pero el backend siempre valida. Un 403 se muestra como
  "Sin acceso", nunca se reintenta.
- Los permisos requeridos por módulo y ruta viven en un único archivo
  (`shared/auth/access.ts`). Sin tabla nueva en el backend para el menú.
- Al cambiar de empresa se recargan los permisos y se descartan los datos de la
  empresa anterior.
- No enviar campos de auditoría ni de actor/empresa en el body: los asigna el
  servidor. La empresa viaja solo en `X-Company-Id`.
- "Eliminar" es baja lógica: el texto dice "Dar de baja", pide confirmación y
  las listas ofrecen "ver inactivos" y "restaurar" cuando el backend lo tiene.
- Mostrar errores del backend con su mensaje seguro (`detail`); nunca volcar
  respuestas crudas. 429: mostrar el tiempo de `Retry-After`.
- Importes: el backend los da como texto decimal; formatear sin convertir a
  `float` para cálculos.

## Estructura y componentes

- `src/app` (router, layout, guards), `src/modules/<modulo>/{pages,components,
  services,types}`, `src/shared/{api,auth,components,hooks,utils}`.
- Un archivo de servicio por recurso (`areasService.ts`) con funciones
  tipadas; las páginas no llaman a `fetch`.
- Componentes reutilizables en `shared/components` antes de repetir marcado:
  `PageHeader`, `DataTable` (con paginación y estado vacío), `FilterBar`,
  `FormModal` (sobre `<dialog>`), `ConfirmDialog`, `StatusBadge`,
  `EmptyState`, `Toast`. Un componente nuevo solo cuando se usa en dos sitios.
- Pestañas de un módulo como rutas hijas (`/perfil/seguridad`), no estado local.
- Componentes de pantalla pequeños; si un archivo pasa de ~300 líneas,
  dividirlo por pestaña o sección.
- Textos en español con tildes, en frases (no Title Case).

## Qué no repetir del proyecto 08

Token en `localStorage`, rutas sin guard, 401 sin limpiar la sesión,
`API_BASE_URL` duplicado, servicios que saltan el cliente HTTP, `alert()`
nativo, modales sin ESC ni foco, componentes de más de 1000 líneas, clases de
Tailwind sin Tailwind, nginx inline en el Dockerfile.

## Verificación

Cambio de empresa (menú, permisos y datos se actualizan), usuario sin
`ledger.*` no ve Contabilidad ni entra por URL, usuario no admin no ve
Empresa ni Plataforma, 401 con refresh correcto y con refresh vencido, 409 por
máximo de sesiones y 429 en login, baja lógica con confirmación, y que ningún
token aparezca en `localStorage`, URLs ni consola.
