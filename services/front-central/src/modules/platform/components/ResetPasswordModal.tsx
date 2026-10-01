import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { copyText } from '../../../shared/utils/clipboard'
import { TEMP_PASSWORD_MIN, generatePassword } from '../../../shared/utils/password'
import * as usersService from '../services/usersService'
import type { AdminUser } from '../types'

// Restablecer la contraseña de un usuario: se le asigna una temporal y se
// cierran todas sus sesiones. El admin la entrega por un canal seguro.
export default function ResetPasswordModal({ user, onClose }: { user: AdminUser; onClose: () => void }) {
  const [password, setPassword] = useState(generatePassword)
  const [show, setShow] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const { revoked } = await usersService.resetPassword(user.id, password)
      toast.success(`Contraseña restablecida. Se cerraron ${revoked} ${revoked === 1 ? 'sesión' : 'sesiones'}.`)
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    // copyText funciona también por HTTP en la red (sin navigator.clipboard).
    if (await copyText(password)) toast.info('Contraseña copiada')
    else toast.warning('No se pudo copiar: selecciónala y cópiala a mano.')
  }

  return (
    <FormModal open title={`Restablecer contraseña de ${user.email}`} submitLabel="Restablecer" busy={busy} error={error}
      canSubmit={password.length >= TEMP_PASSWORD_MIN} onSubmit={submit} onClose={onClose}>
      <p className="small text-body-secondary">
        Se reemplaza su contraseña y se cierran todas sus sesiones. Cópiala antes de confirmar: después no se vuelve a mostrar.
      </p>
      <label htmlFor="reset-password" className="form-label">Contraseña temporal</label>
      <div className="input-group">
        <input id="reset-password" type={show ? 'text' : 'password'} className="form-control font-monospace" autoComplete="new-password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <button type="button" className="btn btn-outline-secondary" onClick={() => setShow((v) => !v)}
          aria-label={show ? 'Ocultar contraseña' : 'Mostrar contraseña'}>
          <i className={`bi bi-eye${show ? '-slash' : ''}`} aria-hidden="true" />
        </button>
        <button type="button" className="btn btn-outline-secondary" onClick={() => setPassword(generatePassword())}
          aria-label="Generar otra contraseña" title="Generar otra">
          <i className="bi bi-arrow-repeat" aria-hidden="true" />
        </button>
        <button type="button" className="btn btn-outline-secondary" onClick={copy} aria-label="Copiar contraseña" title="Copiar">
          <i className="bi bi-clipboard" aria-hidden="true" />
        </button>
      </div>
      <div className="form-text">Mínimo {TEMP_PASSWORD_MIN} caracteres. Pide que la cambie en Mi perfil › Seguridad al entrar.</div>
    </FormModal>
  )
}
