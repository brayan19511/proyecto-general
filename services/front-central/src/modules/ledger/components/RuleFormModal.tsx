import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { parseAmount } from '../../../shared/utils/decimal'
import { categoryTree } from '../categories'
import * as rulesService from '../services/rulesService'
import CategoryFormModal from './CategoryFormModal'
import type { Category, Rule, RuleConditions, RuleInput } from '../types'

type RuleFormModalProps = {
  rule: Rule | null // null = nueva
  categories: Category[] // activas (y la actual de la regla aunque esté de baja)
  canCreateCategory: boolean
  nextPriority: number
  onCategoriesChanged: () => void // recargar la lista tras crear una categoría
  onClose: () => void
  onSaved: () => void
}

// Campos de texto del formulario (vacío = sin condición).
const TEXT_FIELDS: { key: keyof RuleConditions; label: string; placeholder?: string; help?: string }[] = [
  { key: 'account_code', label: 'Cuenta', placeholder: '959005993' },
  { key: 'counter_account_code', label: 'Contracuenta' },
  { key: 'cost_center_code', label: 'Centro de costo', placeholder: 'V1141177' },
  { key: 'include_text', label: 'La glosa contiene', placeholder: 'alquiler' },
  { key: 'exclude_text', label: 'La glosa no contiene' },
  { key: 'nombre_cuenta', label: 'Nombre de cuenta', help: 'Vacío = el nombre de la cuenta SAP.' },
]
const CONDITION_KEYS: (keyof RuleConditions)[] = [
  'account_code', 'counter_account_code', 'cost_center_code', 'include_text', 'exclude_text', 'amount_min', 'amount_max',
]
const AMOUNT = /^-?\d+(\.\d{1,4})?$/ // hasta 4 decimales, como Numeric(19,4)

type Form = Record<keyof RuleConditions, string> & { priority: string; category_id: string }

function toForm(rule: Rule | null, nextPriority: number, categories: Category[]): Form {
  const text = (v: string | null | undefined) => v ?? ''
  return {
    priority: String(rule?.priority ?? nextPriority),
    category_id: rule?.category_id ?? categories[0]?.id ?? '',
    account_code: text(rule?.account_code),
    counter_account_code: text(rule?.counter_account_code),
    cost_center_code: text(rule?.cost_center_code),
    include_text: text(rule?.include_text),
    exclude_text: text(rule?.exclude_text),
    amount_min: text(rule?.amount_min),
    amount_max: text(rule?.amount_max),
    nombre_cuenta: text(rule?.nombre_cuenta),
  }
}

// Validación local; libro-mayor valida lo mismo y más (su mensaje se muestra tal cual).
function validate(form: Form, categories: Category[]): string | null {
  if (!/^\d+$/.test(form.priority)) return 'La prioridad debe ser un número entero (0 o más).'
  if (!form.category_id) return 'Elige la categoría de destino.'
  // libro-mayor solo acepta destinos activos ("Categoría no encontrada").
  if (!categories.find((c) => c.id === form.category_id)?.is_active) {
    return 'La categoría de destino está dada de baja: elige otra para guardar.'
  }
  if (CONDITION_KEYS.every((k) => form[k].trim() === '')) return 'La regla necesita al menos una condición.'
  for (const k of ['amount_min', 'amount_max'] as const) {
    if (form[k].trim() && !AMOUNT.test(form[k].trim())) return 'Los importes usan punto decimal y hasta 4 decimales.'
  }
  if (form.amount_min.trim() && form.amount_max.trim() && parseAmount(form.amount_min) > parseAmount(form.amount_max)) {
    return 'El importe mínimo no puede ser mayor que el máximo.'
  }
  return null
}

