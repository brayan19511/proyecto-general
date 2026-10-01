import { useState } from 'react'
import { Outlet } from 'react-router'
import { useSessionStore } from '../../shared/auth/sessionStore'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import './AppLayout.css'

// Mismo punto de corte que "lg" de Bootstrap (992px).
const DESKTOP_QUERY = '(min-width: 992px)'

export default function AppLayout() {
  // Escritorio: sidebar ancha o solo iconos. Móvil: sidebar oculta o superpuesta.
  const [collapsed, setCollapsed] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const companyId = useSessionStore((s) => s.companyId)

  const toggleMenu = () => {
    if (window.matchMedia(DESKTOP_QUERY).matches) setCollapsed((c) => !c)
    else setMenuOpen((o) => !o)
  }

  const closeMenu = () => setMenuOpen(false)

  const shellClass = [
    'app-shell',
    collapsed && 'is-collapsed',
    menuOpen && 'is-menu-open',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={shellClass}>
      <Sidebar onNavigate={closeMenu} />
      {menuOpen && <div className="app-backdrop" onClick={closeMenu} />}

      <div className="app-main">
        <Topbar onToggleMenu={toggleMenu} />
        <main className="app-content">
          {/* La key remonta la página al cambiar de empresa: descarta los datos
              de la empresa anterior y vuelve a cargarlos con el nuevo X-Company-Id. */}
          <Outlet key={companyId ?? 'sin-empresa'} />
        </main>
      </div>
    </div>
  )
}
