import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDate } from '../../../shared/utils/format'
import * as companiesService from '../services/companiesService'
import type { AdminCompany } from '../types'

type SapCompanyModalProps = {
  company: AdminCompany
  onClose: () => void
  onChanged: () => void
}

// Identificador de HANA: letras, dígitos y _, sin empezar por dígito (libro-mayor
// valida lo mismo y lo usa en una lista cerrada, nunca desde el cliente).
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/

// Compañía SAP de una empresa en libro-mayor: de qué schema y vista de HANA se
// leen sus líneas y desde qué fecha. Una por empresa.
export default function SapCompanyModal({ company, onClose, onChanged }: SapCompanyModalProps) {
  const sap = useApi(() => companiesService.getSapCompany(company.id), [company.id])
  const current = sap.data ?? null
  const [form, setForm] = useState<{ sap_schema: string; source_view: string; sync_start_date: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  // El formulario arranca con los valores actuales (o vacío) al cargar.
  const values = form ?? {
    sap_schema: current?.sap_schema ?? '',
    source_view: current?.source_view ?? '',
    sync_start_date: current?.sync_start_date ?? `${new Date().getFullYear()}-01-01`,
  }
  const set = (key: keyof typeof values, value: string) => setForm({ ...values, [key]: value })
  const valid = IDENTIFIER.test(values.sap_schema) && IDENTIFIER.test(values.source_view) && values.sync_start_date !== ''

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      if (current) {
        const changes: Record<string, string> = {}
        for (const key of ['sap_schema', 'source_view', 'sync_start_date'] as const) {
          if (values[key] !== current[key]) changes[key] = values[key]
        }
        if (Object.keys(changes).length > 0) await companiesService.updateSapCompany(company.id, changes)
      } else {
        await companiesService.createSapCompany(company.id, values)
      }
      toast.success('Compañía SAP guardada')
      onChanged()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 409 schema de otra empresa o ya con líneas, 422 identificador inválido
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await companiesService.deleteSapCompany(company.id)
      toast.success('Compañía SAP dada de baja')
      onChanged()
      onClose()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setConfirmDelete(false)
    }
  }

  return (
    <>
      <FormModal open={!confirmDelete} title={`Compañía SAP de ${company.name}`} submitLabel="Guardar" busy={busy} error={error}
        canSubmit={valid && !sap.loading} onSubmit={submit} onClose={onClose}>
        <AsyncState loading={sap.loading} error={sap.error} onRetry={sap.reload} hasData={sap.data !== undefined}>
          <p className="small text-body-secondary">
            {current
              ? `Configurada desde el ${formatDate(current.created_at.slice(0, 10))}. libro-mayor lee de aquí las líneas de las cuentas de esta empresa.`
              : 'Esta empresa aún no tiene compañía SAP: no puede registrar cuentas ni sincronizar hasta configurarla.'}
          </p>
          <div className="mb-3">
            <label htmlFor="sap-schema" className="form-label">Schema SAP (base SBO)</label>
            <input id="sap-schema" className="form-control font-monospace" placeholder="SBO_RASH_PRODUCCION" value={values.sap_schema}
              onChange={(e) => set('sap_schema', e.target.value.trim())} aria-describedby="sap-schema-help" />
            <div id="sap-schema-help" className="form-text">
              Letras, números y _. No se puede cambiar cuando ya hay líneas sincronizadas; un schema solo puede ser de una empresa.
            </div>
          </div>
          <div className="mb-3">
            <label htmlFor="sap-view" className="form-label">Vista de origen</label>
            <input id="sap-view" className="form-control font-monospace" placeholder="VW_LIBRO_MAYOR_PERSONALIZADO_2"
              value={values.source_view} onChange={(e) => set('source_view', e.target.value.trim())} />
          </div>
          <div>
            <label htmlFor="sap-start" className="form-label">Sincronizar desde</label>
            <input id="sap-start" type="date" className="form-control" value={values.sync_start_date}
              onChange={(e) => set('sync_start_date', e.target.value)} aria-describedby="sap-start-help" />
            <div id="sap-start-help" className="form-text">Fecha contable desde la que se hace la carga inicial.</div>
          </div>
          {current && (
            <button type="button" className="btn btn-sm btn-outline-danger mt-4" onClick={() => setConfirmDelete(true)} disabled={busy}>
              Dar de baja la compañía SAP
            </button>
          )}
        </AsyncState>
      </FormModal>

      <ConfirmDialog
        open={confirmDelete}
        title="Dar de baja la compañía SAP"
        message={`${company.name} deja de sincronizarse desde SAP. Las líneas ya traídas se conservan. Para retomar, configura otra.`}
        confirmLabel="Dar de baja"
        danger
        busy={busy}
        onConfirm={remove}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  )
}
