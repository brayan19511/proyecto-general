import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import AreaFormModal from '../../company/components/AreaFormModal'
import type { Area } from '../../company/types'
import * as costCentersService from '../services/costCentersService'
import type { CostCenterMapping } from '../types'

// Crear (con código sugerido opcional) o cambiar el área de una homologación.
export type MappingAction = { kind: 'create'; code?: string } | { kind: 'change'; mapping: CostCenterMapping }

type MappingFormModalProps = {
  action: MappingAction
  areas: Area[] // activas
  canCreateArea: boolean // areas.manage (o platform admin)
  onAreasChanged: () => void // recargar áreas tras crear una
  onClose: () => void
  onSaved: () => void
}

export default function MappingFormModal({ action, areas, canCreateArea, onAreasChanged, onClose, onSaved }: MappingFormModalProps) {
  const [creatingArea, setCreatingArea] = useState(false)
  const editing = action.kind === 'change' ? action.mapping : null
  const [code, setCode] = useState(editing?.cost_center_code ?? (action.kind === 'create' ? action.code ?? '' : ''))
  const [mode, setMode] = useState<'exact' | 'prefix'>(editing?.match_mode ?? 'exact')
  const [areaId, setAreaId] = useState(editing?.auth_area_id ?? areas[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      if (editing) await costCentersService.changeMappingArea(editing.id, areaId)
      else await costCentersService.createMapping(code.trim(), mode, areaId)
      toast.success('Homologación guardada. Se aplica desde la próxima consulta.')
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 ya existe una activa para ese código y modo
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <FormModal
        open
        title={editing ? `Cambiar área de ${editing.cost_center_code}` : 'Nueva homologación'}
        submitLabel="Guardar"
        busy={busy}
        error={error}
        canSubmit={areaId !== '' && (editing !== null || code.trim() !== '')}
        onSubmit={submit}
        onClose={onClose}
      >
        <p className="small text-body-secondary">
          Indica a qué área de la empresa pertenece un centro de costo de SAP. Define qué líneas ve un usuario con
          alcance de área. Un centro resuelve a una sola área: el código exacto gana sobre el prefijo más largo.
        </p>

        {!editing && (
          <div className="row g-3 mb-3">
            <div className="col-sm-7">
              <label htmlFor="map-code" className="form-label">Centro de costo</label>
              <input id="map-code" className="form-control font-monospace" maxLength={100} placeholder="V1141177"
                value={code} onChange={(e) => setCode(e.target.value)} />
            </div>
            <div className="col-sm-5">
              <label htmlFor="map-mode" className="form-label">Coincidencia</label>
              <select id="map-mode" className="form-select" value={mode} onChange={(e) => setMode(e.target.value as 'exact' | 'prefix')}>
                <option value="exact">Código exacto</option>
                <option value="prefix">Empieza con (prefijo)</option>
              </select>
            </div>
            {mode === 'prefix' && code.trim() && (
              <div className="col-12 form-text mt-1">Aplica a todo centro que empiece con "{code.trim()}".</div>
            )}
          </div>
        )}

        <div className="d-flex align-items-center justify-content-between">
          <label htmlFor="map-area" className="form-label">Área</label>
          {canCreateArea && (
            <button type="button" className="btn btn-sm btn-link p-0 mb-2" onClick={() => setCreatingArea(true)}>
              <i className="bi bi-plus-lg me-1" aria-hidden="true" />
              Nueva
            </button>
          )}
        </div>
        <select id="map-area" className="form-select" value={areaId} onChange={(e) => setAreaId(e.target.value)}>
          {areas.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.code})</option>)}
        </select>
        {editing && <div className="form-text">El código y el modo no se editan: para cambiarlos, da de baja y crea otra.</div>}
      </FormModal>

      {/* Fuera del <form> de la homologación: un formulario no puede ir dentro de otro. */}
      {creatingArea && (
        <AreaFormModal
          area={null}
          onClose={() => setCreatingArea(false)}
          onSaved={(created) => {
            onAreasChanged()
            setAreaId(created.id) // la nueva queda elegida
          }}
        />
      )}
    </>
  )
}
