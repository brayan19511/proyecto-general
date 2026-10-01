import type { Membership, Profile } from '../auth/types'

export type { AdminCompany } from '../auth/types'

// GET/POST/PATCH /libro-mayor/admin/sap-company (con X-Company-Id de la empresa).
export type SapCompany = {
  id: string
  company_id: string
  sap_schema: string // base/schema SBO de la empresa en HANA
  source_view: string // vista de la que se leen las líneas
  sync_start_date: string // desde qué fecha se hace la carga inicial
  created_at: string
}

// GET /auth/admin/users
export type AdminUser = {
  id: string
  email: string
  is_active: boolean
  is_platform_admin: boolean
  created_at: string
}

// GET /auth/admin/users/{id}
export type AdminUserDetail = AdminUser & {
  deleted_at: string | null
  max_sessions: number | null // null = el máximo por defecto
  updated_at: string
  profile: Profile | null
  memberships: Membership[]
  active_sessions: number
}

// GET /gateway/admin/services: servicios publicados por la central.
export type GatewayService = {
  service: string // "auth", "libro-mayor"
  enabled: boolean // estado efectivo ahora
  enabled_by_config: boolean // <SERVICIO>_ENABLED
  panel_managed: boolean // false = solo se cambia por configuración
  db_enabled: boolean | null // cambio guardado desde el panel; null = vale la configuración
  reason: string | null
  updated_at: string | null
  updated_by: string | null // id de usuario
}

// GET /gateway/admin/ip-blocks
export type IpBlock = {
  id: string
  network: string // IP o rango CIDR normalizado
  reason: string | null
  expires_at: string | null // null = sin vencimiento
  is_active: boolean
  created_at: string
  created_by: string | null
  deleted_at: string | null
  deleted_by: string | null
}

// GET /gateway/admin/history
export type GatewayHistoryEvent = {
  id: string
  action: string
  resource_type: string // "service_state", "ip_block"
  resource_id: string
  trace_id: string | null
  before: Record<string, unknown>
  after: Record<string, unknown>
  created_at: string
  created_by: string | null
}
