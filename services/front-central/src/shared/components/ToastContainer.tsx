import { useToastStore, type ToastKind } from '../stores/toastStore'

const ICONS: Record<ToastKind, string> = {
  success: 'check-circle',
  danger: 'x-circle',
  warning: 'exclamation-triangle',
  info: 'info-circle',
}

// Se monta una vez en App. Los avisos llegan con toast.success(...), etc.
export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  return (
    <div className="toast-container position-fixed bottom-0 end-0 p-3" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast show align-items-center text-bg-${t.kind} border-0`} role="status">
          <div className="d-flex">
            <div className="toast-body">
              <i className={`bi bi-${ICONS[t.kind]} me-2`} aria-hidden="true" />
              {t.message}
            </div>
            <button
              type="button"
              className="btn-close btn-close-white me-2 m-auto"
              aria-label="Cerrar aviso"
              onClick={() => dismiss(t.id)}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
