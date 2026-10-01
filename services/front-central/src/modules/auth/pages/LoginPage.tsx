import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { ApiError } from '../../../shared/api/apiClient'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import FullPageSpinner from '../../../shared/components/FullPageSpinner'

// Traduce el error del login a un mensaje claro para el usuario.
function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'No se pudo iniciar sesión.'
  if (error.status === 429 && error.retryAfterSeconds) {
    const minutes = Math.ceil(error.retryAfterSeconds / 60)
    return `Demasiados intentos. Vuelve a intentarlo en ${minutes} min.`
  }
  if (error.status === 401) return 'Correo o contraseña incorrectos.'
  if (error.status === 422) return 'Ingresa un correo válido.'
  return error.message // 409 (máximo de sesiones), 5xx, red: el mensaje ya es claro
}

export default function LoginPage() {
  const status = useSessionStore((s) => s.status)
  const notice = useSessionStore((s) => s.notice)
  const login = useSessionStore((s) => s.login)
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/perfil'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'loading') return <FullPageSpinner />
  if (status === 'authenticated') return <Navigate to={from} replace />

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(loginErrorMessage(err))
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-vh-100 d-flex align-items-center justify-content-center bg-body-tertiary px-3">
      <div className="card shadow-sm w-100" style={{ maxWidth: 400 }}>
        <div className="card-body p-4">
          <div className="text-center mb-4">
            <i className="bi bi-bank2 fs-1 text-primary" aria-hidden="true" />
            <h1 className="h4 mt-2 mb-1">Plataforma</h1>
            <p className="text-body-secondary mb-0">Inicia sesión para continuar</p>
          </div>

          {(error || notice) && (
            <div className={`alert ${error ? 'alert-danger' : 'alert-warning'} py-2`} role="alert">
              {error ?? notice}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div className="mb-3">
              <label htmlFor="email" className="form-label">Correo</label>
              <input
                id="email"
                type="email"
                className="form-control"
                placeholder="nombre@empresa.com"
                autoComplete="username"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="mb-4">
              <label htmlFor="password" className="form-label">Contraseña</label>
              <div className="input-group">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  className="form-control"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-outline-secondary"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                >
                  <i className={`bi bi-eye${showPassword ? '-slash' : ''}`} aria-hidden="true" />
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary w-100"
              disabled={submitting || !email.trim() || !password}
            >
              {submitting && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
              Iniciar sesión
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
