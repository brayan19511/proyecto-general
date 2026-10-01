import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as rulesService from '../services/rulesService'
import type { Category } from '../types'

// Crear una categoría, una subcategoría (con parent) o renombrar (con category).
export type CategoryAction =
  | { kind: 'create'; parent: Category | null }
  | { kind: 'rename'; category: Category }

type CategoryFormModalProps = {
  action: CategoryAction
  // Al crear: si se pasan, el usuario elige el nivel (principal o subcategoría de una de ellas).
  parentChoices?: Category[]
  onClose: () => void
  onSaved: (category: Category) => void
}

export default function CategoryFormModal({ action, parentChoices, onClose, onSaved }: CategoryFormModalProps) {
  const [name, setName] = useState(action.kind === 'rename' ? action.category.name : '')
  const [parentId, setParentId] = useState(action.kind === 'create' ? (action.parent?.id ?? '') : '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const title =
    action.kind === 'rename'
      ? 'Renombrar'
      : action.parent
        ? `Nueva subcategoría de ${action.parent.name}`
        : 'Nueva categoría'

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const saved =
        action.kind === 'rename'
          ? await rulesService.renameCategory(action.category.id, name.trim())
          : await rulesService.createCategory(name.trim(), parentId || null)
      toast.success(action.kind === 'rename' ? 'Nombre actualizado' : 'Categoría creada')
      onSaved(saved)
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 nombre repetido
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal
      open
      title={title}
      submitLabel="Guardar"
      busy={busy}
      error={error}
      canSubmit={name.trim() !== ''}
      onSubmit={submit}
      onClose={onClose}
    >
      {action.kind === 'create' && parentChoices && (
        <div className="mb-3">
          <label htmlFor="category-parent" className="form-label">Nivel</label>
          <select id="category-parent" className="form-select" value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">Categoría principal (código)</option>
            {parentChoices.map((p) => <option key={p.id} value={p.id}>Subcategoría de {p.name}</option>)}
          </select>
        </div>
      )}
      <label htmlFor="category-name" className="form-label">Nombre</label>
      <input
        id="category-name"
        className="form-control"
        maxLength={150}
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        aria-describedby="category-name-help"
      />
      <div id="category-name-help" className="form-text">
        Es el nombre que se ve en los reportes ({parentId ? 'subcódigo' : 'código'}).
        Renombrar no obliga a reclasificar.
      </div>
    </FormModal>
  )
}
