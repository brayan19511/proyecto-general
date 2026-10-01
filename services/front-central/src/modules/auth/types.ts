// Respuesta de GET /auth/me (services/auth/app/schemas/me.py).

export type Company = { id: string; code: string; name: string }

export type Area = { id: string; code: string; name: string }

export type Position = {
  id: string
  code: string
  name: string
  area: Area
  roles: string[] // códigos de rol heredados por el puesto
}

export type Membership = {
  company: Company
  positions: Position[]
}

export type Profile = {
  first_names: string | null
  last_names: string | null
  birth_date: string | null // fecha ISO (AAAA-MM-DD)
  nationality_country_code: string | null
}

// GET /auth/me/permissions: permisos efectivos en la empresa del X-Company-Id.
export type PermissionGrant = {
  code: string // p. ej. "ledger.view"
  company: boolean // true: vale en toda la empresa
  area_ids: string[] // áreas donde vale, si el alcance es de área
  own: boolean // true: solo sobre recursos propios
}

export type CompanyPermissions = {
  user_id: string
  email: string
  company: Company
  is_platform_admin: boolean
  permissions: PermissionGrant[]
}

// GET /auth/admin/companies (solo platform admin).
export type AdminCompany = Company & { is_active: boolean; created_at: string }

export type Me = {
  id: string
  email: string
  is_platform_admin: boolean
  profile: Profile | null
  session: { id: string; expires_at: string }
  memberships: Membership[]
}
