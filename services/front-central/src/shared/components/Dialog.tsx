import { useEffect, useRef, type ReactNode } from 'react'

type DialogProps = {
  open: boolean
  onClose: () => void // ESC o Cancelar
  busy?: boolean // mientras hay una acción en curso no se puede cerrar
  labelledBy: string // id del título, para lectores de pantalla
  wide?: boolean // para tablas de detalle
  children: ReactNode
}

// Base de ConfirmDialog y FormModal. Usa <dialog> nativo: el navegador resuelve
// el fondo, el foco dentro del diálogo y el cierre con ESC (evento "cancel"),
// sin el JavaScript de Bootstrap. El contenido va en una .card porque las
// clases modal-* solo tienen estilo dentro de .modal.
export default function Dialog({ open, onClose, busy = false, labelledBy, wide = false, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className={`app-dialog ${wide ? 'app-dialog-wide' : ''}`}
      aria-labelledby={labelledBy}
      onCancel={(e) => {
        e.preventDefault() // el cierre lo decide el estado de React
        if (!busy) onClose()
      }}
    >
      {open && <div className="card shadow">{children}</div>}
    </dialog>
  )
}
