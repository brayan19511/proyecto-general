import { useState, type FormEvent } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as sapService from '../services/sapService'

// URL del Service Layer de la empresa activa. Editarla: solo platform admin
// (las claves SAP de los operadores viajan a esa URL). Vacía = la del despliegue.
export default function ServiceLayerSettings() {
  const isPlatformAdmin = useSessionStore((s) => s.me?.is_platform_admin ?? false)
  const current = useApi(() => sapService.getSettings())
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      current.setData(await sapService.updateSettings(editing?.trim() || null))
      toast.success('Service Layer actualizado')
      setEditing(null)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const data = current.data
  return (
    <div className="border rounded-3 p-3 mb-4">
      <h2 className="h6">Service Layer</h2>
      <AsyncState loading={current.loading} error={current.error} onRetry={current.reload} hasData={data !== undefined}>
        {data && editing === null && (
          <div className="d-flex flex-wrap align-items-center gap-2">
            <span className="font-monospace">{data.service_layer_url ?? 'Sin configurar'}</span>
            <StatusBadge tone={data.source === 'company' ? 'info' : 'secondary'} label={data.source === 'company' ? 'Propia de la empresa' : 'La del despliegue'} />
            {!data.verify_tls && <StatusBadge tone="warning" label="Certificado TLS sin verificar" />}
            {isPlatformAdmin && (
              <button type="button" className="btn btn-sm btn-outline-primary ms-auto" onClick={() => setEditing(data.source === 'company' ? data.service_layer_url ?? '' : '')}>
                Cambiar
              </button>
            )}
          </div>
        )}
        {editing !== null && (
          <form className="d-flex flex-wrap gap-2" onSubmit={save}>
            <input className="form-control form-control-sm font-monospace" style={{ maxWidth: 420 }} maxLength={300} autoFocus
              placeholder="https://10.0.0.14:50000/b1s/v1" aria-label="URL del Service Layer" value={editing} onChange={(e) => setEditing(e.target.value)} />
            <button type="submit" className="btn btn-sm btn-primary" disabled={busy}>Guardar</button>
            <button type="button" className="btn btn-sm btn-outline-secondary" disabled={busy} onClick={() => setEditing(null)}>Cancelar</button>
            <div className="form-text w-100">
              Vacía = usar la del despliegue. Afecta a los trabajos que se ejecuten o reanuden desde ahora; queda en el historial.
            </div>
          </form>
        )}
      </AsyncState>
    </div>
  )
}
