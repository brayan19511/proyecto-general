import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import * as paymentsService from '../services/paymentsService'
import type { Batch } from '../types'

const MB = 1024 * 1024

// Sube constancias en PDF: pagos-proveedores las lee (OCR si son escaneadas) y
// las agrupa por proveedor. Un PDF ilegible no corta el lote: queda con error.
export default function NewBatchModal({ onClose, onCreated }: { onClose: () => void; onCreated: (batch: Batch) => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const total = files.reduce((sum, f) => sum + f.size, 0)
  const tooBig = files.filter((f) => f.size > paymentsService.MAX_FILE_BYTES)
  const notPdf = files.filter((f) => !f.name.toLowerCase().endsWith('.pdf'))
  const problem =
    files.length > paymentsService.MAX_FILES ? `Máximo ${paymentsService.MAX_FILES} archivos por lote.`
    : tooBig.length ? `Superan 25 MB: ${tooBig.map((f) => f.name).join(', ')}.`
    : notPdf.length ? `No son PDF: ${notPdf.map((f) => f.name).join(', ')}.`
    : total > paymentsService.MAX_REQUEST_BYTES ? 'En total superan 100 MB: divídelos en varios lotes.'
    : null

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const batch = await paymentsService.createBatch(files, reference.trim())
      onCreated(batch)
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 422 duplicate_file
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title="Nuevo lote de pagos" submitLabel={busy ? 'Leyendo constancias…' : 'Subir y leer'} busy={busy}
      error={error ?? problem} canSubmit={files.length > 0 && problem === null} onSubmit={submit} onClose={onClose}>
      <div className="mb-3">
        <label htmlFor="b-files" className="form-label">Constancias (PDF)</label>
        <input id="b-files" type="file" accept="application/pdf,.pdf" multiple className="form-control"
          onChange={(e) => setFiles([...(e.target.files ?? [])])} />
        <div className="form-text">
          {files.length > 0
            ? `${files.length} archivos · ${(total / MB).toFixed(1)} MB`
            : `Hasta ${paymentsService.MAX_FILES} archivos de 25 MB, 100 MB en total.`}
        </div>
      </div>
      <div>
        <label htmlFor="b-ref" className="form-label">Referencia <span className="text-body-secondary">(opcional)</span></label>
        <input id="b-ref" className="form-control" maxLength={100} placeholder="Pagos semana 40" value={reference}
          onChange={(e) => setReference(e.target.value)} />
      </div>
      {busy && <p className="small text-body-secondary mt-3 mb-0">Puede tardar unos minutos si hay constancias escaneadas.</p>}
    </FormModal>
  )
}
