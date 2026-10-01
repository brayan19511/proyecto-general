import { useState } from 'react'
import { LEDGER_UPDATE, useCanAccess } from '../../../shared/auth/access'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import EmptyState from '../../../shared/components/EmptyState'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { categoryTree } from '../categories'
import * as rulesService from '../services/rulesService'
import type { Category } from '../types'
import CategoryFormModal, { type CategoryAction } from './CategoryFormModal'

// Categorías (código) y subcategorías (subcódigo). Dos niveles.
export default function CategoriesTab() {
  const canEdit = useCanAccess()({ anyOf: LEDGER_UPDATE })
  const [includeInactive, setIncludeInactive] = useState(false)
  const query = useApi(() => rulesService.listCategories(includeInactive), [includeInactive])
  const [action, setAction] = useState<CategoryAction | null>(null)
  const [toDeactivate, setToDeactivate] = useState<Category | null>(null)
  const [busy, setBusy] = useState(false)

  const tree = categoryTree(query.data ?? [])

  const deactivate = async () => {
    if (!toDeactivate) return
    setBusy(true)
    try {
      await rulesService.deactivateCategory(toDeactivate.id)
      toast.success('Categoría dada de baja')
      query.reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409: tiene subcategorías o reglas activas
    } finally {
      setBusy(false)
      setToDeactivate(null)
    }
  }

  const actions = (category: Category, isParent: boolean) =>
    canEdit && category.is_active && (
      <div className="d-flex gap-1">
        {isParent && (
          <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setAction({ kind: 'create', parent: category })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Subcategoría
          </button>
        )}
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setAction({ kind: 'rename', category })}
          aria-label={`Renombrar ${category.name}`} title="Renombrar">
          <i className="bi bi-pencil" aria-hidden="true" />
        </button>
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setToDeactivate(category)}
          aria-label={`Dar de baja ${category.name}`} title="Dar de baja">
          <i className="bi bi-archive" aria-hidden="true" />
        </button>
      </div>
    )

  const label = (category: Category) => (
    <span className={category.is_active ? undefined : 'text-body-secondary text-decoration-line-through'}>
      {category.name}
      {!category.is_active && <span className="ms-2"><StatusBadge tone="secondary" label="De baja" /></span>}
    </span>
  )

  return (
    <>
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
        <div className="form-check form-switch mb-0">
          <input id="cat-inactive" type="checkbox" className="form-check-input" checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)} />
          <label htmlFor="cat-inactive" className="form-check-label">Ver dadas de baja</label>
        </div>
        {canEdit && (
          <button type="button" className="btn btn-primary" onClick={() => setAction({ kind: 'create', parent: null })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva categoría
          </button>
        )}
      </div>

      <AsyncState loading={query.loading} error={query.error} onRetry={query.reload} hasData={query.data !== undefined}>
        {tree.length === 0 ? (
          <EmptyState icon="tags" title="Aún no hay categorías" description="Crea una categoría y luego sus subcategorías." />
        ) : (
          <div className="list-group">
            {tree.map(({ parent, children }) => (
              <div key={parent.id} className="list-group-item">
                <div className="d-flex align-items-center justify-content-between gap-2">
                  <span className="fw-semibold">{label(parent)}</span>
                  {actions(parent, true)}
                </div>
                {children.length > 0 && (
                  <ul className="list-unstyled mb-0 mt-2 ms-4">
                    {children.map((child) => (
                      <li key={child.id} className="d-flex align-items-center justify-content-between gap-2 py-1 border-top">
                        {label(child)}
                        {actions(child, false)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </AsyncState>

      {action && <CategoryFormModal action={action} onClose={() => setAction(null)} onSaved={() => query.reload()} />}

      <ConfirmDialog
        open={toDeactivate !== null}
        title="Dar de baja"
        message={`"${toDeactivate?.name ?? ''}" dejará de estar disponible para nuevas reglas. Solo se puede si no tiene subcategorías ni reglas activas. No se borra: queda en el historial.`}
        confirmLabel="Dar de baja"
        danger
        busy={busy}
        onConfirm={deactivate}
        onCancel={() => setToDeactivate(null)}
      />
    </>
  )
}
