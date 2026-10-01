import type { FormEvent, ReactNode } from 'react'
import Dialog from './Dialog'

type FormModalProps = {
  open: boolean
  title: string
  submitLabel: string
  busy?: boolean // enviando: deshabilita botones e impide cerrar
  error?: string | null // mensaje del backend o de validación
  canSubmit?: boolean // false mientras el formulario no es válido
  onSubmit: () => void
  onClose: () => void
  children: ReactNode // campos del formulario
}

// Diálogo con formulario para altas y ediciones. Los campos y su estado los
// maneja quien lo usa; este componente solo arma el marco común.
export default function FormModal({
  open,
  title,
  submitLabel,
  busy = false,
  error,
  canSubmit = true,
  onSubmit,
  onClose,
  children,
}: FormModalProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!busy && canSubmit) onSubmit()
  }

  return (
    <Dialog open={open} onClose={onClose} busy={busy} labelledBy="form-modal-title">
      <form onSubmit={handleSubmit}>
        <div className="card-header bg-transparent">
          <h2 id="form-modal-title" className="h5 mb-0">{title}</h2>
        </div>
        <div className="card-body">
          {error && <div className="alert alert-danger py-2" role="alert">{error}</div>}
          {children}
        </div>
        <div className="card-footer bg-transparent d-flex justify-content-end gap-2">
          <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || !canSubmit}>
            {busy && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
            {submitLabel}
          </button>
        </div>
      </form>
    </Dialog>
  )
}
