import AsyncState from '../../../shared/components/AsyncState'
import Dialog from '../../../shared/components/Dialog'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDate } from '../../../shared/utils/format'
import * as usersService from '../services/usersService'

// Todo sobre un usuario: cuenta, datos personales, empresas con puestos y roles,
// y cuántas sesiones tiene abiertas. Solo lectura.
export default function UserDetailModal({ userId, onClose }: { userId: string; onClose: () => void }) {
  const user = useApi(() => usersService.getUser(userId), [userId])
  const u = user.data
  const fullName = u?.profile ? [u.profile.first_names, u.profile.last_names].filter(Boolean).join(' ') : ''

  return (
    <Dialog open wide onClose={onClose} labelledBy="user-title">
      <div className="card-header bg-transparent d-flex align-items-center">
        <h2 id="user-title" className="h5 mb-0 me-auto">{u?.email ?? 'Usuario'}</h2>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} />
      </div>
      <div className="card-body">
        <AsyncState loading={user.loading} error={user.error} onRetry={user.reload} hasData={u !== undefined}>
          {u && (
            <>
              <div className="d-flex flex-wrap gap-2 mb-3">
                <StatusBadge tone={u.is_active ? 'success' : 'secondary'} label={u.is_active ? 'Cuenta activa' : 'Cuenta inhabilitada'} />
                {u.is_platform_admin && <StatusBadge tone="info" label="Admin de plataforma" />}
                <StatusBadge tone="secondary" label={`${u.active_sessions} sesiones abiertas`} />
              </div>
              <dl className="row small mb-4">
                <dt className="col-sm-3 text-body-secondary fw-normal">Nombre</dt>
                <dd className="col-sm-9">{fullName || '—'}</dd>
                <dt className="col-sm-3 text-body-secondary fw-normal">Registrado</dt>
                <dd className="col-sm-9">{formatDate(u.created_at.slice(0, 10))}</dd>
                <dt className="col-sm-3 text-body-secondary fw-normal">Máximo de sesiones</dt>
                <dd className="col-sm-9 mb-0">{u.max_sessions ?? 'El del servicio'}</dd>
              </dl>

              <h3 className="h6">Empresas</h3>
              {u.memberships.length === 0 ? (
                <p className="small text-body-secondary mb-0">No pertenece a ninguna empresa.</p>
              ) : (
                <ul className="list-group">
                  {u.memberships.map((m) => (
                    <li key={m.company.id} className="list-group-item">
                      <div className="fw-semibold">{m.company.name}</div>
                      {m.positions.length === 0 && <div className="small text-body-secondary">Sin puestos</div>}
                      {m.positions.map((p) => (
                        <div key={p.id} className="small">
                          {p.name} · {p.area.name}
                          {p.roles.length > 0 && <span className="text-body-secondary"> — roles: {p.roles.join(', ')}</span>}
                        </div>
                      ))}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </AsyncState>
      </div>
    </Dialog>
  )
}
