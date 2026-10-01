import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import TemplateFormModal from '../components/TemplateFormModal'
import TemplatePreviewModal from '../components/TemplatePreviewModal'
import * as notificationsService from '../services/notificationsService'
import type { Template } from '../types'

// Plataforma › Plantillas de correo (solo platform admin en el front): asunto y cuerpo con parámetros que
// usan los servicios por código (p. ej. pagos-proveedores).
export default function TemplatesPage() {
  const [includeInactive, setIncludeInactive] = useState(false)
  const [search, setSearch] = useState('')
  const templates = useApi(() => notificationsService.listTemplates(includeInactive), [includeInactive])
  const [form, setForm] = useState<{ template: Template | null } | null>(null)
  const [previewing, setPreviewing] = useState<Template | null>(null)
  const [pending, setPending] = useState<{ kind: 'delete' | 'restore'; template: Template } | null>(null)
  const [busy, setBusy] = useState(false)

  const term = search.trim().toLowerCase()
  const rows = (templates.data?.items ?? []).filter((t) => !term || `${t.code} ${t.name} ${t.description ?? ''}`.toLowerCase().includes(term))

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'delete') await notificationsService.deleteTemplate(pending.template.id)
      else await notificationsService.restoreTemplate(pending.template.id)
      toast.success(pending.kind === 'delete' ? 'Plantilla dada de baja' : 'Plantilla restaurada')
      templates.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const columns: Column<Template>[] = [
    {
      header: 'Plantilla',
      render: (t) => (
        <>
          <div>{t.name}</div>
          <div className="small text-body-secondary font-monospace">{t.code}</div>
        </>
      ),
    },
    { header: 'Asunto', className: 'small', render: (t) => t.subject_template },
    { header: 'Actualizada', className: 'small text-nowrap', render: (t) => formatDateTime(t.updated_at) },
    { header: 'Estado', render: (t) => <StatusBadge tone={t.is_active ? 'success' : 'secondary'} label={t.is_active ? 'Activa' : 'De baja'} /> },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (t) =>
        t.is_active ? (
          <>
            <button type="button" className="btn btn-sm btn-outline-primary me-1" onClick={() => setPreviewing(t)} title="Vista previa">
              <i className="bi bi-eye" aria-hidden="true" />
              <span className="visually-hidden">Vista previa de {t.name}</span>
            </button>
            <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setForm({ template: t })} title="Editar">
              <i className="bi bi-pencil" aria-hidden="true" />
              <span className="visually-hidden">Editar {t.name}</span>
            </button>
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'delete', template: t })} title="Dar de baja">
              <i className="bi bi-archive" aria-hidden="true" />
              <span className="visually-hidden">Dar de baja {t.name}</span>
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-sm btn-outline-success" onClick={() => setPending({ kind: 'restore', template: t })}>Restaurar</button>
        ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Plantillas de correo"
        description="Plantillas de la empresa activa, para todos los módulos: asunto y cuerpo con parámetros {{ nombre }}; los servicios las piden por su código."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setForm({ template: null })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva plantilla
          </button>
        }
      />
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 280 }} placeholder="Buscar plantilla…" aria-label="Buscar plantillas"
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="form-check form-switch mb-0">
          <input id="tpl-inactive" type="checkbox" className="form-check-input" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
          <label htmlFor="tpl-inactive" className="form-check-label">Ver dadas de baja</label>
        </div>
      </div>
      <AsyncState loading={templates.loading} error={templates.error} onRetry={templates.reload} hasData={templates.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(t) => t.id} emptyMessage={term ? 'Ninguna plantilla coincide.' : 'Aún no hay plantillas.'} />
      </AsyncState>

      {form && <TemplateFormModal template={form.template} onClose={() => setForm(null)} onSaved={templates.reload} />}
      {previewing && <TemplatePreviewModal template={previewing} onClose={() => setPreviewing(null)} />}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'delete' ? 'Dar de baja la plantilla' : 'Restaurar plantilla'}
        message={pending?.kind === 'delete'
          ? `Los envíos que pidan ${pending.template.code} fallarán con 422 hasta restaurarla.`
          : `${pending?.template.code ?? ''} vuelve a estar disponible.`}
        confirmLabel={pending?.kind === 'delete' ? 'Dar de baja' : 'Restaurar'}
        danger={pending?.kind === 'delete'}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
