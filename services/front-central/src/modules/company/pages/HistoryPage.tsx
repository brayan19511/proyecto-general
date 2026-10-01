import { Fragment, useState, type FormEvent } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import { ACTION_FILTERS, actionLabel, actionTone } from '../historyLabels'
import * as historyService from '../services/historyService'
import * as membersService from '../services/membersService'
import type { HistoryEvent } from '../types'

const EMPTY: historyService.HistoryFilters = { action: '', actorId: '', resourceId: '' }

const show = (value: unknown) =>
  value === null || value === undefined || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)

// Campos que cambiaron entre antes y después (los de alta o baja muestran todo).
function changes(event: HistoryEvent) {
  const keys = [...new Set([...Object.keys(event.before), ...Object.keys(event.after)])]
  return keys
    .filter((k) => JSON.stringify(event.before[k]) !== JSON.stringify(event.after[k]))
    .map((k) => ({ field: k, before: event.before[k], after: event.after[k] }))
}

// Nombre legible del recurso, si el evento lo trae (name, code, email…).
function resourceName(event: HistoryEvent) {
  const data = { ...event.before, ...event.after }
  const parts = [data.name, data.code, data.email, data.permission].filter((v) => typeof v === 'string')
  return parts.length > 0 ? parts.join(' · ') : null
}

// Empresa › Historial (fase 1: solo platform admin). Quién cambió qué y cuándo.
// Los eventos son de solo anexado: no se editan ni se borran.
export default function HistoryPage() {
  const [form, setForm] = useState(EMPTY)
  const [filters, setFilters] = useState(EMPTY)
  const [offset, setOffset] = useState(0)
  const [open, setOpen] = useState<string | null>(null)
  const events = useApi(() => historyService.listHistory(filters, offset), [filters.action, filters.actorId, filters.resourceId, offset])
  const members = useApi(() => membersService.listMembers(0))

  const apply = (next: historyService.HistoryFilters) => {
    setForm(next)
    setFilters(next)
    setOffset(0)
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    apply(form)
  }

  return (
    <>
      <PageHeader
        title="Historial"
        description="Quién cambió qué y cuándo en esta empresa: miembros, puestos, áreas, roles y permisos."
        actions={
          <button type="button" className="btn btn-outline-secondary" onClick={events.reload}>
            <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
            Actualizar
          </button>
        }
      />

      <form className="card card-body mb-3" onSubmit={handleSubmit}>
        <div className="row g-3 align-items-end">
          <div className="col-sm-6 col-lg-3">
            <label htmlFor="h-action" className="form-label small">Sobre</label>
            <select id="h-action" className="form-select form-select-sm" value={form.action}
              onChange={(e) => apply({ ...form, action: e.target.value })}>
              <option value="">Todo</option>
              {ACTION_FILTERS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>
          </div>
          <div className="col-sm-6 col-lg-3">
            <label htmlFor="h-actor" className="form-label small">Hecho por</label>
            <select id="h-actor" className="form-select form-select-sm" value={form.actorId}
              onChange={(e) => apply({ ...form, actorId: e.target.value })}>
              <option value="">Cualquiera</option>
              {(members.data ?? []).map((m) => <option key={m.user_id} value={m.user_id}>{m.email}</option>)}
            </select>
          </div>
          <div className="col-sm-8 col-lg-4">
            <label htmlFor="h-resource" className="form-label small">Id del recurso</label>
            <input id="h-resource" className="form-control form-control-sm font-monospace" value={form.resourceId}
              onChange={(e) => setForm({ ...form, resourceId: e.target.value })} placeholder="Pega un id o usa “Ver solo este”" />
          </div>
          <div className="col-sm-4 col-lg-2 d-flex gap-2">
            <button type="submit" className="btn btn-sm btn-primary">Filtrar</button>
            <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => apply(EMPTY)}>Limpiar</button>
          </div>
        </div>
      </form>

      <AsyncState loading={events.loading} error={events.error} onRetry={events.reload} hasData={events.data !== undefined}>
        <div className="table-responsive border rounded-3">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
              <tr><th>Fecha</th><th>Acción</th><th>Recurso</th><th>Hecho por</th><th>Cambios</th></tr>
            </thead>
            <tbody>
              {(events.data ?? []).length === 0 && (
                <tr><td colSpan={5} className="text-center text-body-secondary py-4">No hay cambios con estos filtros.</td></tr>
              )}
              {(events.data ?? []).map((e) => {
                const diff = changes(e)
                return (
                  <Fragment key={e.id}>
                    <tr>
                      <td className="text-nowrap small">{formatDateTime(e.created_at)}</td>
                      <td><StatusBadge tone={actionTone(e.action)} label={actionLabel(e.action)} /></td>
                      <td>
                        <div>{resourceName(e) ?? <span className="text-body-secondary">—</span>}</div>
                        <button type="button" className="btn btn-link btn-sm p-0" onClick={() => apply({ ...EMPTY, resourceId: e.resource_id })}>
                          Ver solo este
                        </button>
                      </td>
                      <td className="small">{e.actor_email ?? (e.actor_id ? e.actor_id.slice(0, 8) : 'Sistema')}</td>
                      <td>
                        {diff.length === 0 ? (
                          <span className="small text-body-secondary">Sin cambios de valores</span>
                        ) : (
                          <button type="button" className="btn btn-sm btn-outline-secondary" aria-expanded={open === e.id}
                            onClick={() => setOpen(open === e.id ? null : e.id)}>
                            {diff.length} {diff.length === 1 ? 'campo' : 'campos'}
                            <i className={`bi bi-chevron-${open === e.id ? 'up' : 'down'} ms-1`} aria-hidden="true" />
                          </button>
                        )}
                      </td>
                    </tr>
                    {open === e.id && (
                      <tr>
                        <td colSpan={5} className="bg-body-tertiary">
                          <table className="table table-sm mb-0 small bg-transparent">
                            <thead><tr><th>Campo</th><th>Antes</th><th>Después</th></tr></thead>
                            <tbody>
                              {diff.map((d) => (
                                <tr key={d.field}>
                                  <td className="font-monospace">{d.field}</td>
                                  <td className="text-danger-emphasis text-break">{show(d.before)}</td>
                                  <td className="text-success-emphasis text-break">{show(d.after)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
        <Pager offset={offset} limit={historyService.HISTORY_PAGE_SIZE} count={events.data?.length ?? 0} onChange={setOffset} />
      </AsyncState>
    </>
  )
}
