import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { useCanAccess, type AccessRule } from '../shared/auth/access'
import EmptyState from '../shared/components/EmptyState'

type RequireAccessProps = {
  rule: AccessRule
  children: ReactNode
}

// Guard por ruta: evita entrar escribiendo la URL a un módulo oculto en el menú.
export default function RequireAccess({ rule, children }: RequireAccessProps) {
  const canAccess = useCanAccess()
  if (canAccess(rule)) return children

  return (
    <EmptyState
      icon="lock"
      title="No tienes acceso a esta sección"
      description="Si lo necesitas, pide a un administrador que te asigne el permiso en esta empresa."
      action={
        <Link to="/perfil" className="btn btn-outline-primary btn-sm">
          Ir a mi perfil
        </Link>
      }
    />
  )
}
