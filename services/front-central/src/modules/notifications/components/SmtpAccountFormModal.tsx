import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as notificationsService from '../services/notificationsService'
import type { SmtpAccount, SmtpAccountInput } from '../types'

type Props = { account: SmtpAccount | null; onClose: () => void; onSaved: () => void }

// Alta o edición de una cuenta SMTP. La contraseña se cifra en notificaciones y
// nunca vuelve: al editar, vacío = no cambiarla.
export default function SmtpAccountFormModal({ account, onClose, onSaved }: Props) {
  const [name, setName] = useState(account?.name ?? '')
  const [host, setHost] = useState(account?.host ?? '')
  const [port, setPort] = useState(String(account?.port ?? 587))
  const [security, setSecurity] = useState<'starttls' | 'ssl'>(account?.security ?? 'starttls')
  const [username, setUsername] = useState(account?.username ?? '')
  const [password, setPassword] = useState('')
  const [clearPassword, setClearPassword] = useState(false)
  const [fromEmail, setFromEmail] = useState(account?.from_email ?? '')
  const [fromName, setFromName] = useState(account?.from_name ?? '')
  const [priority, setPriority] = useState(String(account?.priority ?? 1))
  const [timeout, setTimeoutSeconds] = useState(String(account?.timeout_seconds ?? 30))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const portN = Number(port)
  const priorityN = Number(priority)
  const timeoutN = Number(timeout)
  const valid =
    name.trim() !== '' && host.trim() !== '' && fromEmail.includes('@') &&
    Number.isInteger(portN) && portN >= 1 && portN <= 65535 &&
    Number.isInteger(priorityN) && priorityN >= 0 && priorityN <= 1000 &&
    Number.isInteger(timeoutN) && timeoutN >= 1 && timeoutN <= 120

  const submit = async () => {
    setBusy(true)
    setError(null)
    const input: SmtpAccountInput = {
      name: name.trim(),
      host: host.trim(),
      port: portN,
      security,
      username: username.trim() || null,
      from_email: fromEmail.trim(),
      from_name: fromName.trim() || null,
      priority: priorityN,
      timeout_seconds: timeoutN,
    }
    if (password) input.password = password
    else if (clearPassword) input.password = null
    try {
      if (account) {
        // Solo lo que cambió (PATCH).
        const changes: Partial<SmtpAccountInput> = {}
        for (const k of Object.keys(input) as (keyof SmtpAccountInput)[]) {
          if (k === 'password' || input[k] !== account[k as keyof SmtpAccount]) Object.assign(changes, { [k]: input[k] })
        }
        await notificationsService.updateSmtpAccount(account.id, changes)
      } else {
        await notificationsService.createSmtpAccount(input)
      }
      toast.success(account ? 'Cuenta actualizada' : 'Cuenta creada. Pruébala antes de usarla.')
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={account ? `Editar ${account.name}` : 'Nueva cuenta SMTP'} submitLabel="Guardar" busy={busy}
      error={error} canSubmit={valid} onSubmit={submit} onClose={onClose}>
      <div className="row g-3">
        <div className="col-12">
          <label htmlFor="s-name" className="form-label">Nombre</label>
          <input id="s-name" className="form-control" maxLength={100} placeholder="Office 365 principal" autoFocus value={name}
            onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="s-host" className="form-label">Servidor</label>
          <input id="s-host" className="form-control" placeholder="smtp.office365.com" value={host} onChange={(e) => setHost(e.target.value)} />
        </div>
        <div className="col-sm-3">
          <label htmlFor="s-port" className="form-label">Puerto</label>
          <input id="s-port" type="number" className="form-control" min={1} max={65535} value={port} onChange={(e) => setPort(e.target.value)} />
        </div>
        <div className="col-sm-3">
          <label htmlFor="s-sec" className="form-label">Seguridad</label>
          <select id="s-sec" className="form-select" value={security} onChange={(e) => setSecurity(e.target.value as 'starttls' | 'ssl')}>
            <option value="starttls">STARTTLS</option>
            <option value="ssl">SSL/TLS</option>
          </select>
        </div>
        <div className="col-sm-6">
          <label htmlFor="s-user" className="form-label">Usuario <span className="text-body-secondary">(opcional)</span></label>
          <input id="s-user" className="form-control" autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="s-pass" className="form-label">Contraseña</label>
          <input id="s-pass" type="password" className="form-control" autoComplete="new-password"
            placeholder={account?.has_password ? 'Guardada — vacío para no cambiarla' : ''} value={password}
            onChange={(e) => setPassword(e.target.value)} />
          {account?.has_password && !password && (
            <div className="form-check mt-1">
              <input id="s-clear" type="checkbox" className="form-check-input" checked={clearPassword} onChange={(e) => setClearPassword(e.target.checked)} />
              <label htmlFor="s-clear" className="form-check-label small">Borrar la contraseña guardada</label>
            </div>
          )}
        </div>
        <div className="col-sm-6">
          <label htmlFor="s-from" className="form-label">Remitente (correo)</label>
          <input id="s-from" type="email" className="form-control" value={fromEmail} onChange={(e) => setFromEmail(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="s-fromname" className="form-label">Remitente (nombre) <span className="text-body-secondary">(opcional)</span></label>
          <input id="s-fromname" className="form-control" maxLength={100} placeholder="Tesorería" value={fromName} onChange={(e) => setFromName(e.target.value)} />
        </div>
        <div className="col-sm-6">
          <label htmlFor="s-prio" className="form-label">Prioridad</label>
          <input id="s-prio" type="number" className="form-control" min={0} max={1000} value={priority} onChange={(e) => setPriority(e.target.value)} />
          <div className="form-text">Se usa primero la de número menor; si falla, la siguiente.</div>
        </div>
        <div className="col-sm-6">
          <label htmlFor="s-timeout" className="form-label">Espera máxima (s)</label>
          <input id="s-timeout" type="number" className="form-control" min={1} max={120} value={timeout} onChange={(e) => setTimeoutSeconds(e.target.value)} />
        </div>
      </div>
    </FormModal>
  )
}
