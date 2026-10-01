// Respuestas de pagos-proveedores (services/pagos-proveedores/app/schemas).

export type Page<T> = { items: T[]; total: number }

export type Provider = {
  id: string
  tax_id: string // RUC o DNI normalizado (solo letras y dígitos en mayúscula)
  legal_name: string
  commercial_names: string[] // nombres con que aparece en las constancias
  payment_emails: string[]
  is_active: boolean
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export type ProviderInput = Pick<Provider, 'tax_id' | 'legal_name' | 'commercial_names' | 'payment_emails'>

export type BatchStatus = 'draft' | 'sending' | 'sent'

export type BatchSummary = {
  id: string
  reference: string | null
  status: BatchStatus
  file_count: number
  notification_dispatch_id: string | null
  created_at: string
  sent_at: string | null
}

export type BatchFile = {
  id: string
  sequence: number
  original_filename: string
  size_bytes: number
  parse_status: 'parsed' | 'error'
  parse_error: string | null
  used_ocr: boolean
  beneficiary_name: string | null
  beneficiary_tax_id: string | null
  account: string | null
  currency: string | null
  amount: string | null // decimal en texto (2 decimales)
  operation_date: string | null
  already_sent_in_batch_id: string | null // este pago ya se envió en ese lote
  already_sent_match: 'file' | 'data' | null // mismo PDF, u otro PDF con los mismos datos de pago
}

export type GroupStatus = 'READY' | 'MISSING_PROVIDER' | 'MISSING_PAYMENT_EMAIL'

export type BatchGroup = {
  status: GroupStatus
  provider_id: string | null
  provider_name: string
  provider_tax_id: string | null
  pdf_holder: string | null
  payment_emails: string[]
  payment_count: number
  totals: { currency: string; symbol: string; total: string }[]
  payments: {
    file_id: string
    suggested_filename: string
    currency: string
    amount: string
    account: string | null
    reference: string | null
    process_date: string | null
  }[]
}

export type Batch = BatchSummary & {
  ready_to_send: boolean
  counts: { files: number; parsed: number; errors: number; groups: number; missing_provider: number; missing_email: number }
  files: BatchFile[]
  groups: BatchGroup[]
}

// GET/PATCH /settings: plantilla por defecto de los lotes de la empresa.
export type PaymentSettings = {
  default_template_code: string | null // elegida por la empresa; null = la del servicio
  effective_template_code: string // la que usará el próximo envío
  service_template_code: string // DEFAULT_TEMPLATE_CODE del servicio
}

export type DeliveryStatus = {
  status: string // del envío en notificaciones
  counts: Record<string, number>
  deliveries: {
    delivery_id: string
    provider_id: string | null
    legal_name: string
    payment_emails: string[]
    message_id: string | null
    status: string | null
    sent_at: string | null
  }[]
}
