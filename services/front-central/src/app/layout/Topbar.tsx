import { useLocation, useNavigate } from 'react-router'
import { useSessionStore } from '../../shared/auth/sessionStore'
import { useTheme } from '../../shared/hooks/useTheme'
import type { Me } from '../../modules/auth/types'
import { findNavItem } from './navigation'

// Iniciales para el avatar: nombres y apellidos del perfil o, si no hay, el correo.
function initials(me: Me): string {
  const first = me.profile?.first_names?.trim()
  const last = me.profile?.last_names?.trim()
  if (first && last) return (first[0] + last[0]).toUpperCase()
  return me.email.slice(0, 2).toUpperCase()
}

type TopbarProps = {
  onToggleMenu: () => void
}

export default function Topbar({ onToggleMenu }: TopbarProps) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const me = useSessionStore((s) => s.me)
  const companies = useSessionStore((s) => s.companies)
  const companyId = useSessionStore((s) => s.companyId)
  const selectCompany = useSessionStore((s) => s.selectCompany)
  const logout = useSessionStore((s) => s.logout)
  const current = findNavItem(pathname)

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  // RequireAuth garantiza sesión; esto solo satisface a TypeScript.
  if (!me) return null

  return (
    <header className="app-topbar">
      <button
        type="button"
        className="btn btn-sm btn-link text-body-secondary"
        onClick={onToggleMenu}
        aria-label="Mostrar u ocultar menú"
      >
        <i className="bi bi-list fs-5" aria-hidden="true" />
      </button>

      <nav aria-label="Ubicación" className="d-none d-sm-block text-body-secondary small text-truncate">
        {current ? `${current.group.label} / ${current.item.label}` : ''}
      </nav>

      <div className="ms-auto d-flex align-items-center gap-2">
        {companies.length > 0 ? (
          <select
            className="form-select form-select-sm app-company-select"
            aria-label="Empresa activa"
            value={companyId ?? ''}
            onChange={(e) => selectCompany(e.target.value)}
          >
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        ) : (
          <span className="small text-body-secondary">Sin empresas</span>
        )}

        <button
          type="button"
          className="btn btn-sm btn-link text-body-secondary"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Usar tema claro' : 'Usar tema oscuro'}
        >
          <i className={`bi bi-${theme === 'dark' ? 'sun' : 'moon'}`} aria-hidden="true" />
        </button>

        <span className="app-avatar" title={me.email}>
          {initials(me)}
        </span>

        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          onClick={handleLogout}
          aria-label="Cerrar sesión"
          title="Cerrar sesión"
        >
          <i className="bi bi-box-arrow-right" aria-hidden="true" />
        </button>
      </div>
    </header>
  )
}