export default function RuleFormModal({
  rule,
  categories,
  canCreateCategory,
  nextPriority,
  onCategoriesChanged,
  onClose,
  onSaved,
}: RuleFormModalProps) {
  const [creatingCategory, setCreatingCategory] = useState(false)
  const [form, setForm] = useState(() => toForm(rule, nextPriority, categories))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof Form, value: string) => setForm((f) => ({ ...f, [key]: value }))
  const inactiveTarget = categories.some((c) => c.id === form.category_id && !c.is_active)
  const suffix = (c: Category) => (c.is_active ? '' : ' (de baja)')

  const submit = async () => {
    const invalid = validate(form, categories)
    if (invalid) {
      setError(invalid)
      return
    }
    const orNull = (v: string) => v.trim() || null
    const body: RuleInput = {
      priority: Number(form.priority),
      category_id: form.category_id,
      account_code: orNull(form.account_code),
      counter_account_code: orNull(form.counter_account_code),
      cost_center_code: orNull(form.cost_center_code),
      include_text: orNull(form.include_text),
      exclude_text: orNull(form.exclude_text),
      amount_min: orNull(form.amount_min),
      amount_max: orNull(form.amount_max),
      nombre_cuenta: orNull(form.nombre_cuenta),
    }
    setBusy(true)
    setError(null)
    try {
      if (rule) await rulesService.updateRule(rule.id, body)
      else await rulesService.createRule(body)
      toast.success('Regla guardada. Las líneas afectadas se reclasificarán en breve.')
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <FormModal open title={rule ? 'Editar regla' : 'Nueva regla'} submitLabel="Guardar" busy={busy} error={error}
        onSubmit={submit} onClose={onClose}>
        <p className="small text-body-secondary">
          Las reglas se evalúan por prioridad (menor primero) y gana la primera que cumple. Las condiciones vacías no
          filtran; las llenas deben cumplirse todas.
        </p>

        <div className="row g-3">
          <div className="col-4">
            <label htmlFor="rule-priority" className="form-label">Prioridad</label>
            <input id="rule-priority" className="form-control" inputMode="numeric" value={form.priority}
              onChange={(e) => set('priority', e.target.value)} />
          </div>
          <div className="col-8">
            <div className="d-flex align-items-center justify-content-between">
              <label htmlFor="rule-category" className="form-label">Clasificar como</label>
              {canCreateCategory && (
                <button type="button" className="btn btn-sm btn-link p-0 mb-2" onClick={() => setCreatingCategory(true)}>
                  <i className="bi bi-plus-lg me-1" aria-hidden="true" />
                  Nueva
                </button>
              )}
            </div>
            <select id="rule-category" className="form-select" value={form.category_id}
              onChange={(e) => set('category_id', e.target.value)}>
              {categoryTree(categories).map(({ parent, children }) => (
                <optgroup key={parent.id} label={parent.name}>
                  <option value={parent.id}>{parent.name} (sin subcategoría){suffix(parent)}</option>
                  {children.map((c) => <option key={c.id} value={c.id}>{parent.name} › {c.name}{suffix(c)}</option>)}
                </optgroup>
              ))}
            </select>
            {inactiveTarget && (
              <div className="form-text text-warning-emphasis">
                Esta categoría está dada de baja. Para guardar cambios, elige un destino activo.
              </div>
            )}
          </div>

          {TEXT_FIELDS.map((f) => (
            <div key={f.key} className="col-sm-6">
              <label htmlFor={`rule-${f.key}`} className="form-label">{f.label}</label>
              <input id={`rule-${f.key}`} className="form-control" placeholder={f.placeholder} value={form[f.key]}
                onChange={(e) => set(f.key, e.target.value)} />
              {f.help && <div className="form-text">{f.help}</div>}
            </div>
          ))}

          <div className="col-sm-6">
            <label htmlFor="rule-amount-min" className="form-label">Importe desde</label>
            <input id="rule-amount-min" className="form-control" inputMode="decimal" placeholder="0.00"
              value={form.amount_min} onChange={(e) => set('amount_min', e.target.value)} />
          </div>
          <div className="col-sm-6">
            <label htmlFor="rule-amount-max" className="form-label">Importe hasta</label>
            <input id="rule-amount-max" className="form-control" inputMode="decimal"
              value={form.amount_max} onChange={(e) => set('amount_max', e.target.value)} />
          </div>
        </div>
      </FormModal>

      {/* Fuera del <form> de la regla: un formulario no puede ir dentro de otro. */}
      {creatingCategory && (
        <CategoryFormModal
          action={{ kind: 'create', parent: null }}
          parentChoices={categories.filter((c) => c.parent_id === null && c.is_active)}
          onClose={() => setCreatingCategory(false)}
          onSaved={(created) => {
            onCategoriesChanged()
            set('category_id', created.id) // la nueva queda elegida como destino
          }}
        />
      )}
    </>
  )
}
