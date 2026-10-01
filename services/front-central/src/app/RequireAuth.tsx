import { Navigate, Outlet, useLocation } from 'react-router'
import { useSessionStore } from '../shared/auth/sessionStore'
import FullPageSpinner from '../shared/components/FullPageSpinner'

// Guard de las rutas privadas. Solo decide qué mostrar: la autorización real
// la hace el backend en cada solicitud.
export default function RequireAuth() {
  const status = useSessionStore((s) => s.status)
  const location = useLocation()

  if (status === 'loading') return <FullPageSpinner />
  if (status === 'anonymous') {
    // Guarda a dónde iba para volver ahí después del login.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
