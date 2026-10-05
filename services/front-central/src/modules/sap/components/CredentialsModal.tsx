import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import * as sapService from '../services/sapService'
import type { Job } from '../types'

type Props = {
  job: Job
  mode: 'enqueue' | 'resume'
  onClose: () => void
  onDone: (job: Job) => void
}

// Usuario y clave SAP del operador. Al ejecutar se prueba el inicio de sesión en
// SAP antes de encolar. La clave viaja una sola vez y se guarda cifrada; nunca
// se guarda en el navegador.
export default function CredentialsModal({ job, mode, onClose, onDone }: Props) {
  const [user, setUser] = useState(job.sap_user ?? '')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const optional = mode === 'resume' && job.has_credentials

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const updated = mode === 'enqueue'
        ? await sapService.enqueue(job.id, user.trim(), password)
        : await sapService.resume(job.id, password ? user.trim() : undefined, password || undefined)
      onDone(updated)
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 422: SAP rechazó el login; 502: SAP no responde o certificado
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={mode === 'enqueue' ? 'Ejecutar en SAP' : 'Reanudar trabajo'}
      submitLabel={busy ? 'Comprobando en SAP…' : mode === 'enqueue' ? `Ejecutar ${job.total_items} ítems` : 'Reanudar'}
      busy={busy} error={error} canSubmit={optional || (user.trim().length > 0 && password.length > 0)}
      onSubmit={submit} onClose={onClose}>
      <p className="small text-body-secondary">
        Base <span className="font-monospace">{job.company_db}</span>.
        {mode === 'enqueue'
          ? ' Se usa tu usuario de SAP: SAP aplica sus permisos y registra los cambios a tu nombre.'
          : ' Sigue con los ítems pendientes; los inciertos no se repiten.'}
      </p>
      {optional && <p className="small">Déjalos vacíos para usar las credenciales guardadas ({job.sap_user}).</p>}
      <div className="mb-3">
        <label htmlFor="sap-user" className="form-label">Usuario SAP</label>
        <input id="sap-user" className="form-control" autoComplete="username" maxLength={100} value={user} onChange={(e) => setUser(e.target.value)} />
      </div>
      <div>
        <label htmlFor="sap-password" className="form-label">Clave SAP</label>
        <input id="sap-password" type="password" className="form-control" autoComplete="current-password" maxLength={200}
          value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
    </FormModal>
  )
}
