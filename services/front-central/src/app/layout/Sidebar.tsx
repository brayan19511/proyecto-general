import { NavLink } from 'react-router'
import { useCanAccess } from '../../shared/auth/access'
import { NAV_GROUPS } from './navigation'

type SidebarProps = {
  onNavigate: () => void // cierra el menú en móvil al elegir una opción
}

export default function Sidebar({ onNavigate }: SidebarProps) {
  const canAccess = useCanAccess()

  // Solo ítems permitidos; un grupo sin ítems visibles no se muestra.
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => canAccess(item.access)),
  })).filter((group) => group.items.length > 0)

  return (
    <aside className="app-sidebar" aria-label="Menú principal">
      <div className="app-brand">
        <i className="bi bi-bank2" aria-hidden="true" />
        <span className="app-brand-name">Plataforma</span>
      </div>

      <nav className="px-2 pb-3">
        {groups.map((group) => (
          <div key={group.label}>
            <div className="app-nav-group">{group.label}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className="app-nav-link"
                title={item.label}
                onClick={onNavigate}
              >
                <i className={`bi bi-${item.icon}`} aria-hidden="true" />
                <span className="app-nav-label">{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}
