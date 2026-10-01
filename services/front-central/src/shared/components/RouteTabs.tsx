import { NavLink } from 'react-router'

type RouteTab = { label: string; to: string; icon?: string }

// Pestañas que son rutas: se pueden enlazar y funcionan con atrás/adelante.
export default function RouteTabs({ tabs }: { tabs: RouteTab[] }) {
  return (
    <nav className="nav nav-underline flex-nowrap overflow-x-auto mb-4 border-bottom">
      {tabs.map((tab) => (
        // end: la pestaña de la ruta padre no queda activa en las demás.
        <NavLink key={tab.to} to={tab.to} end className="nav-link text-nowrap">
          {tab.icon && <i className={`bi bi-${tab.icon} me-2`} aria-hidden="true" />}
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
