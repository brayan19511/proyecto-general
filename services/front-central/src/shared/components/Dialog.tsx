import { useEffect, useRef, type ReactNode } from 'react'

type DialogProps = {
  open: boolean
  onClose: () => void // ESC, Cancelar o clic fuera del diálogo
  busy?: boolean // mientras hay una acción en curso no se puede cerrar
  labelledBy: string // id del título, para lectores de pantalla
  wide?: boolean // para tablas de detalle
  children: ReactNode
}

// Base de ConfirmDialog y FormModal. Usa <dialog> nativo: el navegador resuelve
// el fondo, el foco dentro del diálogo y el cierre con ESC (evento "cancel"),
// sin el JavaScript de Bootstrap. El contenido va en una .card porque las
// clases modal-* solo tienen estilo dentro de .modal.
// Clic fuera (en el fondo) también cierra: el <dialog> no tiene padding, así
// que un clic cuyo destino es el propio <dialog> cayó en el fondo. Se exige
// que el clic también haya empezado fuera: si se arrastra para seleccionar
// texto de un campo y se suelta afuera, no se pierde lo escrito.
export default function Dialog({ open, onClose, busy = false, labelledBy, wide = false, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const pressedOutside = useRef(false)

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
      onMouseDown={(e) => {
        pressedOutside.current = e.target === e.currentTarget
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && pressedOutside.current && !busy) onClose()
        pressedOutside.current = false
      }}
      onCancel={(e) => {
        e.preventDefault() // el cierre lo decide el estado de React
        if (!busy) onClose()
      }}
    >
      {open && <div className="card shadow">{children}</div>}
    </dialog>
  )
}
