// Tipos de libro-mayor (services/libro-mayor/app/schemas/sync_runs.py).

export type SyncRunStatus = 'pending' | 'running' | 'succeeded' | 'failed'

// GET /libro-mayor/sync-status: una fila por cuenta activa.
export type SyncStatus = {
  account_id: string
  code: string
  match_mode: string
  name: string | null
  watermark: string | null // día desde el que leerá el próximo delta; null = sin carga inicial
  last_success_at: string | null
  hours_since_success: number | null
  consecutive_failures: number // > 0: algo falla desde la última carga correcta
  last_run_id: string | null
  last_run_kind: string | null
  last_run_status: SyncRunStatus | null
  last_error: string | null
}

// GET /libro-mayor/sync-runs
export type SyncRun = {
  id: string
  account_id: string
  kind: 'sync' | 'initial' | 'delta'
  origin: 'manual' | 'schedule'
  status: SyncRunStatus
  date_from: string
  date_to: string
  days_total: number
  days_done: number
  rows_read: number
  rows_inserted: number
  rows_updated: number
  safe_error: string | null // mensaje seguro (sin texto crudo del driver)
  created_at: string
  started_at: string | null
  heartbeat_at: string | null
  finished_at: string | null
  schedule_slot: string | null
}

export type SyncRunFilters = {
  status: SyncRunStatus | ''
  accountId: string
  offset: number
}

// Filtros de /libro-mayor/ledger/* (lines, lines.csv, summary).
export type LedgerFilters = {
  dateFrom: string // AAAA-MM-DD
  dateTo: string
  accounts: string // "95*,701110002" (* = prefijo); vacío = todas
  costCenterCode: string
}

// Filtros de un nodo del árbol (ver summaryTree.ts). Los "no…" piden solo las
// líneas sin ese dato, para que ningún nodo "sin asignar" mezcle otras líneas.
export type NodeFilters = {
  codigo?: string
  subcodigo?: string
  noSubcodigo?: boolean // clasificada en una categoría principal
  unclassified?: boolean // sin regla
  supplier?: string
  noSupplier?: boolean // sin proveedor en SAP
}

// Filtros del detalle: los de la consulta + los del nodo elegido.
export type LedgerDetailFilters = LedgerFilters & NodeFilters

// GET /libro-mayor/ledger/summary: por año, mes, codigo y subcodigo.
export type SummaryRow = {
  year: number
  month: number
  codigo: string | null // null = sin clasificar
  subcodigo: string | null
  supplier?: string | null // con by_supplier=true (null = sin proveedor)
  lines: number
  amount_local: string // decimal como texto
  amount_foreign: string
}

// Una línea de GET /libro-mayor/ledger/lines (tal como vino de SAP + clasificación).
export type LedgerLine = {
  sap_transaction_id: number
  sap_line: number
  posting_date: string
  document_date: string | null
  document_number: string | null
  transaction_type: string | null
  folio: string | null
  document_type: string | null
  account_code: string
  account_name: string | null
  supplier: string | null
  description: string | null
  line_comment: string | null
  counter_account_code: string | null
  counter_account_name: string | null
  reference_1: string | null
  reference_2: string | null
  reference_3: string | null
  amount_local: string
  amount_foreign: string
  cost_center_code: string | null
  cost_center_area: string | null
  cost_center_name: string | null
  area_id: string | null
  area_name: string | null
  sap_created_at: string | null
  sap_updated_at: string | null
  rule_id: string | null
  codigo: string | null
  subcodigo: string | null
  nombre_cuenta: string | null
}

export type LedgerLinesPage = {
  total: number
  limit: number
  offset: number
  next_offset: number | null // null = no hay más
  lines: LedgerLine[]
}

// GET /libro-mayor/accounts: cuentas registradas para sincronizar.
export type Account = {
  id: string
  code: string
  match_mode: 'exact' | 'prefix'
  name: string | null
  is_active: boolean
  created_at: string
  deleted_at: string | null
}

// POST /libro-mayor/live-queries: consulta SAP en el momento (no se guarda).
export type LiveQueryView = 'summary' | 'full' // solo resumen | resumen + líneas

export type LiveQueryRequest = {
  accounts: string[] // "95*" (prefijo) o "701110002" (exacta)
  date_from: string
  date_to: string
  split: 'month' | 'day' // tramos que libro-mayor consulta a SAP en paralelo
  view: LiveQueryView
}

export type LiveQueryResult = {
  accounts: string[]
  date_from: string
  date_to: string
  split: string
  chunks: number // tramos consultados
  lines_total: number
  elapsed_ms: number
  summary: SummaryRow[] | null // sin proveedor
  lines: LedgerLine[] | null // null con view=summary
}

// --- Reglas y categorías (services/libro-mayor/app/schemas/rules.py) ---

// Sin parent_id: categoría ("codigo"). Con parent_id: subcategoría ("subcodigo").
export type Category = {
  id: string
  parent_id: string | null
  name: string
  is_active: boolean
  created_at: string
  deleted_at: string | null
}

// Condiciones de una regla: vacía = no filtra; todas las llenas deben cumplirse.
export type RuleConditions = {
  account_code: string | null
  counter_account_code: string | null
  cost_center_code: string | null
  include_text: string | null
  exclude_text: string | null
  amount_min: string | null // decimal como texto
  amount_max: string | null
  nombre_cuenta: string | null // nombre en reportes; vacío = el de la cuenta SAP
}

export type Rule = RuleConditions & {
  id: string
  priority: number // menor = se evalúa antes; gana la primera que cumple
  category_id: string
  is_active: boolean
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export type RuleInput = RuleConditions & { priority: number; category_id: string }

export type ClassificationRun = {
  id: string
  reason: 'rule_change' | 'manual'
  rule_id: string | null
  date_from: string | null
  date_to: string | null
  status: SyncRunStatus
  rows_checked: number
  rows_changed: number
  safe_error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

// --- Homologación centro de costo → área de auth (schemas/cost_centers.py) ---

// GET /libro-mayor/cost-centers: centros vistos en las líneas sincronizadas.
export type CostCenter = {
  cost_center_code: string | null // null = líneas sin centro
  sap_name: string | null
  lines: number
  last_posting_date: string | null
  area_id: string | null // null = sin homologar
  area_name: string | null
  match_mode: 'exact' | 'prefix' | null // cómo se resolvió
  mapping_code: string | null // código o prefijo de la homologación que aplica
}

export type CostCenterMapping = {
  id: string
  cost_center_code: string
  match_mode: 'exact' | 'prefix'
  auth_area_id: string
  area_code: string
  area_name: string
  is_active: boolean
  created_at: string
  updated_at: string
  deleted_at: string | null
}
