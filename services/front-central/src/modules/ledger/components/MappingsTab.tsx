import { useState } from 'react'
import { LEDGER_ADMIN, useCanAccess } from '../../../shared/auth/access'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as orgService from '../../company/services/orgService'
import * as costCentersService from '../services/costCentersService'
import type { CostCenterMapping } from '../types'
import MappingFormModal, { type MappingAction } from './MappingFormModal'

// Homologaciones registradas: centro de costo (exacto o prefijo) → área de auth.
export default function MappingsTab() {
  const canAccess = useCanAccess()
  const canEdit = canAccess({ anyOf: LEDGER_ADMIN })
  const canCreateArea = canAccess({ anyOf: ['areas.manage'] })
  const [includeInactive, setIncludeInactive] = useState(false)
  const mappings = useApi(() => costCentersService.listMappings(includeInactive), [includeInactive])
  const areas = useApi(() => orgService.listAreas())
  const [action, setAction] = useState<MappingAction | null>(null)
  const [toDeactivate, setToDeactivate] = useState<CostCenterMapping | null>(null)
  const [busy, setBusy] = useState(false)

  const deactivate = async () => {
    if (!toDeactivate) return
    setBusy(true)
    try {
      await costCentersService.deactivateMapping(toDeactivate.id)
      toast.success('Homologación dada de baja')
      mappings.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setToDeactivate(null)
    }
  }

  const columns: Column<CostCenterMapping>[] = [
    { header: 'Centro de costo', render: (m) => <span className="font-monospace">{m.cost_center_code}</span> },
    { header: 'Coincidencia', render: (m) => (m.match_mode === 'prefix' ? 'Empieza con' : 'Código exacto') },
    { header: 'Área', render: (m) => `${m.area_name} (${m.area_code})` },
    {
      header: 'Estado',
      render: (m) => <StatusBadge tone={m.is_active ? 'success' : 'secondary'} label={m.is_active ? 'Activa' : 'De baja'} />,
    },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (m) =>
        canEdit && m.is_active && (
          <>
            <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setAction({ kind: 'change', mapping: m })}
              aria-label={`Cambiar área de ${m.cost_center_code}`} title="Cambiar área">
              <i className="bi bi-pencil" aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setToDeactivate(m)}
              aria-label={`Dar de baja ${m.cost_center_code}`} title="Dar de baja">
              <i className="bi bi-archive" aria-hidden="true" />
            </button>
          </>
        ),
    },
  ]

  return (
    <>
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <div className="form-check form-switch mb-0">
          <input id="map-inactive" type="checkbox" className="form-check-input" checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)} />
          <label htmlFor="map-inactive" className="form-check-label">Ver dadas de baja</label>
        </div>
        {canEdit && (
          <button type="button" className="btn btn-primary ms-auto" onClick={() => setAction({ kind: 'create' })}
            disabled={!areas.data?.some((a) => a.is_active)}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva homologación
          </button>
        )}
      </div>

      <AsyncState loading={mappings.loading} error={mappings.error} onRetry={mappings.reload} hasData={mappings.data !== undefined}>
        <DataTable columns={columns} rows={mappings.data ?? []} rowKey={(m) => m.id} emptyMessage="Aún no hay homologaciones." />
      </AsyncState>

      {action && (
        <MappingFormModal
          action={action}
          areas={(areas.data ?? []).filter((a) => a.is_active)}
          canCreateArea={canCreateArea}
          onAreasChanged={areas.reload}
          onClose={() => setAction(null)}
          onSaved={mappings.reload}
        />
      )}

      <ConfirmDialog
        open={toDeactivate !== null}
        title="Dar de baja la homologación"
        message={`Las líneas del centro ${toDeactivate?.cost_center_code ?? ''} dejarán de asociarse a ${toDeactivate?.area_name ?? ''} desde la próxima consulta (o pasarán a otra homologación que aplique). No se borra: queda en el historial.`}
        confirmLabel="Dar de baja"
        danger
        busy={busy}
        onConfirm={deactivate}
        onCancel={() => setToDeactivate(null)}
      />
    </>
  )
}
