// Respuestas de notificaciones (services/notificaciones/app/schemas).

export type Page<T> = { items: T[]; total: number }

export type DispatchStatus = 'pending' | 'in_progress' | 'completed' | 'completed_with_errors'
export type MessageStatus = 'pending' | 'sending' | 'retrying' | 'sent' | 'failed' | 'uncertain' | 'cancelled'

export type DispatchCounts = Record<'total' | MessageStatus, number>

export type Dispatch = {
  id: string
  kind: string // standard · failure_notice
  consumer: string | null // p. ej. "pagos-proveedores"
  consumer_reference: string | null
  status: DispatchStatus
  counts: DispatchCounts
  requested_by_user_id: string | null
  requested_by_email: string | null // null: lo creó un proceso
  created_at: string
}

export type MessageSummary = {
  id: string
  sequence: number
  consumer_reference: string | null
  to: string[]
  cc: string[]
  bcc: string[]
  subject: string
  status: MessageStatus
  attempts_in_cycle: number
  last_attempt_at: string | null
  sent_at: string | null
  cancelled_at: string | null
}

export type Attachment = {
  id: string
  sequence: number
  filename: string
  content_type: string
  size_bytes: number
  available: boolean // false: ya se purgó (el mensaje se envió o canceló)
}

export type MessageDetail = MessageSummary & {
  dispatch_id: string
  reply_to: string | null
  body_html: string | null // mostrar solo en <iframe sandbox>
  body_text: string | null
  cancel_reason: string | null
  attachments: Attachment[]
  created_at: string
  technical: {
    message_id_header: string
    size_bytes: number
    next_attempt_at: string | null
    locked_until: string | null
  } | null // solo con notifications.admin
}

export type Attempt = {
  id: string
  attempt_number: number
  smtp_account_id: string | null
  smtp_account_name: string | null
  started_at: string
  finished_at: string
  outcome: string
  smtp_code: number | null
  error_kind: string | null
  smtp_response: string | null
}

export type SmtpAccount = {
  id: string
  name: string
  host: string
  port: number
  security: 'starttls' | 'ssl'
  username: string | null
  has_password: boolean // la contraseña nunca se devuelve
  from_email: string
  from_name: string | null
  priority: number
  timeout_seconds: number
  is_active: boolean
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export type SmtpAccountInput = {
  name: string
  host: string
  port: number
  security: 'starttls' | 'ssl'
  username: string | null
  password?: string | null // ausente: no se cambia; null: se borra
  from_email: string
  from_name: string | null
  priority: number
  timeout_seconds: number
}

export type SmtpTestResult = { ok: boolean; error_kind: string | null }

export type Template = {
  id: string
  code: string
  name: string
  description: string | null
  subject_template: string
  body_html_template: string | null
  body_text_template: string | null
  to: string[]
  cc: string[]
  bcc: string[]
  reply_to: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export type TemplateInput = Omit<Template, 'id' | 'is_active' | 'created_at' | 'updated_at' | 'deleted_at'>

export type Preview = { subject: string; body_html: string | null; body_text: string | null }
