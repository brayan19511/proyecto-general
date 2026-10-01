import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  description?: string
  actions?: ReactNode // botones a la derecha; como máximo uno principal
}

export default function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="d-flex flex-wrap align-items-start justify-content-between gap-2 mb-4">
      <div>
        <h1 className="h4 mb-1">{title}</h1>
        {description && <p className="text-body-secondary mb-0">{description}</p>}
      </div>
      {actions && <div className="d-flex gap-2">{actions}</div>}
    </div>
  )
}
