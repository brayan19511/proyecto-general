import { useState, type FormEvent } from 'react'
import CheckboxDropdown from '../../../shared/components/CheckboxDropdown'
import { toIsoDate } from '../../../shared/utils/format'
import type { Account, LiveQueryRequest } from '../types'

type LiveQueryFormProps = {
  accounts: Account[]
  busy: boolean
  onRun: (request: LiveQueryRequest) => void
}

const accountToken = (a: Account) => (a.match_mode === 'prefix' ? `${a.code}*` : a.code)
// "95*, 701110002" → ["95*", "701110002"]
const splitTokens = (text: string) => text.split(',').map((t) => t.trim()).filter(Boolean)

// Tramos que libro-mayor consulta a SAP en paralelo. Hasta un mes: por día
// (varias consultas chicas en paralelo); más largo: por mes (un año por día
// serían 366 consultas a SAP).
const DAY_SPLIT_MAX_DAYS = 31

function daysBetween(from: string, to: string) {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000) + 1
}

// Por defecto: el mes en curso, resumen + detalle.
function initialForm() {
  const today = new Date()
  return {
    registered: [] as string[],
    extra: '',
    dateFrom: toIsoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
    dateTo: toIsoDate(today),
    view: 'full' as LiveQueryRequest['view'],
  }
}

export default function LiveQueryForm({ accounts, busy, onRun }: LiveQueryFormProps) {
  const [form, setForm] = useState(initialForm)
  const set = (change: Partial<typeof form>) => setForm((f) => ({ ...f, ...change }))

  // Sin repetidos; libro-mayor valida formato, máximo de cuentas y de días.
  const tokens = [...new Set([...form.registered, ...splitTokens(form.extra)])]
  const reversed = form.dateFrom > form.dateTo
  const canRun = tokens.length > 0 && form.dateFrom !== '' && form.dateTo !== '' && !reversed
  const days = canRun ? daysBetween(form.dateFrom, form.dateTo) : 0
  const split: LiveQueryRequest['split'] = days <= DAY_SPLIT_MAX_DAYS ? 'day' : 'month'

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!canRun || busy) return
    onRun({ accounts: tokens, date_from: form.dateFrom, date_to: form.dateTo, split, view: form.view })
  }

  return (
    <form className="card card-body mb-3" onSubmit={handleSubmit}>
      <div className="row g-3 align-items-end">
        <div className="col-sm-6 col-lg-2">
          <span className="form-label small d-block">Cuentas registradas</span>
          <CheckboxDropdown
            label="Cuentas"
            icon="journal"
            align="start"
            options={accounts.map((a) => ({ key: accountToken(a), label: `${accountToken(a)}${a.name ? ` — ${a.name}` : ''}` }))}
            selected={form.registered}
            onChange={(registered) => set({ registered })}
          />
        </div>
        <div className="col-sm-6 col-lg-3">
          <label htmlFor="lq-extra" className="form-label small">Otras cuentas</label>
          <input id="lq-extra" className="form-control form-control-sm" placeholder="97*, 701110002"
            value={form.extra} onChange={(e) => set({ extra: e.target.value })} aria-describedby="lq-help" />
        </div>
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="lq-from" className="form-label small">Desde</label>
          <input id="lq-from" type="date" className="form-control form-control-sm" value={form.dateFrom}
            onChange={(e) => set({ dateFrom: e.target.value })} required />
        </div>
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="lq-to" className="form-label small">Hasta</label>
          <input id="lq-to" type="date" className={`form-control form-control-sm ${reversed ? 'is-invalid' : ''}`}
            value={form.dateTo} max={toIsoDate(new Date())} onChange={(e) => set({ dateTo: e.target.value })} required />
        </div>
        <div className="col-sm-6 col-lg-3">
          <label htmlFor="lq-view" className="form-label small">Resultado</label>
          <select id="lq-view" className="form-select form-select-sm" value={form.view}
            onChange={(e) => set({ view: e.target.value as LiveQueryRequest['view'] })}>
            <option value="full">Resumen con proveedor y detalle</option>
            <option value="summary">Solo resumen (más rápido, sin detalle)</option>
          </select>
        </div>
        <div className="col-lg-3">
          <button type="submit" className="btn btn-sm btn-primary" disabled={!canRun || busy}>
            {busy ? <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" /> : <i className="bi bi-lightning-charge me-1" aria-hidden="true" />}
            Consultar en SAP
          </button>
        </div>
      </div>

      {/* Ayudas en una sola línea: dentro de las columnas desalinean los campos. */}
      <div id="lq-help" className="form-text mt-2">
        "Otras cuentas": aunque no estén registradas; * al final = prefijo.
        {canRun && ` · ${tokens.length} cuenta(s): ${tokens.join(', ')} · ${days} días, consulta a SAP por ${split === 'day' ? 'día' : 'mes'}.`}
      </div>
    </form>
  )
}
