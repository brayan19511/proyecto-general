import type { BadgeTone } from '../../shared/components/StatusBadge'
import type { DispatchStatus, MessageStatus } from './types'

export const DISPATCH_STATUS: Record<DispatchStatus, { label: string; tone: BadgeTone }> = {
  pending: { label: 'Pendiente', tone: 'secondary' },
  in_progress: { label: 'Enviando', tone: 'info' },
  completed: { label: 'Completado', tone: 'success' },
  completed_with_errors: { label: 'Con errores', tone: 'danger' },
}

export const MESSAGE_STATUS: Record<MessageStatus, { label: string; tone: BadgeTone; help: string }> = {
  pending: { label: 'Pendiente', tone: 'secondary', help: 'En cola para el worker.' },
  sending: { label: 'Enviando', tone: 'info', help: 'El worker lo está enviando.' },
  retrying: { label: 'Reintentando', tone: 'warning', help: 'Falló y se reintentará solo.' },
  sent: { label: 'Enviado', tone: 'success', help: 'El servidor SMTP lo aceptó.' },
  failed: { label: 'Fallido', tone: 'danger', help: 'Agotó sus reintentos. Se puede reprocesar.' },
  uncertain: {
    label: 'Incierto',
    tone: 'warning',
    help: 'No se sabe si llegó (se cortó la conexión). Reprocesar podría duplicarlo.',
  },
  cancelled: { label: 'Cancelado', tone: 'secondary', help: 'No se enviará.' },
}

// Mensajes que se pueden reprocesar o cancelar (lo valida notificaciones).
export const RETRYABLE: MessageStatus[] = ['failed', 'uncertain']
export const CANCELLABLE: MessageStatus[] = ['pending', 'retrying', 'failed', 'uncertain']

// error_kind de la prueba de una cuenta SMTP.
export const SMTP_TEST_ERROR: Record<string, string> = {
  blocked_address: 'Puerto o dirección no permitidos por la configuración del servicio.',
  connection: 'No se pudo conectar o el servidor cortó la conexión.',
  timeout: 'El servidor no respondió a tiempo.',
  tls: 'Falló el cifrado o el certificado, o el servidor no ofrece STARTTLS.',
  auth: 'Usuario o contraseña rechazados.',
  credentials_unreadable: 'La contraseña guardada no se puede descifrar: vuelve a escribirla.',
  unknown: 'Error desconocido.',
}

export const SECURITY_LABEL = { starttls: 'STARTTLS', ssl: 'SSL/TLS' } as const
