import type { ReactNode } from 'react'

type AsyncStateProps = {
  loading: boolean
  error?: string
  onRetry?: () => void
  hasData: boolean // si ya hay datos, se muestran aunque esté recargando
  children: ReactNode
}

// Estado de carga y error común a las pantallas que piden datos con useApi.
export default function AsyncState({ loading, error, onRetry, hasData, children }: AsyncStateProps) {
  if (error) {
    return (
      <div className="alert alert-danger d-flex align-items-center justify-content-between gap-2" role="alert">
        <span>{error}</span>
        {onRetry && (
          <button type="button" className="btn btn-sm btn-outline-danger" onClick={onRetry}>
            Reintentar
          </button>
        )}
      </div>
    )
  }

  if (loading && !hasData) {
    return (
      <div className="d-flex align-items-center gap-2 text-body-secondary py-4">
        <span className="spinner-border spinner-border-sm" aria-hidden="true" />
        Cargando…
      </div>
    )
  }

  return children
}
