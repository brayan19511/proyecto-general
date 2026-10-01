import { useSessionStore } from '../../../shared/auth/sessionStore'
import EmptyState from '../../../shared/components/EmptyState'

// Empresas, puestos, áreas y roles del usuario. Sale de /auth/me (ya cargado
// en la sesión); no muestra códigos de permiso (acuerdo, fase 1).
export default function CompaniesTab() {
  const me = useSessionStore((s) => s.me)
  const activeCompanyId = useSessionStore((s) => s.companyId)
  if (!me) return null

  return (
    <>
      {me.is_platform_admin && (
        <div className="alert alert-primary d-flex align-items-center gap-2" role="status">
          <i className="bi bi-shield-check" aria-hidden="true" />
          Eres administrador de la plataforma: tienes acceso a todas las empresas y módulos.
        </div>
      )}

      {me.memberships.length === 0 ? (
        <EmptyState
          icon="buildings"
          title="Aún no perteneces a ninguna empresa"
          description="Un administrador debe agregarte a una empresa y asignarte un puesto."
        />
      ) : (
        <div className="row g-3">
          {me.memberships.map(({ company, positions }) => (
            <div key={company.id} className="col-md-6 col-xl-4">
              <div className="card h-100">
                <div className="card-header d-flex align-items-center justify-content-between bg-transparent">
                  <span className="fw-semibold">{company.name}</span>
                  {company.id === activeCompanyId && (
                    <span className="badge text-bg-primary">Activa</span>
                  )}
                </div>
                <ul className="list-group list-group-flush">
                  {positions.length === 0 && (
                    <li className="list-group-item text-body-secondary">Sin puestos asignados</li>
                  )}
                  {positions.map((position) => (
                    <li key={position.id} className="list-group-item">
                      <div>{position.name}</div>
                      <div className="small text-body-secondary mb-2">Área: {position.area.name}</div>
                      <div className="d-flex flex-wrap gap-1">
                        {position.roles.length === 0 && <span className="small text-body-secondary">Sin roles</span>}
                        {position.roles.map((role) => (
                          <span key={role} className="badge bg-primary-subtle text-primary-emphasis">{role}</span>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
