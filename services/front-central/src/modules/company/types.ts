// Tipos de auth para la empresa activa (services/auth/app/schemas).

export type Ref = { id: string; code: string; name: string }

// GET /auth/areas
export type Area = {
  id: string
  code: string
  name: string
  is_active: boolean
  deleted_at: string | null
  created_at: string
  updated_at: string
}

// GET /auth/positions
export type Position = {
  id: string
  code: string
  name: string
  is_active: boolean
  deleted_at: string | null
  area: Ref
  created_at: string
  updated_at: string
}

// GET /auth/members: id = membresía (se usa en /members/{id}).
export type Member = {
  id: string
  user_id: string
  email: string
  first_names: string | null
  last_names: string | null
  is_active: boolean // false = suspendido (conserva sus puestos)
  positions: { id: string; code: string; name: string; area: Ref }[]
  created_at: string
}

// GET /auth/positions/{id}/roles
export type PositionRole = { role_id: string; code: string; name: string; is_active: boolean }

// Concesión de un permiso a un rol (id = la concesión, se usa para retirarla).
export type RoleGrant = { id: string; permission: string; scope: 'company' | 'area' | 'own' }

// GET /auth/roles
export type Role = {
  id: string
  code: string
  name: string
  is_active: boolean
  deleted_at: string | null
  permissions: RoleGrant[] // solo concesiones vigentes
  created_at: string
  updated_at: string
}

// GET /auth/history: un cambio de negocio con sus valores antes/después.
export type HistoryEvent = {
  id: string
  action: string // "membership.suspended", "role_permission.created"…
  resource_id: string
  company_id: string | null
  actor_id: string | null // null = seed o solicitud anónima
  actor_email: string | null
  before: Record<string, unknown>
  after: Record<string, unknown>
  created_at: string
}
