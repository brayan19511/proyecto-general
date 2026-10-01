import Dialog from './Dialog'

type ConfirmDialogProps = {
  open: boolean
  title: string
  message: string
  confirmLabel: string
  danger?: boolean // acción destructiva: botón rojo
  busy?: boolean // la acción está en curso
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onClose={onCancel} busy={busy} labelledBy="confirm-title">
      <div className="card-header bg-transparent">
        <h2 id="confirm-title" className="h5 mb-0">{title}</h2>
      </div>
      <div className="card-body">
        <p className="mb-0">{message}</p>
      </div>
      <div className="card-footer bg-transparent d-flex justify-content-end gap-2">
        <button type="button" className="btn btn-outline-secondary" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
        <button
          type="button"
          className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
          {confirmLabel}
        </button>
      </div>
    </Dialog>
  )
}
