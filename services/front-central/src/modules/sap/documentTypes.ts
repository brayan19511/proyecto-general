// Tipos de documentos SAP y descargas de anexos (sap-operaciones, /documents).

export type Partner = 'customer' | 'supplier' | 'none'
export type Criterion = 'doc_entry' | 'doc_num' | 'num_at_card' | 'folio'

export type DocumentType = {
  code: string // FV, OC, ... (el backend lo traduce a SAP)
  label: string
  partner: Partner // cómo se rotula CardCode/CardName; none = sin búsqueda por socio
  criteria: Criterion[] // búsquedas exactas admitidas
}

export type SapDocument = {
  type_code: string
  doc_entry: number
  doc_num: number | null
  num_at_card: string | null
  folio: string | null
  card_code: string | null
  card_name: string | null
  doc_date: string | null
  has_attachments: boolean
}

// SAP no informa el total: next_offset existe mientras la página venga llena.
export type DocumentSearchPage = { limit: number; offset: number; next_offset: number | null; items: SapDocument[] }

export type Attachment = { line: number; file_name: string; attached_on: string | null }

export type DocumentSearch = {
  company_db: string
  type: string
  doc_entry?: string
  doc_num?: string
  num_at_card?: string
  folio?: string
  card_code?: string
  card_name?: string
  date_from?: string
  date_to?: string
}

export type DownloadMode = 'single' | 'sequential' | 'zip'
export type DownloadFileStatus = 'pending' | 'delivered' | 'failed'

export type DownloadFile = {
  seq: number
  type_code: string
  doc_entry: number
  doc_num: number | null
  line: number
  file_name: string
  status: DownloadFileStatus
  delivered_at: string | null
  error: string | null
}

export type Download = {
  id: string
  company_db: string
  mode: DownloadMode
  file_count: number
  user_id: string // usuario de auth que descargó
  trace_id: string | null
  created_at: string
  files: DownloadFile[]
}

export type DownloadListItem = Omit<Download, 'files' | 'trace_id'> & { delivered_count: number }

// Archivo elegido en pantalla: lo único que se envía para pedir la descarga.
export type FileSelection = { type_code: string; doc_entry: number; line: number }
