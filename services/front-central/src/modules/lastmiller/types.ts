// Tipos de canales-venta › lastmiller (services/canales-venta).

export type Sku = {
  sku: string
  external_id: string | null // Hoy siempre igual al sku.
  is_active: boolean
  has_promotion: boolean | null // null: el canal no maneja promociones.
  created_at: string | null // Hora del servidor de Ofisis, sin zona.
  updated_at: string | null
}

export type Page<T> = {
  total: number
  limit: number
  offset: number
  next_offset: number | null
  items: T[]
}

export type ImportKind = 'sku_full' | 'sku_partial' | 'promotions'
export type ImportStatus = 'previewed' | 'invalid' | 'applying' | 'applied' | 'failed' | 'interrupted' | 'cancelled'

export type ImportSummary = {
  id: string
  kind: ImportKind
  create_missing: boolean
  filename: string
  status: ImportStatus
  total_changes: number
  applied_changes: number
  error_message: string | null
  created_at: string
  applied_at: string | null
}

// Vista previa. SKU: create/activate/deactivate/deactivate_unlisted/missing.
// Promociones: add/remove/missing (bloquea)/inactive (aviso).
export type ImportPlan = {
  rows?: number
  unchanged?: number
  blocking?: boolean
  create?: { sku: string; active: boolean }[]
  activate?: string[]
  deactivate?: string[]
  deactivate_unlisted?: string[]
  missing?: string[]
  add?: string[]
  remove?: string[]
  inactive?: string[]
}

export type ImportDetail = ImportSummary & {
  errors: { row: number | null; message: string }[]
  plan: ImportPlan
  can_apply: boolean
}

export type SkuEvent = {
  id: string
  sku: string
  action: string
  before: Record<string, unknown>
  after: Record<string, unknown>
  import_id: string | null
  user_id: string
  created_at: string
}
