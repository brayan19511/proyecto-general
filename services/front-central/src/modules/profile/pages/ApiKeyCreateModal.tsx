import { useState } from 'react'
import Dialog from '../../../shared/components/Dialog'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { copyText } from '../../../shared/utils/clipboard'
import { describePermission } from '../../company/permissionCatalog'
import { API_KEY_SERVICES, createApiKey, type ApiKeyCreated } from '../apiKeys'

type Props = {
  available: string[] // permisos que tiene el usuario en la empresa activa
  onClose: () => void
  onCreated: () => void
}

const EXPIRATIONS = [
  { days: 30, label: '30 días' },
  { days: 90, label: '90 días' },
  { days: 365, label: '1 año' },
  { days: 0, label: 'Sin vencimiento' },
]

// Crear una API key: nombre, permisos (solo de los propios) y vencimiento. Al
// terminar muestra el secreto una sola vez para copiarlo.
export default function ApiKeyCreateModal({ available, onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [scopes, setScopes] = useState<string[]>([])
  const [days, setDays] = useState(90)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<ApiKeyCreated | null>(null)

  const toggle = (code: string) =>
    setScopes((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]))

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const key = await createApiKey({
        name: name.trim(),
        description: description.trim() || undefined,
        scopes,
        expires_in_days: days || undefined,
      })
      setCreated(key)
      onCreated()
    } catch (err) {
      setError(errorMessage(err)) // 409 máximo de keys o no es miembro; 403 permiso que no tiene
    } finally {
      setBusy(false)
    }
  }

  if (created) return <SecretDialog created={created} onClose={onClose} />

  return (
    <FormModal open title="Nueva API key" submitLabel="Crear" busy={busy} error={error}
      canSubmit={name.trim() !== '' && scopes.length > 0} onSubmit={submit} onClose={onClose}>
      <p className="small text-body-secondary">
        Para integraciones (p. ej. Power BI). Hoy la aceptan: {API_KEY_SERVICES}. Actúa en tu nombre, en la empresa activa.
      </p>
      <div className="mb-3">
        <label htmlFor="k-name" className="form-label">Nombre</label>
        <input id="k-name" className="form-control" maxLength={100} placeholder="Power BI contabilidad" autoFocus
          value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="mb-3">
        <label htmlFor="k-desc" className="form-label">Descripción <span className="text-body-secondary">(opcional)</span></label>
        <input id="k-desc" className="form-control" maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <fieldset className="mb-3">
        <legend className="form-label fs-6">Permisos</legend>
        {available.length === 0 && <p className="small text-body-secondary mb-0">No tienes permisos en esta empresa.</p>}
        {available.map((code) => (
          <div key={code} className="form-check">
            <input id={`k-${code}`} type="checkbox" className="form-check-input" checked={scopes.includes(code)} onChange={() => toggle(code)} />
            <label htmlFor={`k-${code}`} className="form-check-label">
              {describePermission(code).label} <span className="small text-body-secondary font-monospace">{code}</span>
            </label>
          </div>
        ))}
        <div className="form-text">Solo puedes darle permisos que tienes. Si los pierdes, la key también.</div>
      </fieldset>
      <div>
        <label htmlFor="k-exp" className="form-label">Vence</label>
        <select id="k-exp" className="form-select" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {EXPIRATIONS.map((x) => <option key={x.days} value={x.days}>{x.label}</option>)}
        </select>
      </div>
    </FormModal>
  )
}

function SecretDialog({ created, onClose }: { created: ApiKeyCreated; onClose: () => void }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    if (await copyText(created.key)) {
      setCopied(true)
      toast.success('API key copiada')
    } else {
      toast.error('No se pudo copiar: selecciónala y cópiala a mano.')
    }
  }

  return (
    <Dialog open onClose={onClose} labelledBy="secret-title">
      <div className="card-header bg-transparent">
        <h2 id="secret-title" className="h5 mb-0">API key creada</h2>
      </div>
      <div className="card-body">
        <div className="alert alert-warning small">
          Cópiala ahora: <strong>no se volverá a mostrar</strong>. Guárdala como una contraseña; si se pierde, revócala y crea otra.
        </div>
        <label htmlFor="secret-value" className="form-label">{created.name}</label>
        <div className="input-group">
          <input id="secret-value" className="form-control font-monospace small" readOnly value={created.key}
            onFocus={(e) => e.target.select()} />
          <button type="button" className="btn btn-outline-primary" onClick={copy}>
            <i className={`bi ${copied ? 'bi-check-lg' : 'bi-clipboard'} me-1`} aria-hidden="true" />
            Copiar
          </button>
        </div>
        <div className="form-text">Se envía en el header <span className="font-monospace">X-API-Key</span>.</div>
      </div>
      <div className="card-footer bg-transparent text-end">
        <button type="button" className="btn btn-primary" onClick={onClose}>Listo</button>
      </div>
    </Dialog>
  )
}
