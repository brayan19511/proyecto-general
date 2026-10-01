import type { ReactNode } from 'react'

type EmptyStateProps = {
  icon: string // clase de bootstrap-icons sin el prefijo "bi-"
  title: string
  description?: string
  action?: ReactNode
}

export default function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="text-center border rounded-3 py-5 px-3">
      <i className={`bi bi-${icon} fs-2 text-body-tertiary`} aria-hidden="true" />
      <p className="fw-semibold mt-2 mb-1">{title}</p>
      {description && <p className="text-body-secondary mb-3">{description}</p>}
      {action}
    </div>
  )
}
