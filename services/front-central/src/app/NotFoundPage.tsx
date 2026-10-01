import { Link } from 'react-router'
import EmptyState from '../shared/components/EmptyState'

export default function NotFoundPage() {
  return (
    <div className="container py-5" style={{ maxWidth: 560 }}>
      <EmptyState
        icon="signpost-split"
        title="Esta página no existe"
        description="Revisa la dirección o vuelve al inicio."
        action={
          <Link to="/" className="btn btn-primary btn-sm">
            Ir al inicio
          </Link>
        }
      />
    </div>
  )
}
