import { useState, type FormEvent } from 'react'
import { EMPTY_LOG_FILTERS, OUTCOME } from '../logLabels'
import type { AdminUser, LogFilters, LogOutcome } from '../types'

type LogFiltersBarProps = {
  initial: LogFilters
  users: AdminUser[]
  loginPath: string | null // atajo "Inicios de sesión" si el servicio los registra
  onApply: (filters: LogFilters) => void
}

export default function LogFiltersBar({ initial, users, loginPath, onApply }: LogFiltersBarProps) {
  const [form, setForm] = useState(initial)
  const set = (change: Partial<LogFilters>) => setForm((f) => ({ ...f, ...change }))

  // Los atajos aplican de inmediato.
  const applyPreset = (change: Partial<LogFilters>) => {
    const next = { ...EMPTY_LOG_FILTERS, ...change }
    setForm(next)
    onApply(next)
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    onApply(form)
  }

  return (
    <form className="card card-body mb-3" onSubmit={handleSubmit}>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <span className="small text-body-secondary align-self-center">Atajos:</span>
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => applyPreset({ outcome: 'error' })}>
          Errores
        </button>
        <button type="button" className="btn btn-sm btn-outline-warning" onClick={() => applyPreset({ outcome: 'warning' })}>
          Advertencias
        </button>
        {loginPath && (
          <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => applyPreset({ pathPrefix: loginPath })}>
            Inicios de sesión
          </button>
        )}
      </div>

      <div className="row g-3 align-items-end">
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="log-outcome" className="form-label small">Resultado</label>
          <select id="log-outcome" className="form-select form-select-sm" value={form.outcome}
            onChange={(e) => set({ outcome: e.target.value as LogOutcome | '' })}>
            <option value="">Todos</option>
            {Object.entries(OUTCOME).map(([value, { label }]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <div className="col-sm-6 col-lg-3">
          <label htmlFor="log-user" className="form-label small">Usuario</label>
          <select id="log-user" className="form-select form-select-sm" value={form.userId}
            onChange={(e) => set({ userId: e.target.value })}>
            <option value="">Todos</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
          </select>
        </div>
        <div className="col-sm-6 col-lg-3">
          <label htmlFor="log-path" className="form-label small">Ruta que empieza con</label>
          <input id="log-path" className="form-control form-control-sm font-monospace" placeholder="/libro-mayor/sync-runs"
            value={form.pathPrefix} onChange={(e) => set({ pathPrefix: e.target.value })} />
        </div>
        <div className="col-sm-6 col-lg-2">
          <label htmlFor="log-trace" className="form-label small">Trace id</label>
          <input id="log-trace" className="form-control form-control-sm font-monospace"
            value={form.traceId} onChange={(e) => set({ traceId: e.target.value })} />
        </div>
        <div className="col-lg-2 d-flex gap-2">
          <button type="submit" className="btn btn-sm btn-primary">
            <i className="bi bi-funnel me-1" aria-hidden="true" />
            Filtrar
          </button>
          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => applyPreset({})}>
            Limpiar
          </button>
        </div>
      </div>
    </form>
  )
}
