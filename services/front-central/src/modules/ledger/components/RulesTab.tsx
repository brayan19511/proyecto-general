import { useState } from 'react'
import { LEDGER_UPDATE, useCanAccess } from '../../../shared/auth/access'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatAmount, parseAmount } from '../../../shared/utils/decimal'
import { categoryPath } from '../categories'
import * as rulesService from '../services/rulesService'
import type { Category, Rule } from '../types'
import RuleFormModal from './RuleFormModal'

// Condiciones de una regla en texto corto, p. ej. "Cuenta 959005993 · Glosa contiene "alquiler"".
function describeConditions(r: Rule): string[] {
  const parts: string[] = []
  if (r.account_code) parts.push(`Cuenta ${r.account_code}`)
  if (r.counter_account_code) parts.push(`Contracuenta ${r.counter_account_code}`)
  if (r.cost_center_code) parts.push(`Centro ${r.cost_center_code}`)
  if (r.include_text) parts.push(`Glosa contiene "${r.include_text}"`)
  if (r.exclude_text) parts.push(`Glosa no contiene "${r.exclude_text}"`)
  if (r.amount_min || r.amount_max) {
    const min = r.amount_min ? formatAmount(parseAmount(r.amount_min)) : '…'
    const max = r.amount_max ? formatAmount(parseAmount(r.amount_max)) : '…'
    parts.push(`Importe ${min} a ${max}`)
  }
  return parts
}

type Editing = { rule: Rule | null } | null // rule null = nueva

// Opciones de destino: las activas y, al editar, también la actual de la regla
// (y su padre) aunque esté de baja; si no, el selector mostraría otra y al
// guardar cambiaría el destino sin querer.
function formCategories(all: Category[], rule: Rule | null): Category[] {
  const current = rule ? all.find((c) => c.id === rule.category_id) : undefined
  const keep = new Set([current?.id, current?.parent_id].filter(Boolean))
  return all.filter((c) => c.is_active || keep.has(c.id))
}

export default function RulesTab() {
  const canEdit = useCanAccess()({ anyOf: LEDGER_UPDATE })
  const [includeInactive, setIncludeInactive] = useState(false)
  const [search, setSearch] = useState('')
  const rules = useApi(() => rulesService.listRules(includeInactive), [includeInactive])
  // Todas (incluidas de baja) para nombrar el destino de reglas antiguas.
  const categories = useApi(() => rulesService.listCategories(true))
  const [editing, setEditing] = useState<Editing>(null)
  const [toDeactivate, setToDeactivate] = useState<Rule | null>(null)
  const [busy, setBusy] = useState(false)

  const allCategories = categories.data ?? []
  const pathOf = (id: string) => categoryPath(allCategories, id)
  const term = search.trim().toLowerCase()
  const rows = (rules.data ?? []).filter(
    (r) => !term || [pathOf(r.category_id), r.nombre_cuenta ?? '', ...describeConditions(r)].join(' ').toLowerCase().includes(term),
  )
  const nextPriority = Math.max(0, ...(rules.data ?? []).map((r) => r.priority)) + 10

  const deactivate = async () => {
    if (!toDeactivate) return
    setBusy(true)
    try {
      await rulesService.deactivateRule(toDeactivate.id)
      toast.success('Regla dada de baja. Sus líneas se reclasificarán con las reglas que quedan.')
      rules.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setToDeactivate(null)
    }
  }

  const columns: Column<Rule>[] = [
    { header: 'Prioridad', className: 'text-end', render: (r) => r.priority },
    {
      header: 'Clasifica como',
      render: (r) => (
        <>
          <div>{pathOf(r.category_id)}</div>
          {r.nombre_cuenta && <div className="small text-body-secondary">Nombre de cuenta: {r.nombre_cuenta}</div>}
        </>
      ),
    },
    {
      header: 'Condiciones',
      render: (r) => (
        <div className="d-flex flex-wrap gap-1">
          {describeConditions(r).map((c) => <span key={c} className="badge text-bg-light border fw-normal">{c}</span>)}
        </div>
      ),
    },
    {
      header: 'Estado',
      render: (r) => <StatusBadge tone={r.is_active ? 'success' : 'secondary'} label={r.is_active ? 'Activa' : 'De baja'} />,
    },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (r) =>
        canEdit && r.is_active && (
          <>
            <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setEditing({ rule: r })}
              aria-label="Editar regla" title="Editar">
              <i className="bi bi-pencil" aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setToDeactivate(r)}
              aria-label="Dar de baja la regla" title="Dar de baja">
              <i className="bi bi-archive" aria-hidden="true" />
            </button>
          </>
        ),
    },
  ]

  return (
    <>
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 280 }} placeholder="Buscar categoría, cuenta, glosa…"
          aria-label="Buscar reglas" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="form-check form-switch mb-0">
          <input id="rule-inactive" type="checkbox" className="form-check-input" checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)} />
          <label htmlFor="rule-inactive" className="form-check-label">Ver dadas de baja</label>
        </div>
        {canEdit && (
          <button type="button" className="btn btn-primary ms-auto" onClick={() => setEditing({ rule: null })}
            disabled={!allCategories.some((c) => c.is_active)} title={allCategories.some((c) => c.is_active) ? undefined : 'Primero crea una categoría'}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva regla
          </button>
        )}
      </div>

      <AsyncState loading={rules.loading || categories.loading} error={rules.error ?? categories.error} onRetry={rules.reload}
        hasData={rules.data !== undefined && categories.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(r) => r.id}
          emptyMessage={term ? 'Ninguna regla coincide con la búsqueda.' : 'Aún no hay reglas.'} />
      </AsyncState>

      {editing && (
        <RuleFormModal
          rule={editing.rule}
          categories={formCategories(allCategories, editing.rule)}
          canCreateCategory={canEdit}
          nextPriority={nextPriority}
          onCategoriesChanged={categories.reload}
          onClose={() => setEditing(null)}
          onSaved={rules.reload}
        />
      )}

      <ConfirmDialog
        open={toDeactivate !== null}
        title="Dar de baja la regla"
        message="La regla deja de aplicarse y sus líneas se reclasificarán con las reglas que quedan. No se borra: queda en el historial."
        confirmLabel="Dar de baja"
        danger
        busy={busy}
        onConfirm={deactivate}
        onCancel={() => setToDeactivate(null)}
      />
    </>
  )
}
