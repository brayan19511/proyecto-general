// Contrato de logs de packages/platform-audit, igual en todos los servicios
// (GET <servicio>/admin/logs y /admin/logs/{id}).

export type LogOutcome = 'success' | 'warning' | 'error'

export type LogEntry = {
  id: string
  trace_id: string // une las filas de una misma solicitud en todos los servicios
  parent_operation_id: string | null
  method: string
  path: string
  status_code: number | null
  outcome: LogOutcome | null // null = sin cerrar
  ip_address: string | null
  user_agent: string | null
  user_id: string | null
  company_id: string | null
  started_at: string
  finished_at: string | null
  duration_ms: number | null
}

// Parámetros, headers y bodies ya enmascarados por el servicio.
export type LogDetail = {
  level: string
  kind: string // request, response, error, message…
  message: string | null
  data: Record<string, unknown> | null
  created_at: string
}

export type LogStep = {
  step_id: string
  name: string
  phase: string
  message: string | null
  duration_ms: number | null
  created_at: string
}

export type LogFull = LogEntry & { details: LogDetail[]; steps: LogStep[] }

export type LogFilters = {
  outcome: LogOutcome | ''
  userId: string
  pathPrefix: string
  traceId: string
}

// GET /auth/admin/users (solo platform admin): para mostrar correos.
export type AdminUser = { id: string; email: string; is_active: boolean; is_platform_admin: boolean }
