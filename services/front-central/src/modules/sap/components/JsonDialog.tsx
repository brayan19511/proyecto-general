import type { ReactNode } from 'react'
import Dialog from '../../../shared/components/Dialog'
import { copyText } from '../../../shared/utils/clipboard'
import { toast } from '../../../shared/stores/toastStore'

export type JsonSection = { title: string; value: unknown; note?: ReactNode }

// Muestra uno o más bloques JSON legibles (envío y respuesta de SAP, cabecera
// de un trabajo), cada uno con su botón de copiar.
export default function JsonDialog({ title, sections, onClose }: { title: string; sections: JsonSection[]; onClose: () => void }) {
  return (
    <Dialog open onClose={onClose} labelledBy="json-title" wide>
      <div className="card-header bg-transparent"><h2 id="json-title" className="h5 mb-0">{title}</h2></div>
      <div className="card-body">
        {sections.map((section) => {
          const text = section.value === null || section.value === undefined ? '' : JSON.stringify(section.value, null, 2)
          return (
            <div key={section.title} className="mb-3">
              <div className="d-flex align-items-center gap-2 mb-1">
                <h3 className="h6 mb-0">{section.title}</h3>
                {text && (
                  <button type="button" className="btn btn-sm btn-link p-0" onClick={async () => {
                    await copyText(text)
                    toast.success('Copiado')
                  }}>Copiar</button>
                )}
              </div>
              {section.note && <p className="small text-body-secondary mb-1">{section.note}</p>}
              {text
                ? <pre className="bg-body-tertiary border rounded-2 p-2 small mb-0" style={{ maxHeight: 320, overflow: 'auto' }}>{text}</pre>
                : <p className="small text-body-secondary mb-0">Sin datos.</p>}
            </div>
          )
        })}
      </div>
      <div className="card-footer bg-transparent d-flex justify-content-end">
        <button type="button" className="btn btn-outline-secondary" onClick={onClose}>Cerrar</button>
      </div>
    </Dialog>
  )
}
