import { useState } from 'react'
import { ApiError } from '../../../shared/api/apiClient'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { copyText } from '../../../shared/utils/clipboard'
import { TEMP_PASSWORD_MIN as MIN_PASSWORD, generatePassword } from '../../../shared/utils/password'
import * as membersService from '../services/membersService'

type AddMemberModalProps = {
  onClose: () => void
  onAdded: () => void
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
// Agrega a la empresa activa a alguien que ya tiene cuenta, o registra su cuenta
// y luego lo agrega. Al agregarlo no recibe permisos: los hereda de sus puestos.
export default function AddMemberModal({ onClose, onAdded }: AddMemberModalProps) {
  const [mode, setMode] = useState<'existing' | 'register'>('existing')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notRegistered, setNotRegistered] = useState(false) // "Ya tiene cuenta" con un correo sin cuenta

  const validEmail = EMAIL.test(email.trim())
  const canSubmit = validEmail && (mode === 'existing' || password.length >= MIN_PASSWORD)

  const submit = async () => {
    setBusy(true)
    setError(null)
    setNotRegistered(false)
    const cleanEmail = email.trim()
    try {
      if (mode === 'register') {
        try {
          await membersService.registerUser(cleanEmail, password)
        } catch (err) {
          // Ya tenía cuenta: se agrega igual (no se cambia su contraseña).
          if (!(err instanceof ApiError && err.status === 409)) throw err
          toast.info('Ese correo ya tenía cuenta: se agrega sin cambiar su contraseña.')
        }
      }
      try {
        await membersService.addMember(cleanEmail)
      } catch (err) {
        if (mode === 'register') {
          throw new ApiError(0, `La cuenta quedó registrada, pero no se pudo agregar a la empresa: ${errorMessage(err)}`)
        }
        throw err
      }
      toast.success(
        mode === 'register'
          ? 'Cuenta creada y agregada. Entrega la contraseña temporal por un canal seguro.'
          : 'Miembro agregado. Asígnale un puesto para darle permisos.',
      )
      onAdded()
      onClose()
    } catch (err) {
      // 404 al agregar: el correo no tiene cuenta. Se ofrece registrarla aquí mismo.
      if (mode === 'existing' && err instanceof ApiError && err.status === 404) setNotRegistered(true)
      else setError(errorMessage(err)) // 409 ya es miembro, 429 límite de registros
    } finally {
      setBusy(false)
    }
  }

  const switchToRegister = () => {
    setMode('register')
    setNotRegistered(false)
    if (!password) setPassword(generatePassword())
  }

  const copyPassword = async () => {
    // copyText funciona también por HTTP en la red (sin navigator.clipboard).
    if (await copyText(password)) toast.info('Contraseña copiada')
    else toast.warning('No se pudo copiar: selecciónala y cópiala a mano.')
  }

  return (
    <FormModal open title="Agregar miembro" submitLabel={mode === 'register' ? 'Registrar y agregar' : 'Agregar'}
      busy={busy} error={error} canSubmit={canSubmit} onSubmit={submit} onClose={onClose}>
      <div className="btn-group w-100 mb-3" role="group" aria-label="Tipo de alta">
        <input type="radio" className="btn-check" id="mode-existing" checked={mode === 'existing'} onChange={() => setMode('existing')} />
        <label className="btn btn-outline-primary btn-sm" htmlFor="mode-existing">Ya tiene cuenta</label>
        <input type="radio" className="btn-check" id="mode-register" checked={mode === 'register'} onChange={switchToRegister} />
        <label className="btn btn-outline-primary btn-sm" htmlFor="mode-register">Registrar cuenta nueva</label>
      </div>

      {notRegistered && (
        <div className="alert alert-warning py-2 d-flex flex-wrap align-items-center justify-content-between gap-2" role="alert">
          <span>Ese correo no tiene una cuenta registrada.</span>
          <button type="button" className="btn btn-sm btn-warning" onClick={switchToRegister}>Registrar esta cuenta</button>
        </div>
      )}

      <label htmlFor="member-email" className="form-label">Correo</label>
      <input id="member-email" type="email" className="form-control" placeholder="nombre@empresa.com" autoFocus
        value={email} onChange={(e) => setEmail(e.target.value)} />

      {mode === 'register' && (
        <div className="mt-3">
          <label htmlFor="member-password" className="form-label">Contraseña temporal</label>
          <div className="input-group">
            <input id="member-password" type={showPassword ? 'text' : 'password'} className="form-control font-monospace"
              autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)}
              aria-describedby="member-password-help" />
            <button type="button" className="btn btn-outline-secondary" onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}>
              <i className={`bi bi-eye${showPassword ? '-slash' : ''}`} aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setPassword(generatePassword())}
              aria-label="Generar otra contraseña" title="Generar otra">
              <i className="bi bi-arrow-repeat" aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={copyPassword} aria-label="Copiar contraseña" title="Copiar">
              <i className="bi bi-clipboard" aria-hidden="true" />
            </button>
          </div>
          <div id="member-password-help" className="form-text">
            Mínimo {MIN_PASSWORD} caracteres. Entrégala por un canal seguro y pide que la cambie en Mi perfil ›
            Seguridad al entrar.
          </div>
        </div>
      )}

      <div className="form-text mt-3">
        {mode === 'existing'
          ? 'La persona ya debe tener una cuenta registrada.'
          : 'Se crea la cuenta y se agrega a esta empresa.'}{' '}
        No recibe permisos al agregarla: los hereda de los puestos que le asignes.
      </div>
    </FormModal>
  )
}
