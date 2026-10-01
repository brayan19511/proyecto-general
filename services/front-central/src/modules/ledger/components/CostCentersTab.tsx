import { useState } from 'react'
import { LEDGER_ADMIN, useCanAccess } from '../../../shared/auth/access'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDate } from '../../../shared/utils/format'
import * as orgService from '../../company/services/orgService'
import * as costCentersService from '../services/costCentersService'
import type { CostCenter } from '../types'
import MappingFormModal from './MappingFormModal'

const numberFormat = new Intl.NumberFormat('es-PE')

// Centros de costo que aparecen en las líneas sincronizadas y a qué área
// resuelven hoy. Sirve para encontrar los que faltan homologar.
export default function CostCentersTab() {
  const canAccess = useCanAccess()
  const canEdit = canAccess({ anyOf: LEDGER_ADMIN })
  const canCreateArea = canAccess({ anyOf: ['areas.manage'] })
  const [onlyUnmapped, setOnlyUnmapped] = useState(false)
  const [search, setSearch] = useState('')
  const centers = useApi(() => costCentersService.listCostCenters(onlyUnmapped), [onlyUnmapped])
  const areas = useApi(() => orgService.listAreas())
  const [creatingFor, setCreatingFor] = useState<string | null>(null) // '' = sin código sugerido

  const term = search.trim().toLowerCase()
  const rows = (centers.data ?? []).filter(
    (c) => !term || `${c.cost_center_code ?? ''} ${c.sap_name ?? ''} ${c.area_name ?? ''}`.toLowerCase().includes(term),
  )
  const activeAreas = (areas.data ?? []).filter((a) => a.is_active)

  const columns: Column<CostCenter>[] = [
    {
      header: 'Centro de costo',
      render: (c) =>
        c.cost_center_code ? (
          <>
            <div className="font-monospace">{c.cost_center_code}</div>
            {c.sap_name && <div className="small text-body-secondary">{c.sap_name}</div>}
          </>
        ) : (
          <span className="fst-italic text-warning-emphasis">Sin centro de costo</span>
        ),
    },
    { header: 'Líneas', className: 'text-end', render: (c) => numberFormat.format(c.lines) },
    { header: 'Última fecha', className: 'text-nowrap', render: (c) => (c.last_posting_date ? formatDate(c.last_posting_date) : '—') },
    {
      header: 'Área',
      render: (c) =>
        c.area_name ? (
          <>
            <div>{c.area_name}</div>
            <div className="small text-body-secondary">
              {c.match_mode === 'prefix' ? `Por prefijo ${c.mapping_code}` : 'Código exacto'}
            </div>
          </>
        ) : (
          <StatusBadge tone="warning" label="Sin homologar" />
        ),
    },
    {
      header: 'Acciones',
      className: 'text-end',
      render: (c) =>
        canEdit && !c.area_id && c.cost_center_code && (
          <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setCreatingFor(c.cost_center_code)}>
            Homologar
          </button>
        ),
    },
  ]

  return (
    <>
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 280 }} placeholder="Buscar centro, nombre o área…"
          aria-label="Buscar centros de costo" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="form-check form-switch mb-0">
          <input id="cc-unmapped" type="checkbox" className="form-check-input" checked={onlyUnmapped}
            onChange={(e) => setOnlyUnmapped(e.target.checked)} />
          <label htmlFor="cc-unmapped" className="form-check-label">Solo sin homologar</label>
        </div>
        {canEdit && (
          <button type="button" className="btn btn-primary ms-auto" onClick={() => setCreatingFor('')}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva homologación
          </button>
        )}
      </div>
      <p className="small text-body-secondary">
        Las líneas sin homologar (o sin centro) solo las ve quien tiene alcance de toda la empresa.
      </p>

      <AsyncState loading={centers.loading} error={centers.error} onRetry={centers.reload} hasData={centers.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(c) => c.cost_center_code ?? '∅'}
          emptyMessage={onlyUnmapped ? 'Todos los centros están homologados.' : 'Aún no hay líneas sincronizadas.'} />
      </AsyncState>

      {creatingFor !== null && (
        <MappingFormModal
          action={{ kind: 'create', code: creatingFor }}
          areas={activeAreas}
          canCreateArea={canCreateArea}
          onAreasChanged={areas.reload}
          onClose={() => setCreatingFor(null)}
          onSaved={centers.reload}
        />
      )}
    </>
  )
}
