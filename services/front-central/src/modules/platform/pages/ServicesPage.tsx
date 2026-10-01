import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import GatewayHistory from '../components/GatewayHistory'
import ServiceToggleModal from '../components/ServiceToggleModal'
import * as gatewayService from '../services/gatewayService'
import * as usersService from '../services/usersService'
import type { GatewayService } from '../types'

const DESCRIPTION: Record<string, string> = {
  auth: 'Inicio de sesión, usuarios, empresas, roles y permisos.',
  'libro-mayor': 'Libro mayor, sincronización con SAP, reglas y consultas.',
}

// Plataforma › Servicios (solo platform admin): habilitar o deshabilitar en
// caliente los servicios que publica la central.
export default function ServicesPage() {
  const services = useApi(gatewayService.listServices)
  const emails = useApi(usersService.emailsById)
  const [toggling, setToggling] = useState<GatewayService | null>(null)
  const [version, setVersion] = useState(0)
  const emailOf = (id: string | null) => (id ? emails.data?.get(id) ?? id.slice(0, 8) : '—')

  return (
    <>
      <PageHeader
        title="Servicios"
        description="Servicios que publica la central. Deshabilitar uno hace que la central responda 503 a sus rutas, sin apagarlo."
        actions={
          <button type="button" className="btn btn-outline-secondary" onClick={services.reload}>
            <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
            Actualizar
          </button>
        }
      />

      <AsyncState loading={services.loading} error={services.error} onRetry={services.reload} hasData={services.data !== undefined}>
        <div className="row g-3">
          {(services.data ?? []).map((s) => (
            <div key={s.service} className="col-md-6">
              <div className="card h-100">
                <div className="card-body">
                  <div className="d-flex align-items-start justify-content-between gap-2 mb-2">
                    <div>
                      <h2 className="h5 mb-1 font-monospace">{s.service}</h2>
                      <div className="small text-body-secondary">{DESCRIPTION[s.service] ?? ''}</div>
                    </div>
                    <StatusBadge tone={s.enabled ? 'success' : 'danger'} label={s.enabled ? 'Habilitado' : 'Deshabilitado'} />
                  </div>

                  <dl className="row small mb-3">
                    <dt className="col-6 text-body-secondary fw-normal">Por configuración</dt>
                    <dd className="col-6">{s.enabled_by_config ? 'Habilitado' : 'Deshabilitado'}</dd>
                    <dt className="col-6 text-body-secondary fw-normal">Cambio desde el panel</dt>
                    <dd className="col-6">{s.db_enabled === null ? 'Ninguno' : s.db_enabled ? 'Habilitado' : 'Deshabilitado'}</dd>
                    {s.updated_at && (
                      <>
                        <dt className="col-6 text-body-secondary fw-normal">Último cambio</dt>
                        <dd className="col-6">{formatDateTime(s.updated_at)} · {emailOf(s.updated_by)}</dd>
                      </>
                    )}
                    {s.reason && (
                      <>
                        <dt className="col-6 text-body-secondary fw-normal">Motivo</dt>
                        <dd className="col-6 mb-0">{s.reason}</dd>
                      </>
                    )}
                  </dl>

                  {s.panel_managed ? (
                    <button type="button" className={`btn btn-sm ${s.enabled ? 'btn-outline-danger' : 'btn-success'}`} onClick={() => setToggling(s)}>
                      {s.enabled ? 'Deshabilitar' : 'Habilitar'}
                    </button>
                  ) : (
                    <p className="small text-body-secondary mb-0">
                      <i className="bi bi-lock me-1" aria-hidden="true" />
                      Solo se cambia por configuración ({s.service.toUpperCase().replace('-', '_')}_ENABLED): sin este
                      servicio nadie podría volver a entrar al panel.
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </AsyncState>

      <GatewayHistory resourceType="service_state" version={version} emails={emails.data ?? new Map()} />

      {toggling && (
        <ServiceToggleModal
          service={toggling}
          onClose={() => setToggling(null)}
          onSaved={() => {
            services.reload()
            setVersion((v) => v + 1)
          }}
        />
      )}
    </>
  )
}
