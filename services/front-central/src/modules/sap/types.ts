// Tipos de sap-operaciones (services/sap-operaciones).

export type JobKind = 'document_action' | 'reconciliation'
export type JobStatus = 'draft' | 'queued' | 'running' | 'completed' | 'completed_with_errors' | 'failed' | 'cancelled'
export type ItemStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'uncertain' | 'cancelled'

export type Job = {
  id: string
  kind: JobKind
  company_db: string
  entity: string | null
  action: string | null
  parameters: { recon_date?: string; filename?: string; rows?: number }
  status: JobStatus
  total_items: number
  succeeded_items: number
  failed_items: number
  uncertain_items: number
  cancelled_items: number
  error_message: string | null
  sap_user: string | null
  has_credentials: boolean
  can_view_credentials: boolean // solo en el detalle: true para el administrador de plataforma
  service_layer_url: string | null
  trace_id: string | null // solicitud que lo creó (Monitoreo › Actividad y logs)
  created_by: string
  cancel_requested_at: string | null
  created_at: string
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
}

export type JobListItem = Job & { created_by_user: string }

export type Page<T> = { total: number; limit: number; offset: number; next_offset: number | null; items: T[] }

export type Preview = {
  job: Job | null // null: el archivo o la lista tienen errores; nada se guardó.
  errors: { row: number | null; message: string }[]
  duplicates: number
}

export type JobItem = {
  seq: number
  reference: string // DocEntry o ReconNum
  status: ItemStatus
  http_status: number | null
  sap_error: string | null
  started_at: string | null
  finished_at: string | null
}

// Ítem con lo enviado a SAP y su respuesta (acotada a 20 KB).
export type JobItemDetail = JobItem & {
  request: { method: string; path: string; body: unknown } | null
  response: { status: number; body: unknown } | null
}

export type JobEvent = {
  action: string
  details: Record<string, unknown>
  actor_kind: string // user o system
  actor: string
  created_at: string
}

export type SapDatabase = { id: string; company_db: string; label: string | null; created_at: string }
