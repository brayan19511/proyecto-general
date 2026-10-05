import { useState } from 'react'
import Dialog from '../../../shared/components/Dialog'
import { errorMessage } from '../../../shared/hooks/useApi'
import { copyText } from '../../../shared/utils/clipboard'
import { toast } from '../../../shared/stores/toastStore'
import * as sapService from '../services/sapService'

// Solo administrador de plataforma (decisión 2026-10-04): muestra el usuario y la
// clave SAP guardados del trabajo. Pedirla queda en el historial; no se guarda en el
// navegador y se descarta al cerrar.
export default function RevealCredentialsDialog({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const [shown, setShown] = useState<{ sap_user: string | null; sap_password: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reveal = async () => {
    setBusy(true)
    setError(null)
    try {
      setShown(await sapService.revealCredentials(jobId))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onClose={onClose} busy={busy} labelledBy="reveal-title">
      <div className="card-header bg-transparent"><h2 id="reveal-title" className="h5 mb-0">Credenciales SAP del trabajo</h2></div>
      <div className="card-body">
        {error && <div className="alert alert-danger py-2">{error}</div>}
        {!shown ? (
          <p className="mb-0">Verás la clave SAP guardada en este trabajo. Queda registrado en el historial que la consultaste.</p>
        ) : (
          <dl className="row mb-0">
            <dt className="col-4">Usuario</dt><dd className="col-8 font-monospace">{shown.sap_user}</dd>
            <dt className="col-4">Clave</dt>
            <dd className="col-8 font-monospace d-flex align-items-center gap-2">
              {shown.sap_password}
              <button type="button" className="btn btn-sm btn-outline-secondary" onClick={async () => {
                await copyText(shown.sap_password)
                toast.success('Clave copiada')
              }}>Copiar</button>
            </dd>
          </dl>
        )}
      </div>
      <div className="card-footer bg-transparent d-flex justify-content-end gap-2">
        <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={busy}>Cerrar</button>
        {!shown && <button type="button" className="btn btn-warning" onClick={reveal} disabled={busy}>Mostrar</button>}
      </div>
    </Dialog>
  )
}
