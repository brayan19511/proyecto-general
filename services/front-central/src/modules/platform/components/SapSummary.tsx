import { useApi } from '../../../shared/hooks/useApi'
import StatusBadge from '../../../shared/components/StatusBadge'
import * as companiesService from '../services/companiesService'

// Celda "Compañía SAP" de una empresa: se consulta con el X-Company-Id de la fila.
// `version` cambia tras editarla para volver a pedirla.
export default function SapSummary({ companyId, version }: { companyId: string; version: number }) {
  const sap = useApi(() => companiesService.getSapCompany(companyId), [companyId, version])

  if (sap.loading && sap.data === undefined) return <span className="spinner-border spinner-border-sm" aria-label="Cargando" />
  if (sap.error) return <span className="small text-danger-emphasis" title={sap.error}>No disponible</span>
  if (!sap.data) return <StatusBadge tone="warning" label="Sin configurar" />
  return (
    <div className="small">
      <div className="font-monospace">{sap.data.sap_schema}</div>
      <div className="text-body-secondary font-monospace">{sap.data.source_view}</div>
    </div>
  )
}
