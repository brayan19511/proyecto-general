import { useState, type FormEvent } from 'react'
import { ApiError } from '../../../shared/api/apiClient'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { countLabel } from '../../../shared/utils/format'
import * as profileService from '../services/profileService'

const EMPTY = { current: '', next: '', confirm: '' }

function passwordErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429 && error.retryAfterSeconds) {
    return `Demasiados intentos. Vuelve a intentarlo en ${Math.ceil(error.retryAfterSeconds / 60)} min.`
  }
  return errorMessage(error) // 403 contraseña actual incorrecta, 422 igual a la actual
}

export default function SecurityTab() {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mismatch = form.confirm !== '' && form.next !== form.confirm

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (mismatch) return
    setSaving(true)
    setError(null)
    try {
      const { revoked } = await profileService.changeMyPassword(form.current, form.next)
      setForm(EMPTY)
      toast.success(
        revoked > 0
          ? `Contraseña actualizada. Se cerró la sesión en ${countLabel(revoked, 'otro dispositivo', 'otros dispositivos')}.`
          : 'Contraseña actualizada',
      )
    } catch (err) {
      setError(passwordErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const field = (name: keyof typeof EMPTY) => ({
    id: `password-${name}`,
    type: 'password',
    className: 'form-control',
    required: true,
    maxLength: 100,
    value: form[name],
    onChange: (e: { target: { value: string } }) => setForm((f) => ({ ...f, [name]: e.target.value })),
  })

  return (
    <div className="card" style={{ maxWidth: 480 }}>
      <div className="card-header bg-transparent fw-semibold">Cambiar contraseña</div>
      <div className="card-body">
        <p className="text-body-secondary small">
          Al cambiarla se cierran tus sesiones en otros dispositivos; esta sigue abierta.
        </p>

        {error && <div className="alert alert-danger py-2" role="alert">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label htmlFor="password-current" className="form-label">Contraseña actual</label>
            <input autoComplete="current-password" {...field('current')} />
          </div>
          <div className="mb-3">
            <label htmlFor="password-next" className="form-label">Nueva contraseña</label>
            <input autoComplete="new-password" {...field('next')} />
          </div>
          <div className="mb-4">
            <label htmlFor="password-confirm" className="form-label">Repite la nueva contraseña</label>
            <input
              autoComplete="new-password"
              aria-invalid={mismatch}
              aria-describedby="password-confirm-help"
              {...field('confirm')}
              className={`form-control ${mismatch ? 'is-invalid' : ''}`}
            />
            <div id="password-confirm-help" className="invalid-feedback">Las contraseñas no coinciden.</div>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving || mismatch || !form.current || !form.next || !form.confirm}
          >
            {saving && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
            Cambiar contraseña
          </button>
        </form>
      </div>
    </div>
  )
}
