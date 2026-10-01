import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import EmptyState from '../../../shared/components/EmptyState'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import AreaFormModal from '../components/AreaFormModal'
import PositionFormModal, { type PositionAction } from '../components/PositionFormModal'
import PositionRolesModal from '../components/PositionRolesModal'
import * as orgService from '../services/orgService'
import type { Area, Position } from '../types'

// Baja o restauración que pide confirmación.
type Pending =
  | { kind: 'delete-area' | 'restore-area'; area: Area }
  | { kind: 'delete-position' | 'restore-position'; position: Position }

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, 'es')

function confirmText(p: Pending) {
  switch (p.kind) {
    case 'delete-area':
      return { title: 'Dar de baja el área', label: 'Dar de baja', danger: true, done: 'Área dada de baja',
        message: `${p.area.name} deja de estar disponible. Solo se puede si no tiene puestos activos. Se puede restaurar.` }
    case 'restore-area':
      return { title: 'Restaurar área', label: 'Restaurar', danger: false, done: 'Área restaurada',
        message: `${p.area.name} vuelve a estar activa. Sus puestos dados de baja se restauran por separado.` }
    case 'delete-position':
      return { title: 'Dar de baja el puesto', label: 'Dar de baja', danger: true, done: 'Puesto dado de baja',
        message: `${p.position.name} deja de estar disponible. Solo se puede si nadie lo tiene asignado. Se puede restaurar.` }
    case 'restore-position':
      return { title: 'Restaurar puesto', label: 'Restaurar', danger: false, done: 'Puesto restaurado',
        message: `${p.position.name} vuelve a estar activo, con sus roles. Su área debe estar activa.` }
  }
}

// Empresa › Áreas y puestos (fase 1: solo platform admin). Un puesto pertenece a
// un área y tiene roles; las personas reciben permisos al tener el puesto.
export default function AreasPage() {
  const [includeDeleted, setIncludeDeleted] = useState(false)
  const areas = useApi(() => orgService.listAreas(includeDeleted), [includeDeleted])
  const positions = useApi(() => orgService.listPositions(includeDeleted), [includeDeleted])
  const roles = useApi(orgService.listRoles)
  const [areaForm, setAreaForm] = useState<{ area: Area | null } | null>(null)
  const [positionForm, setPositionForm] = useState<PositionAction | null>(null)
  const [rolesOf, setRolesOf] = useState<Position | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = () => {
    areas.reload()
    positions.reload()
  }

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'delete-area') await orgService.deleteArea(pending.area.id)
      else if (pending.kind === 'restore-area') await orgService.restoreArea(pending.area.id)
      else if (pending.kind === 'delete-position') await orgService.deletePosition(pending.position.id)
      else if (pending.kind === 'restore-position') await orgService.restorePosition(pending.position.id)
      toast.success(confirmText(pending).done)
      reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 tiene puestos / personas / área de baja
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const sortedAreas = [...(areas.data ?? [])].sort(byName)
  const positionsOf = (areaId: string) => (positions.data ?? []).filter((p) => p.area.id === areaId).sort(byName)
  const activeAreas = sortedAreas.filter((a) => a.is_active)
  const deletedLabel = (active: boolean) => !active && <span className="ms-2"><StatusBadge tone="secondary" label="De baja" /></span>
  const pendingText = pending && confirmText(pending)

  return (
    <>
      <PageHeader
        title="Áreas y puestos"
        description="Cada puesto pertenece a un área y tiene roles. Las personas heredan los permisos de sus puestos."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setAreaForm({ area: null })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva área
          </button>
        }
      />

      <div className="form-check form-switch mb-3">
        <input id="org-deleted" type="checkbox" className="form-check-input" checked={includeDeleted}
          onChange={(e) => setIncludeDeleted(e.target.checked)} />
        <label htmlFor="org-deleted" className="form-check-label">Ver dados de baja (para restaurarlos)</label>
      </div>

      <AsyncState loading={areas.loading || positions.loading} error={areas.error ?? positions.error} onRetry={reload}
        hasData={areas.data !== undefined && positions.data !== undefined}>
        {sortedAreas.length === 0 ? (
          <EmptyState icon="diagram-3" title="Aún no hay áreas" description="Crea un área y luego sus puestos." />
        ) : (
          <div className="d-flex flex-column gap-3">
            {sortedAreas.map((area) => (
              <div key={area.id} className={`card ${area.is_active ? '' : 'opacity-75'}`}>
                <div className="card-header bg-transparent d-flex flex-wrap align-items-center gap-2">
                  <div className="me-auto">
                    <span className="fw-semibold">{area.name}</span>
                    <span className="small text-body-secondary font-monospace ms-2">{area.code}</span>
                    {deletedLabel(area.is_active)}
                  </div>
                  {area.is_active ? (
                    <>
                      <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setPositionForm({ kind: 'create', area })}>
                        <i className="bi bi-plus-lg me-1" aria-hidden="true" />
                        Puesto
                      </button>
                      <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setAreaForm({ area })}
                        aria-label={`Renombrar ${area.name}`} title="Renombrar">
                        <i className="bi bi-pencil" aria-hidden="true" />
                      </button>
                      <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'delete-area', area })}
                        aria-label={`Dar de baja ${area.name}`} title="Dar de baja">
                        <i className="bi bi-archive" aria-hidden="true" />
                      </button>
                    </>
                  ) : (
                    <button type="button" className="btn btn-sm btn-outline-success" onClick={() => setPending({ kind: 'restore-area', area })}>
                      Restaurar
                    </button>
                  )}
                </div>
                <ul className="list-group list-group-flush">
                  {positionsOf(area.id).length === 0 && (
                    <li className="list-group-item small text-body-secondary">Sin puestos.</li>
                  )}
                  {positionsOf(area.id).map((p) => (
                    <li key={p.id} className="list-group-item d-flex flex-wrap align-items-center gap-2">
                      <div className="me-auto">
                        {p.name}
                        <span className="small text-body-secondary font-monospace ms-2">{p.code}</span>
                        {deletedLabel(p.is_active)}
                      </div>
                      {p.is_active ? (
                        <>
                          <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setRolesOf(p)}>
                            <i className="bi bi-shield-lock me-1" aria-hidden="true" />
                            Roles
                          </button>
                          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setPositionForm({ kind: 'edit', position: p })}
                            aria-label={`Editar ${p.name}`} title="Editar">
                            <i className="bi bi-pencil" aria-hidden="true" />
                          </button>
                          <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'delete-position', position: p })}
                            aria-label={`Dar de baja ${p.name}`} title="Dar de baja">
                            <i className="bi bi-archive" aria-hidden="true" />
                          </button>
                        </>
                      ) : (
                        <button type="button" className="btn btn-sm btn-outline-success" onClick={() => setPending({ kind: 'restore-position', position: p })}>
                          Restaurar
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </AsyncState>

      {areaForm && <AreaFormModal area={areaForm.area} onClose={() => setAreaForm(null)} onSaved={reload} />}
      {positionForm && (
        <PositionFormModal action={positionForm} areas={activeAreas} onClose={() => setPositionForm(null)} onSaved={reload} />
      )}
      {rolesOf && (
        <PositionRolesModal position={rolesOf} roles={(roles.data ?? []).filter((r) => r.is_active)} onClose={() => setRolesOf(null)} />
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pendingText?.title ?? ''}
        message={pendingText?.message ?? ''}
        confirmLabel={pendingText?.label ?? ''}
        danger={pendingText?.danger ?? false}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
