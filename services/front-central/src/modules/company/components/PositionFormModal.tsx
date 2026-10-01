import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { CODE_PATTERN, toCode } from '../codes'
import * as orgService from '../services/orgService'
import type { Area, Position } from '../types'

// Crear un puesto en un área, o editar nombre y área de uno existente.
export type PositionAction = { kind: 'create'; area: Area } | { kind: 'edit'; position: Position }

type PositionFormModalProps = {
  action: PositionAction
  areas: Area[] // activas, para mover de área
  onClose: () => void
  onSaved: () => void
}

export default function PositionFormModal({ action, areas, onClose, onSaved }: PositionFormModalProps) {
  const editing = action.kind === 'edit' ? action.position : null
  const [code, setCode] = useState('')
  const [name, setName] = useState(editing?.name ?? '')
  const [areaId, setAreaId] = useState(editing?.area.id ?? (action.kind === 'create' ? action.area.id : ''))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const validCode = editing !== null || CODE_PATTERN.test(code)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      if (editing) {
        // Solo lo que cambió (auth exige al menos un campo).
        const changes: { name?: string; area_id?: string } = {}
        if (name.trim() !== editing.name) changes.name = name.trim()
        if (areaId !== editing.area.id) changes.area_id = areaId
        if (Object.keys(changes).length > 0) await orgService.updatePosition(editing.id, changes)
      } else {
        await orgService.createPosition(code, name.trim(), areaId)
      }
      toast.success(editing ? 'Puesto actualizado' : 'Puesto creado. Asígnale roles para darle permisos.')
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 código repetido, 403 mover de área sin alcance de empresa
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal
      open
      title={editing ? `Editar puesto ${editing.code}` : `Nuevo puesto en ${action.kind === 'create' ? action.area.name : ''}`}
      submitLabel="Guardar"
      busy={busy}
      error={error}
      canSubmit={validCode && name.trim() !== '' && areaId !== ''}
      onSubmit={submit}
      onClose={onClose}
    >
      {!editing && (
        <div className="mb-3">
          <label htmlFor="pos-code" className="form-label">Código</label>
          <input id="pos-code" className={`form-control font-monospace ${code && !validCode ? 'is-invalid' : ''}`}
            maxLength={50} placeholder="JEFE_VENTAS" autoFocus value={code} onChange={(e) => setCode(toCode(e.target.value))}
            aria-describedby="pos-code-help" />
          <div id="pos-code-help" className="form-text">Mayúsculas, números y _. Único en la empresa; no se cambia después.</div>
        </div>
      )}
      <div className="mb-3">
        <label htmlFor="pos-name" className="form-label">Nombre</label>
        <input id="pos-name" className="form-control" maxLength={150} placeholder="Jefe de ventas" value={name}
          onChange={(e) => setName(e.target.value)} />
      </div>
      {editing && (
        <>
          <label htmlFor="pos-area" className="form-label">Área</label>
          <select id="pos-area" className="form-select" value={areaId} onChange={(e) => setAreaId(e.target.value)}>
            {areas.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.code})</option>)}
          </select>
          <div className="form-text">
            Mover de área cambia el alcance de los permisos "por área" de quienes tienen el puesto.
          </div>
        </>
      )}
    </FormModal>
  )
}
