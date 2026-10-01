import { useState, type FormEvent } from 'react'
import CheckboxDropdown from '../../../shared/components/CheckboxDropdown'
import { toIsoDate } from '../../../shared/utils/format'
import { monthLabel } from '../summaryTree'
import type { Account, LedgerFilters } from '../types'

type LedgerFiltersBarProps = {
  initial: LedgerFilters
  accounts: Account[]
  onApply: (filters: LedgerFilters) => void
}

// Cuenta registrada → filtro de la API ("95*" si es por prefijo).
const accountToken = (a: Account) => (a.match_mode === 'prefix' ? `${a.code}*` : a.code)

// Últimos 24 meses, del más reciente al más antiguo, para el atajo "Mes".
function recentMonths() {
  const today = new Date()
  return Array.from({ length: 24 }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1)
    return { value: toIsoDate(d).slice(0, 7), label: monthLabel(d.getFullYear(), d.getMonth() + 1) }
  })
}

// Filtros que van al servidor. Se aplican con "Consultar" (no en cada cambio):
// cada consulta recorre las líneas del rango en libro-mayor.
export default function LedgerFiltersBar({ initial, accounts, onApply }: LedgerFiltersBarProps) {
  const [form, setForm] = useState(initial)
  const reversed = form.dateFrom !== '' && form.dateTo !== '' && form.dateFrom > form.dateTo
  const selectedAccounts = form.accounts ? form.accounts.split(',') : []

  const set = (change: Partial<LedgerFilters>) => setForm((f) => ({ ...f, ...change }))

  // "AAAA-MM" → del primer al último día del mes (sin pasar de hoy).
  const pickMonth = (value: string) => {
    if (!value) return
    const [year, month] = value.split('-').map(Number)
    const last = toIsoDate(new Date(year, month, 0))
    const today = toIsoDate(new Date())
    set({ dateFrom: `${value}-01`, dateTo: last < today ? last : today })
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!reversed && form.dateFrom && form.dateTo) onApply(form)
  }

  return (
    <form className="card card-body mb-3" onSubmit={handleSubmit}>
      <div className="row g-3 align-items-end">
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="lf-month" className="form-label small">Mes</label>
          <select id="lf-month" className="form-select form-select-sm" value="" onChange={(e) => pickMonth(e.target.value)}>
            <option value="">Elegir…</option>
            {recentMonths().map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="lf-from" className="form-label small">Desde</label>
          <input id="lf-from" type="date" className="form-control form-control-sm" value={form.dateFrom}
            onChange={(e) => set({ dateFrom: e.target.value })} required />
        </div>
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="lf-to" className="form-label small">Hasta</label>
          <input id="lf-to" type="date" className={`form-control form-control-sm ${reversed ? 'is-invalid' : ''}`}
            value={form.dateTo} onChange={(e) => set({ dateTo: e.target.value })} required />
        </div>
        <div className="col-sm-6 col-lg-2">
          <span className="form-label small d-block">Cuentas</span>
          <CheckboxDropdown
            label="Cuentas"
            icon="journal"
            align="start"
            emptyText="todas"
            options={accounts.map((a) => ({ key: accountToken(a), label: `${accountToken(a)}${a.name ? ` — ${a.name}` : ''}` }))}
            selected={selectedAccounts}
            onChange={(tokens) => set({ accounts: tokens.join(',') })}
          />
        </div>
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="lf-cc" className="form-label small">Centro de costo</label>
          <input id="lf-cc" className="form-control form-control-sm" value={form.costCenterCode}
            onChange={(e) => set({ costCenterCode: e.target.value })} />
        </div>
        <div className="col-lg-2">
          <button type="submit" className="btn btn-sm btn-primary" disabled={reversed}>
            <i className="bi bi-search me-1" aria-hidden="true" />
            Consultar
          </button>
        </div>
      </div>
    </form>
  )
}
