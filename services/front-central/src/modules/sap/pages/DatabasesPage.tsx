import { useState, type FormEvent } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import { SAP_EXECUTE, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import * as sapService from '../services/sapService'
import type { SapDatabase } from '../types'
import ServiceLayerSettings from '../components/ServiceLayerSettings'

// SAP › Configuración: URL del Service Layer de la empresa (solo platform admin
// la cambia) y lista de bases (CompanyDB) que se sugieren al crear un trabajo
// (una ayuda: también se puede escribir otra).
export default function DatabasesPage() {
  const canExecute = useCanAccess()({ anyOf: SAP_EXECUTE })
  const databases = useApi(() => sapService.listDatabases())
  const [companyDb, setCompanyDb] = useState('')
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [toDelete, setToDelete] = useState<SapDatabase | null>(null)

  const add = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      await sapService.createDatabase(companyDb.trim(), label.trim())
      toast.success('Base agregada')
      setCompanyDb('')
      setLabel('')
      databases.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!toDelete) return
    setBusy(true)
    try {
      await sapService.deleteDatabase(toDelete.id)
      toast.success('Base dada de baja')
      databases.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setToDelete(null)
    }
  }

  const columns: Column<SapDatabase>[] = [
    { header: 'Base (CompanyDB)', className: 'font-monospace', render: (d) => d.company_db },
    { header: 'Descripción', render: (d) => d.label ?? '—' },
    { header: 'Agregada', className: 'small text-body-secondary', render: (d) => formatDateTime(d.created_at) },
    ...(canExecute
      ? [{
          header: 'Acciones',
          className: 'text-end',
          render: (d: SapDatabase) => (
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setToDelete(d)} title="Dar de baja">
              <i className="bi bi-archive" aria-hidden="true" /><span className="visually-hidden">Dar de baja {d.company_db}</span>
            </button>
          ),
        }]
      : []),
  ]

  return (
    <>
      <PageHeader title="Configuración SAP" description="Servidor de SAP de la empresa y bases que se sugieren al crear un trabajo." />
      <ServiceLayerSettings />
      <h2 className="h6">Bases SAP sugeridas</h2>
      {canExecute && (
        <form className="d-flex flex-wrap gap-2 mb-3" onSubmit={add}>
          <input className="form-control form-control-sm font-monospace" style={{ maxWidth: 220 }} placeholder="SBO_EMPRESA" aria-label="Base SAP"
            maxLength={100} pattern="[A-Za-z0-9_]+" title="Letras, números y _" required value={companyDb} onChange={(e) => setCompanyDb(e.target.value)} />
          <input className="form-control form-control-sm" style={{ maxWidth: 260 }} placeholder="Descripción (opcional)" aria-label="Descripción"
            maxLength={100} value={label} onChange={(e) => setLabel(e.target.value)} />
          <button type="submit" className="btn btn-sm btn-primary" disabled={busy}>Agregar</button>
        </form>
      )}
      <AsyncState loading={databases.loading} error={databases.error} onRetry={databases.reload} hasData={databases.data !== undefined}>
        <DataTable columns={columns} rows={databases.data ?? []} rowKey={(d) => d.id} emptyMessage="Aún no hay bases en la lista." />
      </AsyncState>
      <ConfirmDialog
        open={toDelete !== null}
        title="Dar de baja la base"
        message={`${toDelete?.company_db ?? ''} deja de sugerirse. Los trabajos que la usaron no cambian.`}
        confirmLabel="Dar de baja"
        danger
        busy={busy}
        onConfirm={remove}
        onCancel={() => setToDelete(null)}
      />
    </>
  )
}
