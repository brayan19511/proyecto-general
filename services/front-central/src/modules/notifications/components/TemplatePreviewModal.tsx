import { useState } from 'react'
import Dialog from '../../../shared/components/Dialog'
import { errorMessage } from '../../../shared/hooks/useApi'
import { parseParameters } from '../compose'
import * as notificationsService from '../services/notificationsService'
import type { Preview, Template } from '../types'
import HtmlPreview from './HtmlPreview'

// Arma la plantilla con parámetros de ejemplo, sin guardar ni enviar nada.
export default function TemplatePreviewModal({ template, onClose }: { template: Template; onClose: () => void }) {
  const [params, setParams] = useState('{}')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const parameters = parseParameters(params)

  const run = async () => {
    if (!parameters) return
    setBusy(true)
    setError(null)
    try {
      setPreview(await notificationsService.previewTemplate(template.id, parameters))
    } catch (err) {
      setError(errorMessage(err)) // 422 template_parameter_missing
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open wide onClose={onClose} busy={busy} labelledBy="preview-title">
      <div className="card-header bg-transparent d-flex align-items-center">
        <h2 id="preview-title" className="h5 mb-0 me-auto">Vista previa · {template.name}</h2>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} />
      </div>
      <div className="card-body">
        <label htmlFor="p-params" className="form-label">Parámetros de ejemplo (JSON)</label>
        <textarea id="p-params" className={`form-control font-monospace small ${parameters === null ? 'is-invalid' : ''}`} rows={4}
          value={params} onChange={(e) => setParams(e.target.value)} />
        <div className="d-flex justify-content-end mt-2 mb-3">
          <button type="button" className="btn btn-primary" disabled={busy || parameters === null} onClick={run}>
            {busy && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />}
            Armar
          </button>
        </div>
        {error && <div className="alert alert-danger">{error}</div>}
        {preview && (
          <>
            <div className="mb-2"><span className="text-body-secondary small">Asunto:</span> {preview.subject}</div>
            {preview.body_html && <HtmlPreview html={preview.body_html} title="Vista previa del cuerpo" />}
            {preview.body_text && (
              <pre className="border rounded-3 p-3 small mt-3 mb-0" style={{ whiteSpace: 'pre-wrap' }}>{preview.body_text}</pre>
            )}
          </>
        )}
      </div>
    </Dialog>
  )
}
