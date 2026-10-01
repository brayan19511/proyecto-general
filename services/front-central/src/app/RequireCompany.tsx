import type { ReactNode } from 'react'
import { useSessionStore } from '../shared/auth/sessionStore'
import EmptyState from '../shared/components/EmptyState'

// Para módulos que trabajan sobre la empresa activa (X-Company-Id).
export default function RequireCompany({ children }: { children: ReactNode }) {
  const companyId = useSessionStore((s) => s.companyId)
  if (companyId) return children

  return (
    <EmptyState
      icon="buildings"
      title="No hay una empresa activa"
      description="Este módulo trabaja sobre una empresa. Pide que te agreguen a una o, si eres administrador, crea una."
    />
  )
}
