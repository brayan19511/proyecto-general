import {
  LEDGER_ADMIN,
  LEDGER_VIEW,
  NOTIFICATIONS_VIEW,
  PAYMENTS_VIEW,
  type AccessRule,
} from '../../shared/auth/access'

// Menú lateral. Cada grupo es un módulo; cada ítem, una ruta con la regla que
// decide si se muestra (la misma regla protege la ruta en router.tsx).

export type NavItem = {
  label: string
  path: string
  icon: string // clase de bootstrap-icons sin el prefijo "bi-"
  access: AccessRule
}

export type NavGroup = {
  label: string
  items: NavItem[]
}

// Fase 1 (acuerdo): Empresa, Monitoreo y Plataforma solo para platform admin.
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Cuenta',
    items: [{ label: 'Mi perfil', path: '/perfil', icon: 'person', access: 'authenticated' }],
  },
  {
    label: 'Contabilidad',
    items: [
      { label: 'Libro mayor', path: '/contabilidad/libro-mayor', icon: 'journal-text', access: { anyOf: LEDGER_VIEW } },
      { label: 'Consulta en SAP', path: '/contabilidad/consulta-sap', icon: 'lightning-charge', access: { anyOf: LEDGER_VIEW } },
      { label: 'Sincronización', path: '/contabilidad/sincronizacion', icon: 'arrow-repeat', access: { anyOf: LEDGER_VIEW } },
      { label: 'Reglas y categorías', path: '/contabilidad/reglas', icon: 'list-check', access: { anyOf: LEDGER_VIEW } },
      { label: 'Centros de costo', path: '/contabilidad/centros-costo', icon: 'pin-map', access: { anyOf: LEDGER_VIEW } },
      { label: 'Cuentas', path: '/contabilidad/cuentas', icon: 'journal-bookmark', access: { anyOf: LEDGER_ADMIN } },
    ],
  },
  {
    // Como en proyecto-08 (Finanzas › Tesorería): pagos a proveedores y sus
    // correos. Rutas /tesoreria: /notificaciones/* y /pagos-proveedores/* los
    // envía el borde a la API.
    label: 'Tesorería',
    items: [
      { label: 'Pagos a proveedores', path: '/tesoreria/pagos', icon: 'cash-stack', access: { anyOf: PAYMENTS_VIEW } },
      { label: 'Proveedores', path: '/tesoreria/proveedores', icon: 'building', access: { anyOf: PAYMENTS_VIEW } },
      { label: 'Correos enviados', path: '/tesoreria/correos', icon: 'envelope-arrow-up', access: { anyOf: NOTIFICATIONS_VIEW } },
    ],
  },
  {
    label: 'Empresa',
    items: [
      { label: 'Miembros', path: '/empresa/miembros', icon: 'people', access: 'platformAdmin' },
      { label: 'Áreas y puestos', path: '/empresa/areas', icon: 'diagram-3', access: 'platformAdmin' },
      { label: 'Roles y permisos', path: '/empresa/roles', icon: 'shield-lock', access: 'platformAdmin' },
      { label: 'Historial', path: '/empresa/historial', icon: 'clock-history', access: 'platformAdmin' },
    ],
  },
  {
    label: 'Monitoreo',
    items: [{ label: 'Actividad y logs', path: '/monitoreo/logs', icon: 'activity', access: 'platformAdmin' }],
  },
  {
    label: 'Plataforma',
    items: [
      { label: 'Empresas', path: '/plataforma/empresas', icon: 'buildings', access: 'platformAdmin' },
      { label: 'Usuarios', path: '/plataforma/usuarios', icon: 'person-gear', access: 'platformAdmin' },
      { label: 'Servicios', path: '/plataforma/servicios', icon: 'hdd-network', access: 'platformAdmin' },
      { label: 'IPs bloqueadas', path: '/plataforma/ips', icon: 'shield-x', access: 'platformAdmin' },
      // Correo de la empresa activa, común a todos los módulos (acuerdo 2026-10-01:
      // solo administrador por ahora; a futuro quizá un rol de administrador de TI).
      { label: 'Cuentas SMTP', path: '/plataforma/cuentas-smtp', icon: 'hdd-stack', access: 'platformAdmin' },
      { label: 'Plantillas de correo', path: '/plataforma/plantillas', icon: 'file-earmark-richtext', access: 'platformAdmin' },
    ],
  },
]

// Grupo e ítem de la ruta actual, para las migas de la barra superior.
export function findNavItem(pathname: string) {
  for (const group of NAV_GROUPS) {
    const item = group.items.find(
      (i) => pathname === i.path || pathname.startsWith(i.path + '/'),
    )
    if (item) return { group, item }
  }
  return null
}
